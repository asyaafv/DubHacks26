"""Merchant-scoped /lookup: every active direct reward survives the limit.

Regression for starbucks.com showing no rewards: the stub ranked ALL user
rewards globally, so low-scoring direct rewards (Starbucks BOGO/points) fell
outside the page the client fetched. A resolved merchant must scope the
lookup server-side before any limit applies.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

SEED = Path(__file__).resolve().parents[3] / 'shared' / 'seed'
DEMO = '00000000-0000-0000-0000-000000000001'


def _reset_caches():
    from backend.app import main
    from backend.decisions import memory
    main._rewards = main._cards = main._memberships = main._merchants = None
    memory.reset()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    from backend.app import main
    _reset_caches()
    with TestClient(main.app) as test_client:
        yield test_client
    _reset_caches()


def _lookup(client, domain):
    return client.post('/lookup', json={'user_id': DEMO, 'domain': domain, 'limit': 10},
                       headers={'X-User-Id': DEMO})


def test_every_seed_merchant_domain_returns_all_direct_rewards(client):
    merchants = json.loads((SEED / 'seed_merchants.json').read_text())['merchants']
    rewards = json.loads((SEED / 'seed_rewards.json').read_text())['rewards']
    assert merchants
    total_direct = 0
    for merchant in merchants:
        direct = {r['id'] for r in rewards
                  if r['user_id'] == DEMO and r['status'] == 'active'
                  and r.get('merchant_id') == merchant['id']}
        response = _lookup(client, merchant['domain'])
        assert response.status_code == 200, (merchant['name'], response.text)
        body = response.json()
        assert body['merchant'] and body['merchant']['id'] == merchant['id'], merchant['name']
        returned = {s['reward']['id'] for s in body['rewards']}
        missing = direct - returned
        assert not missing, f"{merchant['name']} is missing direct rewards: {missing}"
        # Scoped lookup: no other merchant's rewards and only exact matches.
        for scored in body['rewards']:
            assert scored['reward']['merchant_id'] == merchant['id'], merchant['name']
            assert scored['match_component'] == 1.0, merchant['name']
        total_direct += len(direct)
    # Sanity: the seed actually exercises this (≥20 active direct rewards).
    assert total_direct >= 20


def test_starbucks_low_scoring_direct_rewards_are_returned(client):
    body = _lookup(client, 'starbucks.com').json()
    kinds = sorted(s['reward']['kind'] for s in body['rewards'])
    assert kinds == ['bogo', 'points']
