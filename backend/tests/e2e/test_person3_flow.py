import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from uuid import uuid4

import pytest

from backend.app.schemas import Merchant, StackRequest
from backend.decisions.jobs.expire import run_expiration
from backend.decisions.stacking.domain import prepare
from backend.decisions.stacking.reference import exhaustive
from backend.decisions.stacking.service import load_checkout
from backend.tests.e2e.harness import serve
from backend.tests.test_delivery import listening, next_data
from backend.tests.test_storage_wallet import reward, card, membership


def checked(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_absent_commit_discover_stack_redeem_stream_replay_sync(db, encoder):
    owner, other = uuid4(), uuid4()
    headers = {'X-User-Id': str(owner)}
    foreign = {'X-User-Id': str(other)}
    now = datetime.now(timezone.utc)
    nike = Merchant(id=uuid4(), name='Nike', domain='nike.com', mcc='5661', category='Shoe Stores')
    offer = reward(owner, merchant_id=nike.id, merchant_name=nike.name, category=nike.category,
                   mcc=nike.mcc, kind='amount_off', value='15', expires_at=now + timedelta(days=2))
    owned_card = card(owner).model_copy(update={'base_rate': Decimal('5'), 'category_rates': []})
    async with db.transaction(owner) as repo:
        await repo.save_merchant(nike, embedding=encoder.encode_query('Nike Shoe Stores'))
        await repo.add_card(owned_card)
    body = {'user_id': str(owner), 'domain': 'nike.com', 'cart_total': '100.00'}
    async with serve(db, encoder) as (client, app):
        initial = checked(await client.get('/sync', headers=headers))
        assert initial['rewards'] == []
        assert checked(await client.post('/lookup', headers=headers, json={'user_id': str(owner), 'query': 'shoes'}))['rewards'] == []
        before = checked(await client.post('/stack', headers=headers, json=body))
        assert before['chosen_rewards'] == [] and before['final_price'] == '100.00'
        async with listening(client, owner) as one, listening(client, owner) as two:
            await next_data(one, 'sync_complete')
            await next_data(two, 'sync_complete')
            # Input boundary: a normalized reward, NOT email extraction/redaction.
            async with db.transaction(owner) as repo:
                assert await repo.save_reward(offer, dedupe_key='new-normalized-offer',
                                              embedding=encoder.encode_query('Nike shoes sneakers'))
                await asyncio.sleep(.06)
                assert not any(data for _, data in one._queue)
            first, second = await asyncio.gather(next_data(one, 'reward_added'), next_data(two, 'reward_added'))
            assert first == second and first[1]['reward_id'] == str(offer.id)
            assert offer.code not in json.dumps(first)
            for query in ('Nike', 'shoes', 'sneakers'):
                found = checked(await client.post('/lookup', headers=headers, json={'user_id': str(owner), 'query': query}))
                assert [r['reward']['id'] for r in found['rewards']] == [str(offer.id)]
                assert found['rewards'][0]['reward']['code'] is None
            stack = checked(await client.post('/stack', headers=headers, json=body))
            assert stack['solver_status'] == 'optimal'
            assert [r['reward_id'] for r in stack['chosen_rewards']] == [str(offer.id)]
            assert stack['chosen_rewards'][0]['savings'] == '15.00'
            assert stack['final_price'] == '85.00' and stack['card_cashback'] == '4.25'
            assert stack['total_savings'] == '19.25' and stack['recommended_card']['id'] == str(owned_card.id)
            expected = (f'Reward {offer.id}: $15.00 immediate discount; expires {offer.expires_at.isoformat()}. '
                        'Checkout: $100.00 - $15.00 immediate discounts = $85.00. '
                        'Product: 5% of $85.00 = $4.25 card cashback after checkout. '
                        'Total savings: $19.25 ($0.00 reward cashback; $4.25 card cashback).')
            assert stack['explanation'] == expected
            async with db.transaction(owner) as repo:
                req = StackRequest(**body)
                rewards, cards, merchant, members = await load_checkout(repo, req, now=now)
                oracle = exhaustive(prepare(req, rewards, cards, members, merchant, now=now))
                assert (oracle.final, oracle.card_cashback, oracle.total) == (8500, 425, 1925)
            wallet = checked(await client.get('/wallet', headers=headers))
            assert [r['id'] for r in wallet['rewards']] == [str(offer.id)]
            assert wallet['rewards'][0]['expires_at'] is not None
            assert checked(await client.post('/lookup', headers=foreign, json={'user_id': str(other), 'query': 'shoes'}))['rewards'] == []
            assert (await client.post('/stack', headers=foreign, json=body)).status_code == 400
            assert (await client.post('/lookup', headers=foreign, json={'user_id': str(owner), 'query': 'Nike'})).status_code == 400
            assert (await client.post('/stack', headers=headers, json={**body, 'merchant_id': str(uuid4())})).status_code == 400
            url = f'/rewards/{offer.id}/redeem'
            assert (await client.post(url, headers=foreign, json={'saved': '15.00'})).status_code == 404
            responses = await asyncio.gather(*[client.post(url, headers=headers, json={'saved': '15.00'}) for _ in range(6)])
            assert all(r.status_code == 200 and r.json()['status'] == 'used' for r in responses)
            used_one, used_two = await asyncio.gather(next_data(one, 'reward_used'), next_data(two, 'reward_used'))
            assert used_one == used_two and used_one[1]['reward_id'] == str(offer.id)
            assert offer.code not in json.dumps(used_one)
        checked(await client.post(url, headers=headers, json={'saved': '999.00'}))
        ledger = checked(await client.get('/savings', headers=headers))
        assert ledger['total'] == '15.00' and len(ledger['items']) == 1
        assert ledger['series'] == [{'date': ledger['items'][0]['redeemed_at'][:10], 'cumulative': '15.00'}]
        assert checked(await client.get('/savings', headers=foreign)) == {'total': '0.00', 'items': [], 'series': []}
        delta = checked(await client.get('/sync', headers=headers, params={'since': initial['last_sync']}))
        assert [r['status'] for r in delta['rewards']] == ['used']
        assert delta['wallet']['rewards'] == []
        assert checked(await client.post('/lookup', headers=headers, json={'user_id': str(owner), 'query': 'shoes'}))['rewards'] == []
        assert checked(await client.post('/stack', headers=headers, json=body))['chosen_rewards'] == []
        async with listening(client, owner, first[0]) as replay:
            replayed = await next_data(replay, 'reward_used')
            assert replayed == used_one
        async with db.transaction(owner) as repo:
            assert len([e for e in await repo.list_events() if e.event.event_type == 'reward_used']) == 1


@pytest.mark.asyncio
async def test_redemption_http_outbox_failure_rolls_back_all_boundaries(db, monkeypatch):
    from backend.decisions.storage.repository import Repository
    owner = uuid4()
    headers = {'X-User-Id': str(owner)}
    offer = reward(owner)
    async with db.transaction(owner) as repo:
        await repo.save_reward(offer)
    original = Repository.append_event

    async def fail(self, event_type, *args, **kwargs):
        if event_type == 'reward_used':
            raise RuntimeError('Test-only outbox failure')
        return await original(self, event_type, *args, **kwargs)

    async with serve(db) as (client, _):
        before = checked(await client.get('/sync', headers=headers))
        monkeypatch.setattr(Repository, 'append_event', fail)
        response = await client.post(f'/rewards/{offer.id}/redeem', headers=headers, json={'saved': '12.50'})
        assert response.status_code == 500
        assert checked(await client.get('/savings', headers=headers)) == {'total': '0.00', 'items': [], 'series': []}
        wallet = checked(await client.get('/wallet', headers=headers))
        assert [r['status'] for r in wallet['rewards']] == ['active']
        delta = checked(await client.get('/sync', headers=headers, params={'since': before['last_sync']}))
        assert delta['pending_events'] == []
        async with db.transaction(owner) as repo:
            assert await repo.get_redemption(offer.id) is None
            assert [e.event.event_type for e in await repo.list_events()] == ['reward_added']
        monkeypatch.setattr(Repository, 'append_event', original)
        checked(await client.post(f'/rewards/{offer.id}/redeem', headers=headers, json={'saved': '12.50'}))
        assert checked(await client.get('/savings', headers=headers))['total'] == '12.50'


@pytest.mark.asyncio
async def test_hollister_persisted_seed_and_explicit_test_only_golden_terms(db):
    from backend.decisions.common import DEMO_USER_ID
    from backend.decisions.storage.seed import seed
    from backend.decisions.stacking.domain import RewardTerms
    from backend.decisions.stacking.service import solve_stacking
    from backend.tests.test_stacking import seed_data, NOW
    req, _, seed_cards, _ = seed_data()
    assert sum(i.price * i.quantity for i in req.items) == Decimal('479.65')
    await seed(db)
    async with serve(db) as (client, _):
        result = checked(await client.post('/stack', headers={'X-User-Id': str(DEMO_USER_ID)}, json=req.model_dump(mode='json')))
        assert result['chosen_rewards'][0]['savings'] == '47.97'
        assert (result['final_price'], result['card_cashback'], result['total_savings']) == ('452.03', '6.78', '54.75')
        assert result['recommended_card']['name'] == 'Freedom Unlimited (DEMO)'
    async with db.transaction(DEMO_USER_ID) as repo:
        rewards, cards, merchant, members = await load_checkout(repo, req, now=NOW)
    # Corrections exist only in this test's model copies. No shared seed/DB edits.
    cards = [c.model_copy(deep=True) for c in cards]
    cash_plus = next(c for c in cards if c.id == seed_cards[-1].id)
    assert '5651' not in cash_plus.category_rates[0].mcc_codes
    cash_plus.category_rates[0].mcc_codes.append('5651')
    terms = {rewards[0].id: RewardTerms(remainder_eligible=True)}
    golden = solve_stacking(req, rewards, cards, merchant, members, now=NOW, terms=terms)
    oracle = exhaustive(prepare(req, rewards, cards, members, merchant, now=NOW, terms=terms))
    assert golden.chosen_rewards[0].savings == Decimal('50.00')
    assert (golden.final_price, golden.card_cashback, golden.total_savings) == (Decimal('450'), Decimal('22.50'), Decimal('72.50'))
    assert (oracle.final, oracle.card_cashback, oracle.total) == (45000, 2250, 7250)


@pytest.mark.asyncio
async def test_http_expiry_ranking_boundary_overlap_and_wallet_removal(db, encoder):
    owner = uuid4()
    headers = {'X-User-Id': str(owner)}
    now = datetime.now(timezone.utc)
    merchant = Merchant(id=uuid4(), name='Nike', domain='nike.com', category='Shoe Stores', mcc='5661')
    urgent = reward(owner, merchant_id=merchant.id, kind='amount_off', value='15', expires_at=now + timedelta(hours=1))
    later = reward(owner, merchant_id=merchant.id, kind='amount_off', value='20', expires_at=now + timedelta(days=30))
    boundary = reward(owner, merchant_id=merchant.id, expires_at=now)
    c, m = card(owner), membership(owner)
    async with db.transaction(owner) as repo:
        await repo.save_merchant(merchant, embedding=encoder.encode_query('Nike Shoe Stores'))
        for r in (urgent, later, boundary):
            await repo.save_reward(r)
        await repo.add_card(c)
        await repo.add_membership(m)
    async with serve(db, encoder) as (client, app):
        snapshot = checked(await client.get('/sync', headers=headers))
        app.state.lookup_clock = lambda: now
        found = checked(await client.post('/lookup', headers=headers, json={'user_id': str(owner), 'query': 'Nike'}))
        assert [r['reward']['id'] for r in found['rewards']] == [str(urgent.id), str(later.id)]
        runs = await asyncio.gather(*[run_expiration(db, clock=lambda: now, batch_size=1) for _ in range(2)])
        assert sum(r.expired for r in runs) == 1
        assert sum(r.alerts for r in runs) == 1
        rerun = await run_expiration(db, clock=lambda: now, batch_size=1)
        assert rerun.expired == rerun.alerts == 0
        removed = checked(await client.post('/wallet', headers=headers, json={'remove_card_ids': [str(c.id)], 'remove_membership_ids': [str(m.id)]}))
        assert removed['cards'] == removed['memberships'] == []
        delta = checked(await client.get('/sync', headers=headers, params={'since': snapshot['last_sync']}))
        assert delta['wallet']['cards'] == delta['wallet']['memberships'] == []
        assert any(r['id'] == str(boundary.id) and r['status'] == 'expired' for r in delta['rewards'])
        async with db.transaction(owner) as repo:
            events = await repo.list_events()
            assert len([e for e in events if e.event.event_type == 'reward_expiring' and e.event.reward_id == urgent.id]) == 1
