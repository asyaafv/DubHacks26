"""Demo mode without Postgres: /wallet, /sync and savings serve the in-memory store.

Postgres behavior is covered by test_storage_wallet/test_savings; these tests run
the real app with DATABASE_URL unset.
"""
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

DEMO = '00000000-0000-0000-0000-000000000001'
OTHER = '00000000-0000-0000-0000-000000000002'


def _reset_caches():
    from backend.app import main
    from backend.decisions import memory
    main._rewards = main._cards = main._memberships = main._merchants = None
    memory.reset()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('PERK_ALLOW_DEMO_IDENTITY', 'true')
    from backend.app import main
    _reset_caches()
    with TestClient(main.app) as test_client:
        yield test_client
    _reset_caches()


def test_wallet_and_sync_work_without_postgres(client):
    wallet = client.get('/wallet', headers={'X-User-Id': DEMO})
    assert wallet.status_code == 200, wallet.text
    data = wallet.json()
    assert len(data['cards']) == 5 and len(data['memberships']) == 5
    assert data['active_rewards_count'] > 0

    sync = client.get('/sync', headers={'X-User-Id': DEMO})
    assert sync.status_code == 200, sync.text
    body = sync.json()
    assert body['rewards'] and len(body['wallet']['cards']) == 5

    # Per-user isolation still holds in memory mode.
    foreign = client.get('/wallet', headers={'X-User-Id': OTHER}).json()
    assert foreign['cards'] == [] and foreign['active_rewards_count'] == 0
    assert client.get('/sync', headers={'X-User-Id': OTHER}).json()['rewards'] == []


def test_savings_seeded_and_redeem_idempotent_without_postgres(client):
    before = client.get('/savings', headers={'X-User-Id': DEMO}).json()
    assert before['total'] == '103.51' and len(before['items']) == 8
    dates = [p['date'] for p in before['series']]
    assert dates == sorted(dates)

    # Taco Bell $5 amount_off: no body -> face value 5.00.
    reward_id = '22222222-2222-2222-2222-222222222202'
    first = client.post(f'/rewards/{reward_id}/redeem', headers={'X-User-Id': DEMO})
    assert first.status_code == 200 and first.json()['status'] == 'used'
    again = client.post(f'/rewards/{reward_id}/redeem', headers={'X-User-Id': DEMO},
                        json={'saved': '99.99'})
    assert again.status_code == 200 and again.json()['status'] == 'used'

    after = client.get('/savings', headers={'X-User-Id': DEMO}).json()
    assert after['total'] == '108.51' and len(after['items']) == 9
    assert after['items'][0]['saved'] == '5.00'
    assert after['series'][-1]['cumulative'] == '108.51'

    # The redeemed reward leaves the active sync snapshot.
    synced = client.get('/sync', headers={'X-User-Id': DEMO}).json()
    assert reward_id not in [r['id'] for r in synced['rewards']]


def test_memory_mode_isolation_and_id_guessing(client):
    reward_id = '22222222-2222-2222-2222-222222222206'
    resp = client.post(f'/rewards/{reward_id}/redeem', headers={'X-User-Id': OTHER},
                       json={'saved': '1.00'})
    assert resp.status_code == 404
    assert client.post(f'/rewards/{uuid4()}/redeem', headers={'X-User-Id': DEMO}).status_code == 404
    foreign = client.get('/savings', headers={'X-User-Id': OTHER}).json()
    assert foreign == {'total': '0.00', 'items': [], 'series': []}
    # Demo reward untouched by the foreign attempt.
    demo_sync = client.get('/sync', headers={'X-User-Id': DEMO}).json()
    assert reward_id in [r['id'] for r in demo_sync['rewards']]
