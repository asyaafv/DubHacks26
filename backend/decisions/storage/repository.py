"""User-scoped persistence. Construct only through Database.transaction()."""
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
from uuid import UUID

from backend.app.schemas import (Reward, RewardStatus, Event, EventType, Card,
                                 Membership, Merchant, Wallet, EmailClassification)
from backend.decisions.common import (utc, canonical_domain, vector_literal, exact_number)

ELIGIBLE = "status='active' AND (starts_at IS NULL OR starts_at <= $2) AND (expires_at IS NULL OR expires_at > $2)"


@dataclass(frozen=True)
class StoredEvent:
    id: UUID
    sequence: int
    event: Event


class Repository:
    def __init__(self, conn, user_id, key):
        self._conn, self.user_id, self._key = conn, user_id, key

    async def _insert(self, table, model, *, secret=None, extras=None):
        # All table/column names come exclusively from internal model allowlists.
        data = model.model_dump(mode='python')
        for field in ('created_at', 'updated_at', 'expires_at', 'starts_at'):
            if data.get(field) is not None:
                data[field] = utc(data[field])
        columns, args, expressions = [], [], []
        plaintext = data.pop(secret, None) if secret else None
        for name, value in data.items():
            if hasattr(value, 'value'):
                value = value.value
            if name in ('field_confidence', 'category_rates'):
                value = json.dumps(model.model_dump(mode='json')[name])
            columns.append(name)
            args.append(value)
            expressions.append(f'${len(args)}')
        if secret:
            encrypted = 'code_encrypted' if secret == 'code' else 'member_id_encrypted'
            columns.append(encrypted)
            args.extend([plaintext, self._key])
            expressions.append(f'pgp_sym_encrypt(${len(args)-1}::text, ${len(args)}::text)')
        for name, value in (extras or {}).items():
            columns.append(name)
            args.append(value)
            expressions.append(f'${len(args)}' + ('::vector' if name == 'embedding' else ''))
        sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join(expressions)}) ON CONFLICT DO NOTHING RETURNING id"
        return await self._conn.fetchval(sql, *args) is not None

    def _owner(self, model):
        if model.user_id != self.user_id:
            raise ValueError('Resource owner does not match transaction owner')

    async def save_reward(self, reward: Reward, *, dedupe_key=None, embedding=None):
        self._owner(reward)
        exact_number(reward.value, 6)
        for val in (reward.min_spend, reward.max_discount):
            if val is not None:
                exact_number(val, 2)
        extras = {'dedupe_key': dedupe_key}
        if embedding is not None:
            extras['embedding'] = vector_literal(embedding)
        added = await self._insert('rewards', reward, secret='code', extras=extras)
        if added:
            await self.append_event(EventType.reward_added, reward.id)
        return added

    def _reward(self, row):
        if row is None:
            return None
        data = dict(row)
        data['field_confidence'] = json.loads(data['field_confidence'])
        return Reward.model_validate(data)

    async def get_reward(self, reward_id, reveal_code=False):
        # Decrypt only after ownership predicate; secret never enters an event.
        return self._reward(await self._conn.fetchrow(
            "SELECT *, CASE WHEN $3 THEN pgp_sym_decrypt(code_encrypted,$4) ELSE NULL END AS code FROM rewards WHERE user_id=$1 AND id=$2",
            self.user_id, reward_id, reveal_code, self._key))

    async def list_rewards(self, eligible_only=True, now=None, since=None):
        args = [self.user_id]
        predicate = 'user_id=$1'
        if eligible_only:
            args.append(utc(now))
            predicate += ' AND ' + ELIGIBLE
        if since is not None:
            args.append(utc(since))
            predicate += f' AND updated_at >= ${len(args)}'
        rows = await self._conn.fetch(f'SELECT *, NULL::text AS code FROM rewards WHERE {predicate} ORDER BY updated_at,id', *args)
        return [self._reward(row) for row in rows]

    async def snapshot_time(self) -> datetime:
        """Database UTC watermark; this repository already holds the user lock."""
        return utc(await self._conn.fetchval('SELECT clock_timestamp()'))

    async def list_expiration_candidates(self, now: datetime, window_end: datetime,
                                         after: UUID | None = None, limit: int = 100) -> list[Reward]:
        """Page active expiring/expired rewards, including the overdue backlog.

        The job owns alert policy and transitions; this method never mutates data
        and never reveals codes. UUID order remains stable as statuses change.
        """
        if not 1 <= limit <= 1000:
            raise ValueError('Invalid expiration page size')
        if utc(window_end) < utc(now):
            raise ValueError('Expiration window must not end before now')
        rows = await self._conn.fetch(
            "SELECT *, NULL::text AS code FROM rewards WHERE user_id=$1 AND status='active' "
            "AND expires_at <= $2 AND ($3::uuid IS NULL OR id > $3) ORDER BY id LIMIT $4",
            self.user_id, utc(window_end), after, limit)
        return [self._reward(row) for row in rows]

    async def search_rewards(self, embedding, limit=10, now=None):
        if not 1 <= limit <= 100:
            raise ValueError('Invalid limit')
        rows = await self._conn.fetch(
            f'WITH candidates AS MATERIALIZED (SELECT * FROM rewards WHERE user_id=$1 AND {ELIGIBLE} AND embedding IS NOT NULL) SELECT *, NULL::text AS code FROM candidates ORDER BY embedding <=> $3::vector,id LIMIT $4',
            self.user_id, utc(now), vector_literal(embedding), limit)
        return [self._reward(row) for row in rows]

    async def set_reward_status(self, reward_id, status):
        status = RewardStatus(status)
        row = await self._conn.fetchrow(
            'UPDATE rewards SET status=$3 WHERE user_id=$1 AND id=$2 AND status<>$3 RETURNING id',
            self.user_id, reward_id, status.value)
        if row:
            await self.append_event(EventType.reward_used if status == RewardStatus.used else EventType.reward_updated, reward_id)
        return row is not None

    async def claim_email(self, message_id, classification, *, content_hash=None, rewards_extracted=0):
        return await self._conn.fetchval(
            'INSERT INTO processed_emails(user_id,message_id,classification,content_hash,rewards_extracted) VALUES($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING RETURNING message_id',
            self.user_id, message_id, EmailClassification(classification).value, content_hash, rewards_extracted) is not None

    async def set_email_result(self, message_id, classification, rewards_extracted):
        return await self._conn.fetchval(
            'UPDATE processed_emails SET classification=$3,rewards_extracted=$4 WHERE user_id=$1 AND message_id=$2 RETURNING message_id',
            self.user_id, message_id, EmailClassification(classification).value, rewards_extracted) is not None

    async def append_event(self, event_type, reward_id=None, *, dedupe_key=None):
        event_type = EventType(event_type)
        data = {}
        if reward_id is not None:
            row = await self._conn.fetchrow('SELECT status,expires_at FROM rewards WHERE user_id=$1 AND id=$2', self.user_id, reward_id)
            if row is None:
                raise ValueError('Reward not found for event owner')
            data = {'status': row['status'], 'expires_at': row['expires_at'].isoformat() if row['expires_at'] else None}
        return await self._conn.fetchval(
            'INSERT INTO events(user_id,event_type,reward_id,data,dedupe_key) VALUES($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING RETURNING id',
            self.user_id, event_type.value, reward_id, json.dumps(data), dedupe_key) is not None

    async def event_watermark(self) -> int:
        """Highest visible sequence for this locked owner; zero if empty."""
        return await self._conn.fetchval(
            'SELECT COALESCE(max(sequence), 0) FROM events WHERE user_id=$1', self.user_id)

    async def list_events(self, after=0, limit=100):
        if after < 0 or not 1 <= limit <= 1000:
            raise ValueError('Invalid replay window')
        rows = await self._conn.fetch('SELECT * FROM events WHERE user_id=$1 AND sequence>$2 ORDER BY sequence LIMIT $3', self.user_id, after, limit)
        return self._stored_events(rows)

    async def list_events_since(self, since: datetime, after: int = 0,
                                limit: int = 100) -> list[StoredEvent]:
        """Replay by durable insertion time, independent of reward timestamps."""
        if after < 0 or not 1 <= limit <= 1000:
            raise ValueError('Invalid replay window')
        rows = await self._conn.fetch(
            'SELECT * FROM events WHERE user_id=$1 AND created_at >= $2 AND sequence > $3 ORDER BY sequence LIMIT $4',
            self.user_id, utc(since), after, limit)
        return self._stored_events(rows)

    def _stored_events(self, rows):
        return [StoredEvent(row['id'], row['sequence'], Event(event_type=row['event_type'],
                    user_id=self.user_id, reward_id=row['reward_id'], data=json.loads(row['data']),
                    timestamp=row['created_at'])) for row in rows]

    async def add_redemption(self, redemption) -> bool:
        """Insert one redemption; False when this reward was already redeemed."""
        self._owner(redemption)
        exact_number(redemption.saved, 2)
        return await self._conn.fetchval(
            'INSERT INTO redemptions(id,user_id,reward_id,merchant_name,description,saved,redeemed_at) '
            'VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT DO NOTHING RETURNING id',
            redemption.id, self.user_id, redemption.reward_id, redemption.merchant_name,
            redemption.description, redemption.saved, utc(redemption.redeemed_at)) is not None

    async def get_redemption_for_reward(self, reward_id):
        from backend.decisions.savings.schemas import Redemption
        row = await self._conn.fetchrow(
            'SELECT * FROM redemptions WHERE user_id=$1 AND reward_id=$2', self.user_id, reward_id)
        return Redemption.model_validate(dict(row)) if row else None

    async def list_redemptions(self):
        """Newest first, for GET /savings items."""
        from backend.decisions.savings.schemas import Redemption
        rows = await self._conn.fetch(
            'SELECT * FROM redemptions WHERE user_id=$1 ORDER BY redeemed_at DESC, id', self.user_id)
        return [Redemption.model_validate(dict(row)) for row in rows]

    async def save_merchant(self, merchant: Merchant, embedding=None):
        normalized = merchant.model_copy(update={'domain': canonical_domain(merchant.domain)})
        extras = {'embedding': vector_literal(embedding)} if embedding is not None else {}
        return await self._insert('merchants', normalized, extras=extras)

    async def resolve_merchant(self, merchant_id=None, domain=None):
        by_id = await self._conn.fetchrow('SELECT * FROM merchants WHERE id=$1', merchant_id) if merchant_id else None
        by_domain = None
        if domain:
            host = canonical_domain(domain)
            rows = await self._conn.fetch('SELECT * FROM merchants WHERE domain=$1 OR $1=ANY(aliases)', host)
            if len(rows) > 1:
                raise ValueError('Ambiguous merchant domain')
            by_domain = rows[0] if rows else None
        if merchant_id and domain and (by_id is None or by_domain is None or by_id['id'] != by_domain['id']):
            raise ValueError('Merchant ID and domain disagree')
        row = by_id if merchant_id else by_domain
        return Merchant.model_validate(dict(row)) if row else None

    async def add_card(self, card: Card):
        self._owner(card)
        exact_number(card.base_rate, 6, maximum=100)
        for rate in card.category_rates:
            exact_number(rate.rate, 6, maximum=100)
            if any(len(code) != 4 or not code.isdigit() for code in rate.mcc_codes):
                raise ValueError('MCC must have four digits')
        # Existing contract has last_four, but foundation never stores number data.
        return await self._insert('cards', card.model_copy(update={'last_four': None}))

    async def add_membership(self, membership: Membership):
        self._owner(membership)
        if membership.annual_reward_rate is not None:
            exact_number(membership.annual_reward_rate, 6, maximum=100)
        return await self._insert('memberships', membership, secret='member_id')

    async def remove_card(self, card_id):
        return await self._conn.fetchval('DELETE FROM cards WHERE user_id=$1 AND id=$2 RETURNING id', self.user_id, card_id) is not None

    async def remove_membership(self, membership_id):
        return await self._conn.fetchval('DELETE FROM memberships WHERE user_id=$1 AND id=$2 RETURNING id', self.user_id, membership_id) is not None

    async def get_wallet(self, now=None):
        now = utc(now)
        rows = await self._conn.fetch('SELECT * FROM cards WHERE user_id=$1 ORDER BY created_at,id', self.user_id)
        cards = [Card.model_validate({**dict(row), 'category_rates': json.loads(row['category_rates'])}) for row in rows]
        rows = await self._conn.fetch('SELECT *,pgp_sym_decrypt(member_id_encrypted,$2) AS member_id FROM memberships WHERE user_id=$1 ORDER BY created_at,id', self.user_id, self._key)
        memberships = [Membership.model_validate(dict(row)) for row in rows]
        counts = await self._conn.fetchrow(f'SELECT count(*) AS active,count(*) FILTER(WHERE expires_at <= $3) AS expiring FROM rewards WHERE user_id=$1 AND {ELIGIBLE}', self.user_id, now, now + timedelta(days=3))
        return Wallet(user_id=self.user_id, cards=cards, memberships=memberships,
                      active_rewards_count=counts['active'], expiring_soon_count=counts['expiring'])
