"""No process-local event queue: every stream page comes from the durable outbox."""
import asyncio
from collections import Counter
from dataclasses import dataclass
import re

from asyncpg import PostgresError

from fastapi import HTTPException

from backend.app.schemas import Event, EventType, RewardStatus, SyncResponse
from backend.decisions.common import utc


@dataclass(frozen=True)
class Settings:
    poll_seconds: float = 1.0
    heartbeat_seconds: float = 15.0
    max_stream_seconds: float = 600.0
    query_timeout_seconds: float = 5.0
    batch_size: int = 100
    max_clients: int = 128
    max_clients_per_user: int = 8
    max_sync_events: int = 10000

    def __post_init__(self):
        if any(value <= 0 for value in vars(self).values()):
            raise ValueError('Delivery limits must be positive')
        if self.batch_size > 1000:
            raise ValueError('Repository batch limit is 1000')


class Runtime:
    def __init__(self, settings=None):
        self.settings = settings or Settings()
        self.stopping = asyncio.Event()
        self.clients = Counter()

    def reserve(self, user):
        if self.stopping.is_set():
            raise HTTPException(503, 'Delivery is shutting down')
        if sum(self.clients.values()) >= self.settings.max_clients or self.clients[user] >= self.settings.max_clients_per_user:
            raise HTTPException(429, 'Stream capacity reached', headers={'Retry-After': '5'})
        self.clients[user] += 1

    def release(self, user):
        self.clients[user] -= 1
        if self.clients[user] <= 0:
            del self.clients[user]


async def startup(app, settings=None):
    """Call once in integration lifespan, after app.state.database is configured."""
    app.state.delivery = Runtime(settings)


async def shutdown(app):
    """Wake all streams; no scheduler or listener connection to tear down."""
    runtime = getattr(app.state, 'delivery', None)
    if runtime:
        runtime.stopping.set()


def cursor_id(user, sequence):
    return f'{user}:{sequence}'


def parse_cursor(value, user):
    if value is None:
        return 0
    match = re.fullmatch(re.escape(str(user)) + r':(0|[1-9][0-9]{0,18})', value)
    if not match or int(match[1]) > 9223372036854775807:
        raise HTTPException(400, 'Invalid Last-Event-ID for this user')
    return int(match[1])


def format_sse(event, event_id):
    return f'id: {event_id}\nevent: {event.event_type.value}\ndata: {event.model_dump_json()}\n\n'


async def read_page(database, user, after, settings, validate_cursor=False):
    async def read():
        async with database.transaction(user) as repo:
            if validate_cursor and after > await repo.event_watermark():
                raise HTTPException(400, 'Last-Event-ID is ahead of stored history')
            return await repo.list_events(after=after, limit=settings.batch_size)
    return await asyncio.wait_for(read(), timeout=settings.query_timeout_seconds)


async def stream(request, database, user, after, runtime, first_page):
    settings = runtime.settings
    loop = asyncio.get_running_loop()
    started = last_heartbeat = loop.time()
    caught_up = False
    page = first_page
    try:
        yield 'retry: 1000\n\n'
        while not runtime.stopping.is_set():
            if await request.is_disconnected() or loop.time() - started >= settings.max_stream_seconds:
                return
            for stored in page:
                # Each connection owns its cursor. Never set events.delivered.
                yield format_sse(stored.event, cursor_id(user, stored.sequence))
                after = stored.sequence
            if len(page) < settings.batch_size:
                if not caught_up:
                    yield format_sse(Event(event_type=EventType.sync_complete, user_id=user,
                                           timestamp=utc(), data={'message': 'Connected'}), cursor_id(user, after))
                    caught_up = True
                if loop.time() - last_heartbeat >= settings.heartbeat_seconds:
                    yield ': heartbeat\n\n'
                    last_heartbeat = loop.time()
                try:
                    await asyncio.wait_for(runtime.stopping.wait(), timeout=settings.poll_seconds)
                except asyncio.TimeoutError:
                    pass
                if runtime.stopping.is_set():
                    return
            # No DB connection or owner lock is held while yielding or waiting.
            page = await read_page(database, user, after, settings)
    except (asyncio.TimeoutError, OSError, PostgresError):
        # A dropped response reconnects at the last *applied* ID; no cursor advances.
        return
    finally:
        runtime.release(user)


async def sync_snapshot(database, user, since, settings):
    async with database.transaction(user) as repo:
        # The owner lock excludes concurrent writers for the entire snapshot.
        watermark = await repo.snapshot_time()
        if since is not None and since > watermark:
            raise HTTPException(400, 'since must not be in the future')
        sequence = await repo.event_watermark()
        rewards = {r.id: r for r in await repo.list_rewards(eligible_only=False, since=since)}
        events = []
        if since is not None:
            after = 0
            while True:
                page = await repo.list_events_since(since, after=after, limit=settings.batch_size)
                if len(events) + len(page) > settings.max_sync_events:
                    raise HTTPException(409, 'Sync history too large; request a full snapshot without since')
                events.extend(row.event for row in page)
                for row in page:
                    if row.event.reward_id and row.event.reward_id not in rewards:
                        reward = await repo.get_reward(row.event.reward_id)
                        if reward:
                            rewards[reward.id] = reward
                if len(page) < settings.batch_size:
                    break
                after = page[-1].sequence
        # Time alone can expire a reward without updating its row or running the job.
        # Include such transitions in deltas, and project the effective status only.
        for reward in await repo.list_rewards(eligible_only=False):
            if reward.status == 'active' and reward.expires_at and utc(reward.expires_at) <= watermark:
                if since is None or utc(reward.expires_at) >= since or reward.id in rewards:
                    rewards[reward.id] = reward.model_copy(update={'status': RewardStatus.expired})
        wallet = await repo.get_wallet(now=watermark)
        return SyncResponse(user_id=user, rewards=list(rewards.values()), wallet=wallet,
                            last_sync=watermark, pending_events=events), cursor_id(user, sequence)
