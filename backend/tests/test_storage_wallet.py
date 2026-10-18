"""Real-Postgres integration tests; no SQLite or mocked encryption path."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
import secrets
from uuid import uuid4, UUID

import asyncpg
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException

from backend.app.schemas import Card, Membership, Reward, RewardStatus, Merchant, EventType
from backend.decisions.common import card_rate, resolve_user, vector_literal, DEMO_USER_ID
from backend.decisions.storage import Database
from backend.decisions.storage.seed import seed
from backend.decisions.wallet.router import router

NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db():
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('TEST_DATABASE_URL is required for real Postgres tests')
    schema = 'test_perk_' + uuid4().hex
    admin = await asyncpg.connect(url)
    for extension in ('pgcrypto', 'vector', 'uuid-ossp'):
        await admin.execute(f'CREATE EXTENSION IF NOT EXISTS "{extension}" WITH SCHEMA public')
    await admin.execute(f'CREATE SCHEMA {schema}')
    pool = await asyncpg.create_pool(url, min_size=1, max_size=5,
                                   server_settings={'search_path': schema + ',public', 'timezone': 'UTC'})
    database = Database(pool, secrets.token_hex(32))
    database.test_url = url
    database.test_schema = schema
    try:
        await database.migrate()
        yield database
    finally:
        await database.close()
        await admin.execute(f'DROP SCHEMA {schema} CASCADE')
        await admin.close()


def reward(owner, **updates):
    data = dict(id=uuid4(), user_id=owner, merchant_name='Shop', category='Clothing',
                mcc='5651', kind='percent_off', value='10.00', source='manual',
                code='secret-' + uuid4().hex, created_at=NOW, updated_at=NOW)
    data.update(updates)
    return Reward(**data)


def card(owner):
    return Card(id=uuid4(), user_id=owner, issuer='Bank', network='visa', name='Product',
                base_rate='1.5', category_rates=[{'category': 'Clothing', 'mcc_codes': ['5651'], 'rate': '5'}])


def membership(owner):
    return Membership(id=uuid4(), user_id=owner, merchant_name='Shop', program_name='Club', member_id='private-' + uuid4().hex)


@pytest.mark.asyncio
async def test_encryption_scoping_and_atomic_status(db):
    owner, other = uuid4(), uuid4()
    r, c, m = reward(owner), card(owner), membership(owner)
    async with db.transaction(owner) as repo:
        assert await repo.save_reward(r, embedding=[1.] * 384)
        assert await repo.add_card(c)
        assert await repo.add_membership(m)
        assert (await repo.get_reward(r.id)).code is None
        assert [x.id for x in await repo.search_rewards([1.] * 384, now=NOW)] == [r.id]
        assert (await repo.get_reward(r.id, reveal_code=True)).code == r.code
        assert (await repo.get_wallet()).memberships[0].member_id == m.member_id
        row = await repo._conn.fetchrow('SELECT code_encrypted FROM rewards WHERE user_id=$1 AND id=$2', owner, r.id)
        assert r.code.encode() not in bytes(row['code_encrypted'])
        cipher = await repo._conn.fetchval('SELECT member_id_encrypted FROM memberships WHERE user_id=$1 AND id=$2', owner, m.id)
        assert m.member_id.encode() not in bytes(cipher)
    async with db.transaction(other) as repo:
        assert await repo.get_reward(r.id, reveal_code=True) is None
        assert not await repo.list_rewards(eligible_only=False)
        assert not await repo.search_rewards([1.] * 384, now=NOW)
        assert not await repo.list_events()
        assert not await repo.remove_card(c.id)
        assert not await repo.remove_membership(m.id)
        assert not await repo.set_reward_status(r.id, 'used')
        assert not (await repo.get_wallet()).cards
        with pytest.raises(ValueError):
            await repo.save_reward(r)
        with pytest.raises(ValueError):
            await repo.append_event('reward_updated', r.id)
    async with db.transaction(owner) as repo:
        assert await repo.set_reward_status(r.id, 'used')
        assert not await repo.set_reward_status(r.id, 'used')
        assert not await repo.list_rewards(now=NOW)
        assert (await repo.list_rewards(eligible_only=False, since=NOW))[0].status == RewardStatus.used
        events = await repo.list_events()
        assert [row.event.event_type for row in events] == [EventType.reward_added, EventType.reward_used]
        assert [row.sequence for row in events] == sorted(row.sequence for row in events)
        assert r.code not in str(events) and m.member_id not in str(events)
        assert await repo.list_events(after=events[-1].sequence) == []


@pytest.mark.asyncio
async def test_rollback_hides_email_reward_and_event(db):
    owner = uuid4()
    r = reward(owner)
    with pytest.raises(RuntimeError):
        async with db.transaction(owner) as repo:
            assert await repo.claim_email('same-message', 'reward')
            assert await repo.save_reward(r)
            raise RuntimeError('rollback')
    async with db.transaction(owner) as repo:
        assert await repo.get_reward(r.id, reveal_code=True) is None
        assert not await repo.list_events()
        assert await repo.claim_email('same-message', 'reward')


@pytest.mark.asyncio
async def test_per_user_deduplication_and_alert_dedupe(db):
    owner, other = uuid4(), uuid4()
    r = reward(owner)
    async with db.transaction(owner) as repo:
        assert await repo.claim_email('same', 'reward', content_hash='digest')
        assert not await repo.claim_email('same', 'reward')
        assert not await repo.claim_email('different', 'reward', content_hash='digest')
        assert await repo.set_email_result('same', 'reward', 1)
        assert await repo.save_reward(r, dedupe_key='offer-digest')
        assert not await repo.save_reward(reward(owner), dedupe_key='offer-digest')
        assert not await repo.save_reward(r)
        assert await repo.append_event('reward_expiring', r.id, dedupe_key='expiry-version-1')
        assert not await repo.append_event('reward_expiring', r.id, dedupe_key='expiry-version-1')
        assert len(await repo.list_events()) == 2
    async with db.transaction(other) as repo:
        assert await repo.claim_email('same', 'reward', content_hash='digest')
        assert await repo.save_reward(reward(other), dedupe_key='offer-digest')


@pytest.mark.asyncio
async def test_counts_query_time_eligibility_and_precision(db):
    owner = uuid4()
    async with db.transaction(owner) as repo:
        rows = [reward(owner), reward(owner, expires_at=NOW + timedelta(days=3)),
                reward(owner, expires_at=NOW), reward(owner, starts_at=NOW + timedelta(seconds=1)),
                reward(owner, status='used'), reward(owner, status='expired'), reward(owner, status='needs_review')]
        for r in rows:
            await repo.save_reward(r)
        wallet = await repo.get_wallet(now=NOW)
        assert wallet.active_rewards_count == 2
        assert wallet.expiring_soon_count == 1
        assert len(await repo.list_rewards(now=NOW)) == 2
        assert len(await repo.list_rewards(eligible_only=False)) == 7
        with pytest.raises(ValueError):
            await repo.save_reward(reward(owner, min_spend='1.001'))
        with pytest.raises(ValueError):
            await repo.save_reward(reward(owner, value='-1'))


@pytest.mark.asyncio
async def test_reconnect_retains_wallet_and_seed_never_restores_changes(db):
    await seed(db)
    async with db.transaction(DEMO_USER_ID) as repo:
        wallet = await repo.get_wallet(now=NOW)
        assert wallet.cards and wallet.memberships
        removed = wallet.cards[0].id
        await repo.remove_card(removed)
        r = (await repo.list_rewards(now=NOW))[0]
        original_code = (await repo.get_reward(r.id, reveal_code=True)).code
        await repo.set_reward_status(r.id, 'used')
    await db.pool.close()
    db.pool = await asyncpg.create_pool(db.test_url, min_size=1, max_size=5,
        server_settings={'search_path': db.test_schema + ',public', 'timezone': 'UTC'})
    await db.migrate()  # idempotent and no reset
    await seed(db)
    async with db.transaction(DEMO_USER_ID) as repo:
        assert removed not in [c.id for c in (await repo.get_wallet()).cards]
        assert (await repo.get_reward(r.id)).status == RewardStatus.used
        assert (await repo.get_reward(r.id, reveal_code=True)).code == original_code


@pytest.mark.asyncio
async def test_uncommitted_events_invisible_and_replay_commit_order(db):
    owner = uuid4()
    r1, r2 = reward(owner), reward(owner)
    first_written, release = asyncio.Event(), asyncio.Event()

    async def first():
        async with db.transaction(owner) as repo:
            await repo.save_reward(r1)
            first_written.set()
            await release.wait()

    async def second():
        await first_written.wait()
        async with db.transaction(owner) as repo:
            await repo.save_reward(r2)

    a, b = asyncio.create_task(first()), asyncio.create_task(second())
    try:
        await asyncio.wait_for(first_written.wait(), 3)
        async with db.pool.acquire() as observer:
            assert not await observer.fetch('SELECT * FROM events WHERE user_id=$1', owner)
        # A later writer must block until the first transaction commits.
        done, _ = await asyncio.wait([b], timeout=0.05)
        assert not done
        release.set()
        await asyncio.wait_for(asyncio.gather(a, b), 3)
        async with db.transaction(owner) as repo:
            assert [row.event.reward_id for row in await repo.list_events()] == [r1.id, r2.id]
    finally:
        release.set()
        await asyncio.gather(a, b, return_exceptions=True)


@pytest.mark.asyncio
async def test_merchant_id_domain_agreement(db):
    m = Merchant(id=uuid4(), name='Shop', domain='WWW.Shop.test', mcc='5651', category='Clothing')
    async with db.transaction(uuid4()) as repo:
        await repo.save_merchant(m, embedding=[1.] * 384)
        assert (await repo.resolve_merchant(m.id, 'https://www.shop.test/cart')).id == m.id
        with pytest.raises(ValueError):
            await repo.resolve_merchant(m.id, 'other.test')


@pytest.mark.asyncio
async def test_wallet_http_identity_products_and_atomic_updates(db, monkeypatch):
    app = FastAPI()
    app.include_router(router)
    app.state.database = db
    owner, other = uuid4(), uuid4()
    headers = {'X-User-Id': str(owner)}
    payload = {'add_cards': [dict(issuer='Bank', network='visa', name='Product', base_rate='1.5',
                    category_rates=[dict(category='Clothing', mcc_codes=['5651'], rate='5')])],
               'add_memberships': [dict(merchant_name='Shop', program_name='Club', member_id='sensitive-id')]}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        monkeypatch.delenv('PERK_ALLOW_DEMO_IDENTITY', raising=False)
        assert (await client.get('/wallet')).status_code == 401
        assert (await client.get('/wallet', headers={'X-User-Id': 'invalid'})).status_code == 400
        assert (await client.post('/wallet', headers=headers, json={**payload, 'user_id': str(other)})).status_code == 400
        added = await client.post('/wallet', headers=headers, json=payload)
        assert added.status_code == 200, added.text
        data = added.json()
        card_id, member_id = data['cards'][0]['id'], data['memberships'][0]['id']
        assert data['cards'][0]['last_four'] is None
        assert Decimal(data['cards'][0]['category_rates'][0]['rate']) == 5
        assert data['memberships'][0]['member_id'] == 'sensitive-id'
        assert not (await client.get('/wallet', headers={'X-User-Id': str(other)})).json()['cards']
        await client.post('/wallet', headers={'X-User-Id': str(other)}, json={'remove_card_ids': [card_id], 'remove_membership_ids': [member_id]})
        assert len((await client.get('/wallet', headers=headers)).json()['cards']) == 1
        invalid = {**payload, 'add_memberships': [dict(merchant_name='Shop', program_name='Bad', annual_reward_rate='-1')]}
        assert (await client.post('/wallet', headers=headers, json=invalid)).status_code == 422
        assert len((await client.get('/wallet', headers=headers)).json()['cards']) == 1
        number_input = {'add_cards': [{**payload['add_cards'][0], 'card_number': 'unwanted'}]}
        assert (await client.post('/wallet', headers=headers, json=number_input)).status_code == 422
        removed = await client.post('/wallet', headers=headers, json={'remove_card_ids': [card_id], 'remove_membership_ids': [member_id]})
        assert removed.json()['cards'] == removed.json()['memberships'] == []
        monkeypatch.setenv('PERK_ALLOW_DEMO_IDENTITY', 'true')
        assert (await client.get('/wallet')).status_code == 200


def test_exact_card_rates_and_identity(monkeypatch):
    c = card(uuid4())
    assert card_rate(c, category='Clothing', mcc='5651') == Decimal('5')
    assert card_rate(c, category='Clothing', mcc='5411') == Decimal('1.5')
    assert card_rate(c, category='Clothing') == Decimal('1.5')
    c.category_rates[0].mcc_codes = []
    assert card_rate(c, category=' clothing ') == Decimal('5')
    assert card_rate(c, category='Unknown') == Decimal('1.5')
    monkeypatch.delenv('PERK_ALLOW_DEMO_IDENTITY', raising=False)
    with pytest.raises(HTTPException):
        resolve_user()
    with pytest.raises(HTTPException):
        resolve_user(uuid4(), uuid4())
    monkeypatch.setenv('PERK_ALLOW_DEMO_IDENTITY', 'true')
    assert resolve_user() == DEMO_USER_ID
    with pytest.raises(ValueError):
        vector_literal([1.] * 383)
    with pytest.raises(ValueError):
        vector_literal([float('nan')] * 384)
    with pytest.raises(ValueError):
        vector_literal([0.] * 384)


@pytest.mark.asyncio
async def test_wrong_key_and_foreign_event_constraint(db):
    owner, other = uuid4(), uuid4()
    r = reward(owner)
    async with db.transaction(owner) as repo:
        await repo.save_reward(r)
    wrong_key_db = Database(db.pool, secrets.token_hex(32))
    async with wrong_key_db.transaction(other) as repo:
        # Even a wrong-key session must not try decrypting another user's row.
        assert await repo.get_reward(r.id, reveal_code=True) is None
    with pytest.raises(asyncpg.PostgresError):
        async with wrong_key_db.transaction(owner) as repo:
            await repo.get_reward(r.id, reveal_code=True)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        async with db.transaction(other) as repo:
            await repo._conn.execute('INSERT INTO events(user_id,event_type,reward_id) VALUES($1,$2,$3)', other, 'reward_added', r.id)
    async with db.transaction(owner) as repo:
        assert (await repo.get_reward(r.id, reveal_code=True)).code == r.code


def test_missing_database_is_explicit():
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        assert client.get('/wallet', headers={'X-User-Id': str(uuid4())}).status_code == 503


@pytest.mark.asyncio
async def test_bounded_scheduler_registry_and_expiration_candidates(db):
    owners = [uuid4(), uuid4(), uuid4()]
    for owner in owners:
        async with db.transaction(owner):
            pass
    all_users, cursor = [], None
    while True:
        page = await db.list_user_ids(after=cursor, limit=2)
        if not page:
            break
        all_users.extend(page)
        cursor = page[-1]
    assert set(owners).issubset(all_users)
    assert all_users == sorted(set(all_users))
    assert not await db.list_user_ids(after=UUID(int=2**128 - 1))
    with pytest.raises(ValueError):
        await db.list_user_ids(limit=1001)
    owner, other = owners[:2]
    expected = [reward(owner, expires_at=NOW - timedelta(days=10)),
                reward(owner, expires_at=NOW),
                reward(owner, expires_at=NOW + timedelta(hours=24))]
    async with db.transaction(owner) as repo:
        for r in expected + [reward(owner), reward(owner, status='used', expires_at=NOW),
                              reward(owner, status='needs_review', expires_at=NOW),
                              reward(owner, expires_at=NOW + timedelta(hours=25))]:
            await repo.save_reward(r)
    async with db.transaction(other) as repo:
        await repo.save_reward(reward(other, expires_at=NOW))
    async with db.transaction(owner) as repo:
        collected, cursor = [], None
        while True:
            page = await repo.list_expiration_candidates(NOW, NOW + timedelta(hours=24), after=cursor, limit=1)
            if not page:
                break
            collected.extend(page)
            cursor = page[-1].id
            # Expiration jobs may mutate earlier pages without skipping later UUIDs.
            await repo.set_reward_status(cursor, 'expired')
        assert [r.id for r in collected] == sorted(r.id for r in expected)
        assert all(r.code is None for r in collected)
        with pytest.raises(ValueError):
            await repo.list_expiration_candidates(NOW, NOW - timedelta(seconds=1))
        with pytest.raises(ValueError):
            await repo.list_expiration_candidates(NOW, NOW, limit=0)


@pytest.mark.asyncio
async def test_database_snapshot_and_timestamp_event_replay(db):
    owner, other = uuid4(), uuid4()
    async with db.transaction(owner) as repo:
        await repo.save_reward(reward(owner))
    async with db.transaction(owner) as repo:
        watermark = await repo.snapshot_time()
        assert watermark.tzinfo is not None and watermark.utcoffset() == timedelta(0)
        old_rewards = [reward(owner, updated_at=NOW - timedelta(days=365)) for _ in range(3)]
        for r in old_rewards:
            await repo.save_reward(r)
        # Caller timestamps cannot make newly inserted durable events disappear.
        assert await repo.list_rewards(eligible_only=False, since=watermark) == []
        first = await repo.list_events_since(watermark, limit=2)
        second = await repo.list_events_since(watermark, after=first[-1].sequence, limit=2)
        events = first + second
        assert [e.event.reward_id for e in events] == [r.id for r in old_rewards]
        assert all(e.event.timestamp >= watermark for e in events)
        assert len(await repo.list_events_since(events[0].event.timestamp)) == 3
        assert not await repo.list_events_since(watermark, after=events[-1].sequence)
        with pytest.raises(ValueError):
            await repo.list_events_since(watermark, after=-1)
        with pytest.raises(ValueError):
            await repo.list_events_since(watermark, limit=0)
    async with db.transaction(other) as repo:
        assert not await repo.list_events_since(watermark)
