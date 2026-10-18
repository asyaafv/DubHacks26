"""Component tests against real PostgreSQL transactions and real HTTP streaming."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import socket
import statistics
import sys
import time
from uuid import uuid4

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
import httpx
import pytest
import pytest_asyncio
import uvicorn

from backend.decisions.delivery import router, startup, shutdown
from backend.decisions.delivery.service import Settings, cursor_id, parse_cursor
from backend.decisions.jobs.expire import run_expiration
from backend.tests.test_storage_wallet import db, reward, card, membership


@pytest_asyncio.fixture
async def server(db):
    app = FastAPI()
    app.include_router(router)
    app.state.database = db
    await startup(app, Settings(poll_seconds=.02, heartbeat_seconds=.05))
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(128)
    config = uvicorn.Config(app, log_level='error', lifespan='off')
    running = uvicorn.Server(config)
    task = asyncio.create_task(running.serve(sockets=[sock]))
    try:
        for _ in range(200):
            if running.started:
                break
            if task.done():
                await task
            await asyncio.sleep(.01)
        assert running.started
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{sock.getsockname()[1]}', timeout=5) as client:
            yield client, app
    finally:
        await shutdown(app)
        running.should_exit = True
        await asyncio.wait_for(task, 5)
        sock.close()


@asynccontextmanager
async def listening(client, user, last=None):
    queue = asyncio.Queue()
    headers = {'X-User-Id': str(user)}
    if last:
        headers['Last-Event-ID'] = last
    async with client.stream('GET', '/events', headers=headers) as response:
        assert response.status_code == 200
        assert response.headers['content-type'].startswith('text/event-stream')
        assert response.headers['x-accel-buffering'] == 'no'
        assert response.headers['cache-control'] == 'no-cache, no-transform'

        async def read():
            frame = {}
            async for line in response.aiter_lines():
                if not line:
                    if 'data' in frame:
                        await queue.put((frame['id'], json.loads(frame['data'])))
                    elif 'heartbeat' in frame:
                        await queue.put(('heartbeat', None))
                    frame = {}
                elif line.startswith(': heartbeat'):
                    frame['heartbeat'] = True
                elif ': ' in line:
                    key, value = line.split(': ', 1)
                    frame[key] = value
        task = asyncio.create_task(read())
        try:
            yield queue
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


async def next_data(queue, kind=None):
    while True:
        event_id, data = await asyncio.wait_for(queue.get(), 4)
        if data and (kind is None or data['event_type'] == kind):
            return event_id, data


@pytest.mark.asyncio
async def test_committed_delivery_two_clients_rollback_and_isolation(db, server):
    client, app = server
    user, other = uuid4(), uuid4()
    async with listening(client, user) as one, listening(client, user) as two, listening(client, other) as foreign:
        await next_data(one, 'sync_complete')
        await next_data(two, 'sync_complete')
        await next_data(foreign, 'sync_complete')
        r = reward(user)
        async with db.transaction(user) as repo:
            await repo.save_reward(r)
            # A reader blocked on the owner lock cannot expose uncommitted data.
            await asyncio.sleep(.08)
            assert one.empty() and two.empty()
        (id1, data1), (id2, data2) = await asyncio.gather(next_data(one, 'reward_added'), next_data(two, 'reward_added'))
        assert id1 == id2 and data1 == data2
        assert data1['reward_id'] == str(r.id)
        assert r.code not in json.dumps(data1)
        with pytest.raises(RuntimeError):
            async with db.transaction(user) as repo:
                await repo.save_reward(reward(user))
                raise RuntimeError('Rollback extraction')
        await asyncio.sleep(.08)
        async with db.transaction(user) as repo:
            assert len(await repo.list_events()) == 1
        assert not any(data for _, data in list(foreign._queue))
        assert not any(data for _, data in list(one._queue))
    for _ in range(50):
        if not app.state.delivery.clients:
            break
        await asyncio.sleep(.01)
    assert not app.state.delivery.clients


@pytest.mark.asyncio
async def test_reconnect_replay_catchup_boundary_and_heartbeat(db, server):
    client, app = server
    user = uuid4()
    # A tiny page exercises the transition between catch-up pages and live reads.
    app.state.delivery.settings = Settings(batch_size=1, poll_seconds=.02, heartbeat_seconds=.03)
    r1, r2, r3 = [reward(user) for _ in range(3)]
    async with db.transaction(user) as repo:
        await repo.save_reward(r1)
    async with listening(client, user) as queue:
        last, event = await next_data(queue, 'reward_added')
        assert event['reward_id'] == str(r1.id)
    async with db.transaction(user) as repo:
        await repo.save_reward(r2)
    async with listening(client, user, last) as queue:
        replay, event = await next_data(queue)
        assert event['reward_id'] == str(r2.id) and replay != last
        # Commit while initial replay is being drained. Same sequence query is
        # used for both phases, with no subscription/catch-up switch.
        async with db.transaction(user) as repo:
            await repo.save_reward(r3)
        _, event = await next_data(queue, 'reward_added')
        assert event['reward_id'] == str(r3.id)
        while True:
            tag, data = await asyncio.wait_for(queue.get(), 2)
            if tag == 'heartbeat':
                break
            assert data['event_type'] == 'sync_complete'
    invalid = await client.get('/events', headers={'X-User-Id': str(uuid4()), 'Last-Event-ID': last})
    assert invalid.status_code == 400


@pytest.mark.asyncio
async def test_measured_default_poll_latency(db, server, record_property):
    client, app = server
    app.state.delivery.settings = Settings()  # Actual production defaults.
    user = uuid4()
    latencies = []
    async with listening(client, user) as queue:
        await next_data(queue, 'sync_complete')
        for _ in range(3):
            async with db.transaction(user) as repo:
                r = reward(user)
                await repo.save_reward(r)
            committed = time.perf_counter()
            _, data = await next_data(queue, 'reward_added')
            latencies.append(time.perf_counter() - committed)
            assert data['reward_id'] == str(r.id)
    assert max(latencies) < 3
    measured = f'median={statistics.median(latencies):.4f}s max={max(latencies):.4f}s n={len(latencies)}'
    record_property('commit_to_http_event_latency', measured)
    print('\nDEFAULT_DELIVERY_LATENCY ' + measured)


@pytest.mark.asyncio
async def test_sync_offline_status_wallet_removals_old_timestamps_and_equal_boundary(db, server):
    client, _ = server
    user, other = uuid4(), uuid4()
    headers = {'X-User-Id': str(user)}
    r, c, m = reward(user), card(user), membership(user)
    async with db.transaction(user) as repo:
        await repo.save_reward(r)
        await repo.add_card(c)
        await repo.add_membership(m)
    initial = await client.get('/sync', headers=headers)
    assert initial.status_code == 200
    since = initial.json()['last_sync']
    initial_cursor = initial.headers['x-event-cursor']
    assert initial.json()['wallet']['cards']
    old = reward(user, updated_at=datetime(2000, 1, 1, tzinfo=timezone.utc))
    async with db.transaction(user) as repo:
        await repo.set_reward_status(r.id, 'used')
        await repo.save_reward(old)
        await repo.remove_card(c.id)
        await repo.remove_membership(m.id)
    delta = await client.get('/sync', headers=headers, params={'since': since})
    assert delta.status_code == 200, delta.text
    rows = {row['id']: row for row in delta.json()['rewards']}
    assert rows[str(r.id)]['status'] == 'used'
    assert str(old.id) in rows  # recovered through outbox despite an old row timestamp
    assert delta.json()['wallet']['cards'] == delta.json()['wallet']['memberships'] == []
    assert {e['event_type'] for e in delta.json()['pending_events']} == {'reward_added', 'reward_used'}
    assert all(e['user_id'] == str(user) for e in delta.json()['pending_events'])
    async with listening(client, user, initial_cursor) as queue:
        assert (await next_data(queue, 'reward_used'))[1]['reward_id'] == str(r.id)
        assert (await next_data(queue, 'reward_added'))[1]['reward_id'] == str(old.id)
    foreign = await client.get('/sync', headers={'X-User-Id': str(other)}, params={'since': since})
    assert foreign.json()['rewards'] == foreign.json()['pending_events'] == []
    # Inclusive equal-timestamp boundaries intentionally replay idempotent upserts.
    async with db.transaction(user) as repo:
        event_time = (await repo.list_events())[-1].event.timestamp
    equal = await client.get('/sync', headers=headers, params={'since': event_time.isoformat()})
    assert any(e['reward_id'] == str(old.id) for e in equal.json()['pending_events'])
    future = await client.get('/sync', headers=headers, params={'since': '2099-01-01T00:00:00Z'})
    assert future.status_code == 400


@pytest.mark.asyncio
async def test_sync_serializes_writes_with_watermark_and_time_only_expiry(db, server):
    client, _ = server
    user = uuid4()
    expiry = datetime.now(timezone.utc) + timedelta(seconds=.15)
    r = reward(user, expires_at=expiry)
    async with db.transaction(user) as repo:
        await repo.save_reward(r)
    first = await client.get('/sync', headers={'X-User-Id': str(user)})
    assert first.json()['rewards'][0]['status'] == 'active'
    await asyncio.sleep(.2)
    delta = await client.get('/sync', headers={'X-User-Id': str(user)}, params={'since': first.json()['last_sync']})
    assert delta.json()['rewards'][0]['status'] == 'expired'
    assert delta.json()['wallet']['active_rewards_count'] == 0
    async with db.transaction(user) as repo:
        assert not await repo.list_rewards(now=expiry)  # API eligibility excludes exact boundary before job.
        assert (await repo.get_reward(r.id)).status == 'active'  # projection does not mutate storage
        pending = asyncio.create_task(client.get('/sync', headers={'X-User-Id': str(user)}))
        added = reward(user)
        await repo.save_reward(added)
        await asyncio.sleep(.03)
        assert not pending.done()
    snapshot = await pending
    assert str(added.id) in {row['id'] for row in snapshot.json()['rewards']}


@pytest.mark.asyncio
async def test_job_boundaries_repeat_overlap_paging_and_offline_visibility(db, server):
    client, _ = server
    user = uuid4()
    now = datetime.now(timezone.utc)
    async with db.transaction(user) as repo:
        rows = [reward(user, expires_at=now - timedelta(microseconds=1)),
                reward(user, expires_at=now), reward(user, expires_at=now + timedelta(hours=24)),
                reward(user, expires_at=now + timedelta(hours=24, microseconds=1)),
                reward(user, expires_at=now + timedelta(hours=1), status='used'),
                reward(user, expires_at=now + timedelta(hours=1), starts_at=now + timedelta(minutes=5))]
        for row in rows:
            await repo.save_reward(row)
    baseline = await client.get('/sync', headers={'X-User-Id': str(user)})
    a, b = await asyncio.gather(*[run_expiration(db, clock=lambda: now, batch_size=1) for _ in range(2)])
    assert a.expired + b.expired == 2
    assert a.alerts + b.alerts == 1
    repeated = await run_expiration(db, clock=lambda: now, batch_size=2)
    assert repeated.expired == repeated.alerts == 0
    async with db.transaction(user) as repo:
        events = await repo.list_events()
        assert len([e for e in events if e.event.event_type == 'reward_updated']) == 2
        assert len([e for e in events if e.event.event_type == 'reward_expiring']) == 1
        assert [e.event.reward_id for e in events if e.event.event_type == 'reward_expiring'] == [rows[2].id]
        assert (await repo.get_reward(rows[3].id)).status == 'active'
        assert (await repo.get_reward(rows[4].id)).status == 'used'
    delta = await client.get('/sync', headers={'X-User-Id': str(user)}, params={'since': baseline.json()['last_sync']})
    assert len([r for r in delta.json()['rewards'] if r['status'] == 'expired']) == 2
    assert len([e for e in delta.json()['pending_events'] if e['event_type'] == 'reward_expiring']) == 1


@pytest.mark.asyncio
async def test_capacity_shutdown_bad_identity_and_history_bound(db, server, monkeypatch):
    client, app = server
    app.state.delivery.settings = Settings(max_clients_per_user=1, max_sync_events=1, batch_size=1, poll_seconds=.02)
    user = uuid4()
    monkeypatch.delenv('PERK_ALLOW_DEMO_IDENTITY', raising=False)
    assert (await client.get('/events')).status_code == 401
    assert (await client.get('/sync', headers={'X-User-Id': 'invalid'})).status_code == 400
    headers = {'X-User-Id': str(user)}
    async with listening(client, user) as queue:
        await next_data(queue, 'sync_complete')
        assert (await client.get('/events', headers=headers)).status_code == 429
        for _ in range(2):
            async with db.transaction(user) as repo:
                await repo.save_reward(reward(user))
        response = await client.get('/sync', headers=headers, params={'since': '2000-01-01T00:00:00Z'})
        assert response.status_code == 409
        assert (await client.get('/sync', headers=headers)).status_code == 200
        await shutdown(app)
        await asyncio.sleep(.05)
        assert (await client.get('/events', headers=headers)).status_code == 503
    assert not app.state.delivery.clients


@pytest.mark.asyncio
async def test_job_rollback_and_configurable_window_dedupe(db, monkeypatch):
    from backend.decisions.storage.repository import Repository
    user = uuid4()
    now = datetime.now(timezone.utc)
    overdue = reward(user, expires_at=now)
    soon = reward(user, expires_at=now + timedelta(hours=1))
    async with db.transaction(user) as repo:
        await repo.save_reward(overdue)
        await repo.save_reward(soon)
    original = Repository.append_event

    async def fail_event(self, event_type, *args, **kwargs):
        if event_type == 'reward_updated':
            raise RuntimeError('Simulated event persistence failure')
        return await original(self, event_type, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Repository, 'append_event', fail_event)
        with pytest.raises(RuntimeError):
            await run_expiration(db, clock=lambda: now)
    async with db.transaction(user) as repo:
        assert (await repo.get_reward(overdue.id)).status == 'active'
        assert all(row.event.event_type == 'reward_added' for row in await repo.list_events())
    first = await run_expiration(db, clock=lambda: now, window=timedelta(hours=2))
    assert first.expired == first.alerts == 1
    repeated = await run_expiration(db, clock=lambda: now, window=timedelta(hours=2))
    assert repeated.expired == repeated.alerts == 0
    changed_window = await run_expiration(db, clock=lambda: now, window=timedelta(hours=3))
    assert changed_window.expired == 0 and changed_window.alerts == 1


@pytest.mark.asyncio
async def test_stream_lifetime_and_prefetch_timeout_release_capacity(db, server):
    client, app = server
    user = uuid4()
    headers = {'X-User-Id': str(user)}
    app.state.delivery.settings = Settings(poll_seconds=.01, max_stream_seconds=.05, query_timeout_seconds=.03)
    # A legitimate concurrent writer can exceed the query deadline. Return a
    # retryable status before streaming headers, without leaking the reservation.
    async with db.transaction(user):
        response = await client.get('/events', headers=headers)
        assert response.status_code == 503
        assert not app.state.delivery.clients
    response = await client.get('/events', headers=headers)
    assert response.status_code == 200 and 'sync_complete' in response.text
    assert not app.state.delivery.clients
    future = await client.get('/events', headers={**headers, 'Last-Event-ID': cursor_id(user, 999)})
    assert future.status_code == 400
    assert not app.state.delivery.clients


@pytest.mark.asyncio
async def test_scheduling_command_runs_once_and_reruns_safely(db):
    user = uuid4()
    async with db.transaction(user) as repo:
        await repo.save_reward(reward(user, expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    # asyncpg accepts server settings in the DSN; restrict the CLI to this test schema.
    separator = '&' if '?' in db.test_url else '?'
    env = {**os.environ, 'DATABASE_URL': db.test_url + separator + 'search_path=' + db.test_schema + ',public',
           'PERK_ENCRYPTION_KEY': db._key}
    results = []
    for _ in range(2):
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-m', 'backend.decisions.jobs.expire', '--window-hours', '24', '--batch-size', '1',
            env=env, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        output, error = await asyncio.wait_for(process.communicate(), 10)
        assert process.returncode == 0, error.decode()
        results.append(json.loads(output))
    assert results[0]['expired'] == 1
    assert results[1]['expired'] == results[1]['alerts'] == 0


def test_cursor_validation():
    user = uuid4()
    assert parse_cursor(None, user) == 0
    assert parse_cursor(cursor_id(user, 123), user) == 123
    for invalid in ('1', f'{user}:-1', f'{user}:01', f'{user}:9223372036854775808', 'bad\nheader'):
        with pytest.raises(Exception) as error:
            parse_cursor(invalid, user)
        assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_browser_fetch_streaming(db, server, monkeypatch):
    """Optional tooling, real Chromium, actual example module and HTTP route."""
    node = os.getenv('NODE_BINARY')
    if not node or not os.getenv('PLAYWRIGHT_NODE_MODULE'):
        pytest.skip('Set NODE_BINARY and PLAYWRIGHT_NODE_MODULE for real Chromium test')
    monkeypatch.delenv('PERK_ALLOW_DEMO_IDENTITY', raising=False)
    client, app = server

    @app.get('/browser-test')
    async def shell():
        return HTMLResponse('<!doctype html><title>Delivery component test</title>')

    @app.get('/fetch-events.mjs')
    async def example():
        return FileResponse(Path(__file__).parents[1] / 'decisions/delivery/fetch-events.mjs',
                            media_type='text/javascript')

    requests = []

    @app.middleware('http')
    async def observe(request, call_next):
        if request.url.path == '/events':
            requests.append(dict(request.headers))
        return await call_next(request)

    # Starlette freezes middleware after startup; rebuild only in this test fixture.
    app.middleware_stack = app.build_middleware_stack()
    user = uuid4()
    first, replay, live = [reward(user) for _ in range(3)]
    async with db.transaction(user) as repo:
        await repo.save_reward(first)
        await repo.save_reward(replay)
        cursor = cursor_id(user, (await repo.list_events())[0].sequence)
    process = await asyncio.create_subprocess_exec(
        node, str(Path(__file__).with_name('browser_delivery.cjs')), str(client.base_url).rstrip('/'),
        str(user), cursor, str(replay.id), str(live.id),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        ready = await asyncio.wait_for(process.stdout.readline(), 15)
        assert ready == b'READY\n', ready
        async with db.transaction(user) as repo:
            await repo.save_reward(live)
        output, error = await asyncio.wait_for(process.communicate(), 15)
        assert process.returncode == 0, error.decode()
        print('\nBROWSER_VERIFICATION ' + output.decode().strip())
        assert 'x-user-id' not in requests[0]
        assert requests[1]['x-user-id'] == str(user)
        assert requests[1]['last-event-id'] == cursor
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()
