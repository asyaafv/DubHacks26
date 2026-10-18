"""Fast deterministic component tests; these do not verify semantic retrieval."""
from datetime import timedelta
from decimal import Decimal
import math
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from backend.app.schemas import LookupRequest, Merchant
from backend.decisions.lookup.matching import safe_domain, exact_merchants
from backend.decisions.lookup.ranking import rank_rewards, value_component
from backend.decisions.lookup.router import router, get_lookup_service
from backend.decisions.lookup.service import LookupService
from backend.decisions.dependencies import get_database
from backend.tests.test_storage_wallet import NOW, reward


def test_native_units_and_no_invented_values():
    owner = uuid4()
    assert value_component(reward(owner, kind='percent_off', value='20')) == .2
    assert value_component(reward(owner, kind='amount_off', value='20')) == .4
    for kind in ('points', 'free_item', 'bogo', 'cashback'):
        assert value_component(reward(owner, kind=kind, value='20')) == 0
    assert value_component(reward(owner, kind='amount_off', currency='EUR', value='20')) == 0
    r = reward(owner, kind='percent_off', value='20')
    result = rank_rewards([(r, 1)], now=NOW)[0]
    assert result.reward.value == Decimal('20') and result.reward.kind == 'percent_off'
    assert result.score == result.value_component * result.match_component * result.urgency_component


def test_continuous_urgency_value_tradeoff_and_ties():
    owner = uuid4()
    soon = reward(owner, kind='amount_off', value='15', expires_at=NOW + timedelta(hours=1))
    later = reward(owner, kind='amount_off', value='20', expires_at=NOW + timedelta(days=30))
    large = reward(owner, kind='amount_off', value='50')
    results = rank_rewards([(later, 1), (soon, 1), (large, 1)], now=NOW)
    assert [s.reward.id for s in results] == [large.id, soon.id, later.id]
    assert results[1].urgency_component == pytest.approx(1 + math.exp(-(1/24)/3))
    a = reward(owner, id=UUID(int=1), expires_at=None)
    b = a.model_copy(update={'id': UUID(int=2)})
    assert [s.reward.id for s in rank_rewards([(b, 1), (a, 1)], now=NOW)] == [a.id, b.id]


def test_expiration_boundaries_and_default_limit():
    owner = uuid4()
    eligible = [reward(owner, starts_at=NOW, expires_at=NOW + timedelta(microseconds=1)) for _ in range(5)]
    invalid = [reward(owner, expires_at=NOW), reward(owner, expires_at=NOW-timedelta(seconds=1)),
        reward(owner, starts_at=NOW+timedelta(microseconds=1)),
        *[reward(owner, status=s) for s in ('used','expired','needs_review')]]
    assert len(rank_rewards([(r, 1) for r in eligible+invalid], now=NOW)) == 3
    assert len(rank_rewards([(r, 1) for r in eligible+invalid], now=NOW, limit=10)) == 5
    assert not rank_rewards([(eligible[0], 0)], now=NOW)


@pytest.mark.parametrize('value', ['https://WWW.NIKE.COM./cart?q=1', 'nike.com', 'www.nike.com'])
def test_safe_domain(value):
    assert safe_domain(value) == 'nike.com'


@pytest.mark.parametrize('value', ['https://nike.com@evil.com', 'javascript://nike.com', 'nike.com:123',
                                  'nike.com..', '-nike.com', 'nike..com'])
def test_bad_domain(value):
    # Trailing DNS dots are canonicalized by foundation; repeated trailing dots
    # are separately rejected by lookup.
    with pytest.raises(ValueError):
        safe_domain(value)


def test_exact_boundaries_and_aliases():
    m = Merchant(id=uuid4(), name='Nike', domain='nike.com', aliases=['Nike Store'], category='Shoes', mcc='5661')
    assert exact_merchants('Do I have Nike rewards?', [m]) == [m]
    assert exact_merchants('Nike Store', [m]) == [m]
    assert exact_merchants('https://www.NIKE.com./cart', [m]) == [m]
    assert exact_merchants('nike.com.evil', [m]) == []
    with pytest.raises(ValueError):
        exact_merchants('https://nike.com@evil.com', [m])
    assert not exact_merchants('nikeshoes nike.com.evil', [m])


@pytest.mark.asyncio
async def test_router_identity_limits_and_service_dependency():
    from contextlib import asynccontextmanager
    class Repo:
        async def count_lookup_rewards(self, **kwargs): return 0
        async def lookup_merchants(self): return []
    class DB:
        @asynccontextmanager
        async def transaction(self, user_id): yield Repo()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_database] = lambda: DB()
    app.dependency_overrides[get_lookup_service] = lambda: LookupService(clock=lambda: NOW)
    owner = uuid4()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        body = dict(user_id=str(owner), domain='unknown.test')
        assert (await client.post('/lookup', json=body)).json()['rewards'] == []
        assert (await client.post('/lookup', json=body, headers={'X-User-Id': str(uuid4())})).status_code == 400
        assert (await client.post('/lookup', json={**body, 'limit':11})).status_code == 422
        assert (await client.post('/lookup', json={'user_id':str(owner)})).status_code == 400
        assert (await client.post('/lookup', json={'user_id':str(owner), 'query':'shoes'})).status_code == 503
