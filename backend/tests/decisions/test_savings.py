"""Savings/redemption tests on real Postgres (same fixture style as test_storage_wallet)."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
import secrets
from uuid import uuid4

import asyncpg
import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from backend.app.schemas import EventType, Reward, RewardStatus
from backend.decisions.common import DEMO_USER_ID
from backend.decisions.savings.router import router
from backend.decisions.savings.service import face_value
from backend.decisions.storage import Database
from backend.decisions.storage.seed import seed

NOW = datetime(2026, 10, 18, tzinfo=timezone.utc)


@pytest_asyncio.fixture
async def db():
    url = os.getenv('TEST_DATABASE_URL')
    if not url:
        pytest.skip('TEST_DATABASE_URL is required for real Postgres tests')
    schema = 'test_savings_' + uuid4().hex
    admin = await asyncpg.connect(url)
    for extension in ('pgcrypto', 'vector', 'uuid-ossp'):
        await admin.execute(f'CREATE EXTENSION IF NOT EXISTS "{extension}" WITH SCHEMA public')
    await admin.execute(f'CREATE SCHEMA {schema}')
    pool = await asyncpg.create_pool(url, min_size=1, max_size=5,
                                     server_settings={'search_path': schema + ',public', 'timezone': 'UTC'})
    database = Database(pool, secrets.token_hex(32))
    try:
        await database.migrate()
        yield database
    finally:
        await database.close()
        await admin.execute(f'DROP SCHEMA {schema} CASCADE')
        await admin.close()


@pytest_asyncio.fixture
async def client(db):
    app = FastAPI()
    app.include_router(router)
    app.state.database = db
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as c:
        yield c


def reward(owner, **updates):
    data = dict(id=uuid4(), user_id=owner, merchant_name='Shop', category='Clothing',
                mcc='5651', kind='amount_off', value='12.50', source='manual',
                code='secret-' + uuid4().hex, created_at=NOW, updated_at=NOW)
    data.update(updates)
    return Reward(**data)


@pytest.mark.asyncio
async def test_redeem_marks_used_writes_row_and_is_idempotent(db, client):
    owner = uuid4()
    r = reward(owner)
    async with db.transaction(owner) as repo:
        await repo.save_reward(r)
    headers = {'X-User-Id': str(owner)}

    first = await client.post(f'/rewards/{r.id}/redeem', headers=headers, json={'saved': '10.00'})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body['status'] == 'used'
    assert body['code'] == r.code  # decrypted for the owner in the response

    # Idempotent replay: same 200, no second redemption row, no new amount.
    again = await client.post(f'/rewards/{r.id}/redeem', headers=headers, json={'saved': '99.99'})
    assert again.status_code == 200 and again.json()['status'] == 'used'

    async with db.transaction(owner) as repo:
        rows = await repo.list_redemptions()
        assert len(rows) == 1
        assert rows[0].saved == Decimal('10.00')
        assert rows[0].merchant_name == 'Shop'
        events = [row.event.event_type for row in await repo.list_events()]
        assert events.count(EventType.reward_used) == 1
        # Ciphertext at rest: plaintext code must not appear in the raw column.
        raw = await repo._conn.fetchrow('SELECT code_encrypted FROM rewards WHERE user_id=$1 AND id=$2', owner, r.id)
        assert r.code.encode() not in bytes(raw['code_encrypted'])

    savings = (await client.get('/savings', headers=headers)).json()
    assert savings['total'] == '10.00'
    assert [i['reward_id'] for i in savings['items']] == [str(r.id)]


@pytest.mark.asyncio
async def test_redeem_face_value_fallback_and_validation(db, client):
    owner = uuid4()
    percent = reward(owner, kind='percent_off', value='20.00', min_spend='50.00')
    flat = reward(owner, kind='amount_off', value='7.25')
    freebie = reward(owner, kind='free_item', value='1.00')  # team convention: free_item/bogo value is 1.00
    async with db.transaction(owner) as repo:
        for r in (percent, flat, freebie):
            await repo.save_reward(r)
    assert face_value(percent) == Decimal('10.00')
    headers = {'X-User-Id': str(owner)}
    for r, expected in ((percent, '10.00'), (flat, '7.25'), (freebie, '1.00')):
        assert (await client.post(f'/rewards/{r.id}/redeem', headers=headers)).status_code == 200
    async with db.transaction(owner) as repo:
        saved = {row.reward_id: str(row.saved) for row in await repo.list_redemptions()}
    assert saved == {percent.id: '10.00', flat.id: '7.25', freebie.id: '1.00'}
    bad = reward(owner)
    async with db.transaction(owner) as repo:
        await repo.save_reward(bad)
    for invalid in ('-1.00', '1.001'):
        resp = await client.post(f'/rewards/{bad.id}/redeem', headers=headers, json={'saved': invalid})
        assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_savings_total_items_series_cumulative_sorted(db, client):
    owner = uuid4()
    headers = {'X-User-Id': str(owner)}
    amounts_by_day = [('5.00', NOW - timedelta(days=9)), ('2.50', NOW - timedelta(days=9)),
                      ('10.00', NOW - timedelta(days=4)), ('0.01', NOW - timedelta(days=1))]
    async with db.transaction(owner) as repo:
        from backend.decisions.savings.schemas import Redemption
        for saved, when in amounts_by_day:
            r = reward(owner, status='used')
            await repo.save_reward(r)
            await repo.add_redemption(Redemption(id=uuid4(), user_id=owner, reward_id=r.id,
                                                 merchant_name='Shop', description='test',
                                                 saved=Decimal(saved), redeemed_at=when))
    body = (await client.get('/savings', headers=headers)).json()
    assert body['total'] == '17.51'
    assert Decimal(body['total']) == sum(Decimal(i['saved']) for i in body['items'])
    stamps = [i['redeemed_at'] for i in body['items']]
    assert stamps == sorted(stamps, reverse=True)  # newest first
    series = body['series']
    assert [p['date'] for p in series] == sorted(p['date'] for p in series)
    assert len(series) == 3  # one point per day with a redemption
    cumulative = [Decimal(p['cumulative']) for p in series]
    assert cumulative == sorted(cumulative) and cumulative[-1] == Decimal('17.51')
    assert cumulative[0] == Decimal('7.50')


@pytest.mark.asyncio
async def test_per_user_isolation_and_id_guessing(db, client):
    owner, attacker = uuid4(), uuid4()
    r = reward(owner)
    async with db.transaction(owner) as repo:
        await repo.save_reward(r)
    # Guessing another user's reward id must 404, never redeem or reveal it.
    resp = await client.post(f'/rewards/{r.id}/redeem', headers={'X-User-Id': str(attacker)}, json={'saved': '1.00'})
    assert resp.status_code == 404
    async with db.transaction(owner) as repo:
        assert (await repo.get_reward(r.id)).status == RewardStatus.active
        assert await repo.list_redemptions() == []
    await client.post(f'/rewards/{r.id}/redeem', headers={'X-User-Id': str(owner)}, json={'saved': '3.00'})
    foreign = (await client.get('/savings', headers={'X-User-Id': str(attacker)})).json()
    assert foreign['total'] == '0.00' and foreign['items'] == [] and foreign['series'] == []
    assert (await client.post(f'/rewards/{uuid4()}/redeem', headers={'X-User-Id': str(owner)})).status_code == 404


@pytest.mark.asyncio
async def test_seeded_demo_redemptions_total_103_51(db, client):
    await seed(db)
    await seed(db)  # ledger makes reseeding a no-op
    body = (await client.get('/savings', headers={'X-User-Id': str(DEMO_USER_ID)})).json()
    assert body['total'] == '103.51'
    assert len(body['items']) == 8
    assert body['series'][-1]['cumulative'] == '103.51'
    merchants = {i['merchant_name'] for i in body['items']}
    assert {'Hollister', 'Taco Bell', 'Target'} <= merchants
    # Every seeded redemption references a used reward owned by the demo user.
    async with db.transaction(DEMO_USER_ID) as repo:
        for item in body['items']:
            stored = await repo.get_reward(item['reward_id'])
            assert stored is not None and stored.status == RewardStatus.used
