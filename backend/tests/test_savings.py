"""Real PostgreSQL coverage for the ledger, atomic transitions and exact contracts."""
import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI
import httpx
import pytest

from backend.app.schemas import RedeemRequest, RewardStatus
from backend.decisions.common import DEMO_USER_ID
from backend.decisions.savings.router import router
from backend.decisions.savings.seed import seed_redemptions
from backend.decisions.savings.service import calculate_savings, redeem_reward, savings_summary
from backend.decisions.storage.seed import seed
from backend.decisions.wallet.router import router as wallet_router
from backend.tests.test_storage_wallet import db, reward, NOW


def client_for(database):
    app = FastAPI()
    app.state.database = database
    app.include_router(router)
    app.include_router(wallet_router)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


@pytest.mark.asyncio
async def test_redeem_http_records_once_marks_used_and_publishes_owner_event(db):
    owner, other = uuid4(), uuid4()
    offer = reward(owner)
    async with db.transaction(owner) as repo:
        await repo.save_reward(offer)
    async with client_for(db) as client:
        headers = {'X-User-Id': str(owner)}
        foreign = {'X-User-Id': str(other)}
        url = f'/rewards/{offer.id}/redeem'
        assert (await client.post(url, headers=foreign, json={'saved': '12.50'})).status_code == 404
        responses = await asyncio.gather(*[
            client.post(url, headers=headers, json={'saved': '12.50'}) for _ in range(2)
        ])
        assert all(response.status_code == 200 for response in responses)
        assert all(response.json()['status'] == 'used' for response in responses)
        assert all(response.json()['code'] is None for response in responses)
        retried = await client.post(url, headers=headers, json={'saved': '999.00'})
        assert retried.status_code == 200
        data = (await client.get('/savings', headers=headers)).json()
        assert data['total'] == '12.50'
        assert len(data['items']) == 1 and data['items'][0]['saved'] == '12.50'
        assert (await client.get('/savings', headers=foreign)).json() == {
            'total': '0.00', 'items': [], 'series': [],
        }
    async with db.transaction(owner) as repo:
        assert (await repo.get_reward(offer.id)).status == RewardStatus.used
        used = [item for item in await repo.list_events() if item.event.event_type == 'reward_used']
        assert len(used) == 1 and used[0].event.reward_id == offer.id
        assert used[0].event.user_id == owner
        assert offer.code not in used[0].event.model_dump_json()


@pytest.mark.asyncio
async def test_summary_groups_utc_days_and_totals_every_item(db):
    owner, other = uuid4(), uuid4()
    # Two instants on the same UTC day despite different local calendar dates.
    dates = [datetime.fromisoformat('2026-09-08T01:00:00+00:00'),
             datetime.fromisoformat('2026-09-08T23:30:00-07:00'),
             datetime.fromisoformat('2026-09-09T09:00:00+00:00')]
    async with db.transaction(owner) as repo:
        for when, amount in zip(dates, ['10.00', '0.01', '12.50']):
            offer = reward(owner)
            await repo.save_reward(offer)
            await redeem_reward(repo, offer.id, RedeemRequest(saved=amount), now=when)
        summary = await savings_summary(repo)
        data = summary.model_dump(mode='json')
        assert data['total'] == '22.51'
        assert sum(Decimal(item['saved']) for item in data['items']) == Decimal(data['total'])
        assert data['series'] == [
            {'date': '2026-09-08', 'cumulative': '10.00'},
            {'date': '2026-09-09', 'cumulative': '22.51'},
        ]
        assert [item.redeemed_at for item in summary.items] == sorted(
            [item.redeemed_at for item in summary.items], reverse=True)
    async with db.transaction(other) as repo:
        assert not await repo.list_redemptions()
        assert await repo.get_redemption(offer.id) is None
        assert (await savings_summary(repo)).total == 0


@pytest.mark.asyncio
async def test_rollback_on_event_failure_leaves_no_redemption_or_used_status(db, monkeypatch):
    from backend.decisions.storage.repository import Repository
    owner = uuid4()
    offer = reward(owner)
    async with db.transaction(owner) as repo:
        await repo.save_reward(offer)
    original = Repository.append_event

    async def fail_used(self, event_type, *args, **kwargs):
        if event_type == 'reward_used':
            raise RuntimeError('Outbox failed')
        return await original(self, event_type, *args, **kwargs)

    monkeypatch.setattr(Repository, 'append_event', fail_used)
    with pytest.raises(RuntimeError):
        async with db.transaction(owner) as repo:
            await redeem_reward(repo, offer.id, RedeemRequest(saved='12.50'))
    async with db.transaction(owner) as repo:
        assert (await repo.get_reward(offer.id)).status == 'active'
        assert await repo.get_redemption(offer.id) is None
        assert len(await repo.list_events()) == 1


@pytest.mark.asyncio
async def test_fallbacks_validation_and_wallet_expiration_contract(db, monkeypatch):
    owner = uuid4()
    offers = [reward(owner), reward(owner, max_discount='12.50'), reward(owner),
              reward(owner, status='needs_review'), reward(owner, expires_at=NOW),
              reward(owner, starts_at=datetime.now(timezone.utc) + timedelta(days=1))]
    offers[0].expires_at = datetime.now(timezone.utc) + timedelta(days=2)
    offers[2].expires_at = datetime.now(timezone.utc) + timedelta(days=3)
    async with db.transaction(owner) as repo:
        for offer in offers:
            await repo.save_reward(offer)
    async with client_for(db) as client:
        headers = {'X-User-Id': str(owner)}
        first = await client.post(f'/rewards/{offers[0].id}/redeem', headers=headers)
        assert first.status_code == 200, first.text
        second = await client.post(f'/rewards/{offers[1].id}/redeem', headers=headers,
                                   json={'cart_total': '500.00'})
        assert second.status_code == 200, second.text
        for value in ['-1.00', 'NaN', 'Infinity', '0.001', '100000000.00']:
            response = await client.post(f'/rewards/{offers[2].id}/redeem', headers=headers,
                                         json={'saved': value})
            assert response.status_code == 422, (value, response.text)
        for offer in offers[3:]:
            response = await client.post(f'/rewards/{offer.id}/redeem', headers=headers,
                                         json={'saved': '1.00'})
            assert response.status_code == 409
        assert (await client.post(f'/rewards/{uuid4()}/redeem', headers=headers, json={})).status_code == 404
        monkeypatch.delenv('LAPSE_ALLOW_DEMO_IDENTITY', raising=False)
        assert (await client.get('/savings')).status_code == 401
        data = (await client.get('/savings', headers=headers)).json()
        assert data['total'] == '22.50'
        calendar = (await client.get('/wallet', headers=headers)).json()['rewards']
        assert len(calendar) == 1 and calendar[0]['id'] == str(offers[2].id)
        assert calendar[0]['code'] is None
        assert calendar[0]['expires_at'] is not None


@pytest.mark.asyncio
async def test_demo_seed_is_repeatable_exact_and_does_not_spend_live_offers(db):
    assert await seed_redemptions(db, now=NOW)
    assert not await seed_redemptions(db, now=NOW + timedelta(days=10))
    await seed(db)
    async with db.transaction(DEMO_USER_ID) as repo:
        summary = await savings_summary(repo)
        assert summary.total == Decimal('103.51')
        assert len(summary.items) == len(summary.series) == 8
        assert all(NOW - timedelta(weeks=6) <= item.redeemed_at < NOW for item in summary.items)
        assert summary.series[-1].cumulative == summary.total
        assert (await repo.get_reward(UUID('22222222-2222-2222-2222-222222222201'))).status == 'active'
        for item in summary.items:
            assert (await repo.get_reward(item.reward_id)).status == 'used'
        events_before = await repo.event_watermark()
    await seed(db)
    async with db.transaction(DEMO_USER_ID) as repo:
        assert (await savings_summary(repo)).model_dump() == summary.model_dump()
        assert await repo.event_watermark() == events_before
        assert all(offer.expires_at is not None for offer in await repo.list_rewards(now=NOW))


@pytest.mark.asyncio
async def test_redemption_foreign_key_cannot_link_another_owners_reward(db):
    import asyncpg
    owner, other = uuid4(), uuid4()
    offer = reward(owner)
    async with db.transaction(owner) as repo:
        await repo.save_reward(offer)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        async with db.transaction(other) as repo:
            await repo._conn.execute(
                'INSERT INTO redemptions(user_id,reward_id,saved) VALUES($1,$2,$3)',
                other, offer.id, Decimal('1.00'))


@pytest.mark.asyncio
async def test_application_lifespan_seeds_history_before_serving(db, monkeypatch):
    from backend.app.main import app, lifespan
    from backend.decisions.storage import Database
    monkeypatch.setenv('DATABASE_URL', db.test_url)

    class StartupDatabase:
        def transaction(self, user_id):
            return db.transaction(user_id)

        async def close(self):
            pass

    async def connect(*args, **kwargs):
        return StartupDatabase()

    monkeypatch.setattr(Database, 'connect', connect)
    async with lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            response = await client.get('/savings', headers={'X-User-Id': str(DEMO_USER_ID)})
            assert response.status_code == 200
            assert response.json()['total'] == '103.51'
            assert len(response.json()['items']) == 8


@pytest.mark.asyncio
async def test_migration_upgrades_existing_foundation_without_resetting_rewards(db):
    # Simulate the previously deployed 002 schema, retaining existing user data.
    owner = uuid4()
    offer = reward(owner)
    async with db.transaction(owner) as repo:
        await repo.save_reward(offer)
        await repo._conn.execute('DROP TABLE redemptions')
        await repo._conn.execute("DELETE FROM schema_migrations WHERE version='003_redemptions.sql'")
    await db.migrate()
    await db.migrate()
    async with db.transaction(owner) as repo:
        assert (await repo.get_reward(offer.id, reveal_code=True)).code == offer.code
        await redeem_reward(repo, offer.id, RedeemRequest(saved='0.01'))
        assert (await savings_summary(repo)).total == Decimal('0.01')


@pytest.mark.asyncio
async def test_redemption_streams_through_delivery_when_component_is_available(db):
    delivery = pytest.importorskip('backend.decisions.delivery',
        reason='Delivery is a separate, not-yet-merged component on current main')
    from backend.decisions.delivery.service import Settings
    import socket
    import uvicorn

    app = FastAPI()
    app.state.database = db
    app.include_router(router)
    app.include_router(delivery.router)
    await delivery.startup(app, Settings(poll_seconds=.01))
    owner = uuid4()
    offer = reward(owner)
    async with db.transaction(owner) as repo:
        await repo.save_reward(offer)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(128)
    server = uvicorn.Server(uvicorn.Config(app, lifespan='off', log_level='error'))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        for _ in range(200):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(.01)
        assert server.started
        url = f'http://127.0.0.1:{sock.getsockname()[1]}'
        headers = {'X-User-Id': str(owner)}
        async with httpx.AsyncClient(base_url=url, timeout=5) as client:
            async with client.stream('GET', '/events', headers=headers) as response:
                assert response.status_code == 200
                lines = response.aiter_lines()

                async def next_event(kind):
                    async for line in lines:
                        if line.startswith('data: '):
                            event = json.loads(line[6:])
                            if event['event_type'] == kind:
                                return event

                await asyncio.wait_for(next_event('sync_complete'), 3)
                redeemed = await client.post(f'/rewards/{offer.id}/redeem',
                                             headers=headers, json={'saved': '12.50'})
                assert redeemed.status_code == 200
                event = await asyncio.wait_for(next_event('reward_used'), 3)
                assert event['reward_id'] == str(offer.id)
                assert event['user_id'] == str(owner)
                assert event['data']['status'] == 'used'
                assert offer.code not in json.dumps(event)
                assert (await client.get('/savings', headers=headers)).json()['total'] == '12.50'
    finally:
        await delivery.shutdown(app)
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        sock.close()


def test_calculation_caps_rounding_and_generated_contracts():
    offer = reward(uuid4(), value='12.5', max_discount='20.00', min_spend='10.00')
    assert calculate_savings(offer, Decimal('10.04')) == Decimal('1.26')
    assert calculate_savings(offer, Decimal('500.00')) == Decimal('20.00')
    with pytest.raises(ValueError):
        calculate_savings(offer, Decimal('9.99'))
    root = Path(__file__).parents[2]
    schema = json.loads((root / 'shared/schemas/SavingsSummary.json').read_text())
    assert schema['properties']['total']['type'] == 'string'
    spec = json.loads((root / 'shared/openapi.json').read_text())
    assert '/savings' in spec['paths'] and '/rewards/{id}/redeem' in spec['paths']
