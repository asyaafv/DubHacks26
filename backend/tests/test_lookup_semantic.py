"""Opt-in real MiniLM + PostgreSQL/pgvector tests. No synthetic embedding fallback."""
from datetime import timedelta
import os
from uuid import uuid4

import pytest

from backend.app.schemas import LookupRequest, Merchant
from backend.decisions.lookup.embeddings import MiniLMQueryEncoder
from backend.decisions.lookup.service import LookupService
from backend.tests.test_storage_wallet import db, NOW, reward


@pytest.fixture(scope='module')
def encoder():
    if os.getenv('RUN_SEMANTIC_TESTS') != '1':
        pytest.skip('Set RUN_SEMANTIC_TESTS=1 with cached MiniLM weights')
    return MiniLMQueryEncoder(cache_folder=os.getenv('PERK_MODEL_CACHE'), offline=True)


@pytest.mark.asyncio
async def test_real_semantic_retrieval_and_merchant_constraints(db, encoder):
    owner, other = uuid4(), uuid4()
    nike = Merchant(id=uuid4(), name='Nike', domain='nike.com', category='Shoe Stores', mcc='5661', aliases=['Nike Store'])
    adidas = Merchant(id=uuid4(), name='Adidas', domain='adidas.com', category='Shoe Stores', mcc='5661')
    food = Merchant(id=uuid4(), name='Chipotle', domain='chipotle.com', category='Restaurants', mcc='5814')
    nike_vector = encoder.encode_query('Nike Shoe Stores')
    async with db.transaction(owner) as repo:
        for m in (nike, adidas, food):
            await repo.save_merchant(m, embedding=encoder.encode_query(f'{m.name} {m.category}'))
        nike_rewards = [reward(owner, merchant_id=nike.id, merchant_name='Nike', category='Shoe Stores',
            value=str(10+i), expires_at=NOW+timedelta(days=2+i)) for i in range(5)]
        for r in nike_rewards:
            await repo.save_reward(r, embedding=nike_vector)
        # Merchant embedding fallback also finds an offer without a reward vector.
        a = reward(owner, merchant_id=adidas.id, merchant_name='Adidas', category='Shoe Stores')
        await repo.save_reward(a)
        await repo.save_reward(reward(owner, merchant_id=food.id, merchant_name='Chipotle',
            kind='amount_off', value='100', expires_at=NOW+timedelta(seconds=1)),
            embedding=encoder.encode_query('Chipotle Restaurants burrito'))
        # Disallowed rows are identical semantic matches and must be filtered in SQL.
        for updates in [dict(expires_at=NOW), dict(expires_at=NOW-timedelta(seconds=1)),
                        dict(starts_at=NOW+timedelta(microseconds=1)),
                        *[dict(status=s) for s in ('used','expired','needs_review')]]:
            await repo.save_reward(reward(owner, merchant_id=nike.id, **updates), embedding=nike_vector)
    async with db.transaction(other) as repo:
        for _ in range(12):
            await repo.save_reward(reward(other, merchant_id=nike.id), embedding=nike_vector)
    service = LookupService(encoder, clock=lambda: NOW)
    async with db.transaction(owner) as repo:
        for query in ('Nike', 'Do I have Nike rewards?', 'Nike Store'):
            result = await service.lookup(repo, LookupRequest(user_id=owner, query=query))
            assert result.merchant.id == nike.id
            assert len(result.rewards) == 3
            assert all(s.reward.merchant_id == nike.id for s in result.rewards)
            assert result.total_available == 7
            assert all(s.reward.code is None for s in result.rewards)
        for query in ('shoes', 'sneakers'):
            result = await service.lookup(repo, LookupRequest(user_id=owner, query=query, limit=10))
            assert any(s.reward.merchant_id == nike.id for s in result.rewards)
            assert a.id in [s.reward.id for s in result.rewards]
            assert len(result.rewards) == 6
            assert all(s.reward.user_id == owner for s in result.rewards)
            assert [s.reward.id for s in result.rewards] == [s.reward.id for s in
                (await service.lookup(repo, LookupRequest(user_id=owner, query=query, limit=10))).rewards]
        assert not (await service.lookup(repo, LookupRequest(user_id=owner, query='quantum chromodynamics'))).rewards
        assert not (await service.lookup(repo, LookupRequest(user_id=owner, domain='unknown.test', query='shoes'))).rewards
        assert not (await service.lookup(repo, LookupRequest(user_id=owner, query='nike.com.evil'))).rewards
        result = await service.lookup(repo, LookupRequest(user_id=owner, domain='https://www.nike.com./checkout', limit=10))
        assert len(result.rewards) == 5 and all(s.reward.merchant_id == nike.id for s in result.rewards)
        with pytest.raises(ValueError):
            await service.lookup(repo, LookupRequest(user_id=owner, merchant_id=nike.id, domain='adidas.com'))
    async with db.transaction(uuid4()) as repo:
        result = await service.lookup(repo, LookupRequest(user_id=repo.user_id, query='sneakers'))
        assert result.rewards == [] and result.total_available == 0


@pytest.mark.asyncio
async def test_curated_seed_semantics(db, encoder):
    """Exercise the shared catalog, not invented keyword/category embeddings."""
    import json
    from pathlib import Path
    from backend.app.schemas import Reward
    from backend.decisions.common import DEMO_USER_ID
    root = Path(__file__).resolve().parents[2] / 'shared' / 'seed'
    merchants = [Merchant.model_validate(m) for m in json.loads((root/'seed_merchants.json').read_text())['merchants']]
    rewards = [Reward.model_validate(r) for r in json.loads((root/'seed_rewards.json').read_text())['rewards']]
    async with db.transaction(DEMO_USER_ID) as repo:
        for m in merchants:
            await repo.save_merchant(m, embedding=encoder.encode_query(f'{m.name} {m.category}'))
        for r in rewards:
            await repo.save_reward(r, embedding=encoder.encode_query(f'{r.merchant_name} {r.category}'))
        service = LookupService(encoder, clock=lambda: NOW)
        for query in ('shoes', 'sneakers', 'Do I have Nike rewards?'):
            result = await service.lookup(repo, LookupRequest(user_id=DEMO_USER_ID, query=query))
            assert 'Nike' in [s.reward.merchant_name for s in result.rewards]
            assert all(s.reward.status == 'active' for s in result.rewards)
        for query in ('quantum chromodynamics', 'Do I have Gucci rewards?', 'nonexistent-retailer.example'):
            assert not (await service.lookup(repo, LookupRequest(user_id=DEMO_USER_ID, query=query))).rewards


@pytest.mark.asyncio
async def test_ranking_considers_beyond_nearest_hundred(db, encoder):
    owner = uuid4()
    vector = encoder.encode_query('Nike Shoe Stores')
    async with db.transaction(owner) as repo:
        for _ in range(105):
            await repo.save_reward(reward(owner, kind='amount_off', value='1'), embedding=vector)
        best = reward(owner, kind='amount_off', value='50', expires_at=NOW+timedelta(seconds=1))
        await repo.save_reward(best, embedding=vector)
        result = await LookupService(encoder, clock=lambda: NOW).lookup(
            repo, LookupRequest(user_id=owner, query='sneakers'))
        assert len(result.rewards) == 3
        assert result.rewards[0].reward.id == best.id
        assert result.total_available == 106
