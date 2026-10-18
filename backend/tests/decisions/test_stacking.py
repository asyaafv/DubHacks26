"""CP-SAT stacking engine: fixtures, constraints, card choice, and fallback.

API tests run the real app in memory mode (no DATABASE_URL) against the seed
JSON, exactly like the demo. Unit tests drive solve_stack with synthetic data
and a pinned clock.
"""
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.schemas import Card, Merchant, Reward, StackRequest
from backend.decisions.stacking import solve_stack
from backend.decisions.stacking import engine

FIXTURES = Path(__file__).parents[3] / 'shared' / 'seed' / 'fixtures'
DEMO = '00000000-0000-0000-0000-000000000001'
OTHER = '00000000-0000-0000-0000-000000000002'
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
USER = UUID(DEMO)

MERCHANT = Merchant(id=uuid4(), name='Shop', domain='shop.test', mcc='5651',
                    category='Family Clothing Stores')


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


def make_reward(**updates):
    data = dict(id=uuid4(), user_id=USER, merchant_id=MERCHANT.id, merchant_name='Shop',
                category='Family Clothing Stores', mcc='5651', kind='percent_off',
                value='10.00', source='manual', created_at=NOW, updated_at=NOW)
    data.update(updates)
    return Reward(**data)


def make_card(**updates):
    data = dict(id=uuid4(), user_id=USER, issuer='Bank', network='visa', name='Card',
                base_rate='1.0', category_rates=[])
    data.update(updates)
    return Card(**data)


def run(rewards, cards=(), cart_total='100.00', items=None, merchant=MERCHANT):
    request = StackRequest(user_id=USER, merchant_id=merchant.id,
                           cart_total=Decimal(cart_total), items=items or [])
    return solve_stack(request, user_id=USER, rewards=list(rewards),
                       cards=list(cards), merchants=[merchant], now=NOW)


# ---------------------------------------------------------------------------
# Fixture scenarios through the real app
# ---------------------------------------------------------------------------

def test_hollister_500_fixture(client):
    fixture = json.loads((FIXTURES / 'hollister_500_cart.json').read_text())
    response = client.post('/stack', headers={'X-User-Id': DEMO}, json=fixture['request'])
    assert response.status_code == 200, response.text
    data = response.json()

    assert [c['reward_id'] for c in data['chosen_rewards']] == ['22222222-2222-2222-2222-222222222201']
    chosen = data['chosen_rewards'][0]
    assert chosen['savings'] == '50.00' and chosen['applied_order'] == 1
    assert chosen['reward']['code'] == 'HCOFALL10'

    # The fixture's expected card: US Bank Cash+ at 5% on MCC 5651, not cards[0].
    assert data['recommended_card']['id'] == '33333333-3333-3333-3333-333333333305'
    assert data['card_cashback'] == '22.50'
    assert data['original_price'] == '500.00'
    assert data['final_price'] == '450.00'
    assert data['total_savings'] == '72.50'
    assert data['savings_percent'] == '14.50'
    assert data['solver_status'] == 'optimal'
    assert any('HCOFALL10' in line for line in data['explanations'])
    assert any('Cash+' in line for line in data['explanations'])


def test_target_100_fixture_one_code_and_exclusions(client):
    # "Use it before you lose it": TARGET5 expires within 7 days while
    # CIRCLE15 stays good 14+ days past it and both carry promo codes, so the
    # default (prefer_expiring=True) now spends TARGET5 and saves CIRCLE15
    # for later instead of maximizing immediate savings with CIRCLE15.
    fixture = json.loads((FIXTURES / 'target_100_cart.json').read_text())
    response = client.post('/stack', headers={'X-User-Id': DEMO}, json=fixture['request'])
    assert response.status_code == 200, response.text
    data = response.json()

    codes = [c['reward']['code'] for c in data['chosen_rewards'] if c['reward']['code']]
    assert len(codes) <= 1, f'max one promo code violated: {codes}'
    assert codes == ['TARGET5']
    assert data['chosen_rewards'][0]['savings'] == '5.00'
    assert data['final_price'] == '95.00'
    assert data['recommended_card']['id'] == '33333333-3333-3333-3333-333333333305'
    assert data['card_cashback'] == '4.75'
    assert data['total_savings'] == '9.75'
    assert data['solver_status'] == 'optimal'
    assert any(line.startswith('Saved for later: 15% off (CIRCLE15)')
               for line in data['explanations'])

    # Opting out restores the old pure-savings behavior: CIRCLE15 wins at
    # 15% of the $80 eligible base (the $20 Apple item is excluded).
    response = client.post('/stack', headers={'X-User-Id': DEMO},
                           json={**fixture['request'], 'prefer_expiring': False})
    data = response.json()
    codes = [c['reward']['code'] for c in data['chosen_rewards'] if c['reward']['code']]
    assert codes == ['CIRCLE15']
    assert data['chosen_rewards'][0]['savings'] == '12.00'
    assert data['final_price'] == '88.00'
    assert data['card_cashback'] == '4.40'
    assert data['total_savings'] == '16.40'
    assert any('TARGET5' in line and 'one promo code' in line for line in data['explanations'])


def test_min_spend_not_met(client):
    # prefer_expiring=False: the default use-before-you-lose-it rule now
    # withholds CIRCLE15 before the solver ever evaluates its min spend, so
    # opting out is required to exercise the min-spend exclusion explanation.
    response = client.post('/stack', headers={'X-User-Id': DEMO}, json={
        'user_id': DEMO, 'domain': 'target.com', 'cart_total': '50.00', 'items': [],
        'prefer_expiring': False,
    })
    data = response.json()
    # CIRCLE15 needs $75 min spend; only TARGET5 ($5 off, min $25) applies.
    assert [c['reward']['code'] for c in data['chosen_rewards']] == ['TARGET5']
    assert data['chosen_rewards'][0]['savings'] == '5.00'
    assert any('minimum spend' in line and 'CIRCLE15' in line for line in data['explanations'])


def test_other_users_rewards_excluded(client):
    response = client.post('/stack', headers={'X-User-Id': OTHER}, json={
        'user_id': OTHER, 'domain': 'hollisterco.com', 'cart_total': '500.00', 'items': [],
    })
    data = response.json()
    assert data['chosen_rewards'] == [] and data['recommended_card'] is None
    assert data['final_price'] == '500.00'


# ---------------------------------------------------------------------------
# Solver unit tests
# ---------------------------------------------------------------------------

def test_expired_and_future_rewards_excluded():
    expired = make_reward(value='50.00', expires_at=NOW - timedelta(days=1))
    future = make_reward(value='40.00', starts_at=NOW + timedelta(days=1))
    used = make_reward(value='30.00', status='used')
    live = make_reward(value='5.00', expires_at=NOW + timedelta(days=1))
    result = run([expired, future, used, live])
    assert [c.reward_id for c in result.chosen_rewards] == [live.id]
    assert result.chosen_rewards[0].savings == Decimal('5.00')
    assert any('expired on' in line for line in result.explanations)
    assert any('not valid until' in line for line in result.explanations)
    assert any('status is used' in line for line in result.explanations)


def test_percent_vs_amount_off_choice():
    percent = make_reward(kind='percent_off', value='10.00')
    amount = make_reward(kind='amount_off', value='8.00')
    # $50 cart: 10% = $5 < $8 -> amount_off wins.
    small = run([percent, amount], cart_total='50.00')
    assert [c.reward_id for c in small.chosen_rewards] == [amount.id]
    assert small.chosen_rewards[0].savings == Decimal('8.00')
    # $100 cart: 10% = $10 > $8 -> percent_off wins.
    large = run([percent, amount], cart_total='100.00')
    assert [c.reward_id for c in large.chosen_rewards] == [percent.id]
    assert large.chosen_rewards[0].savings == Decimal('10.00')


def test_max_discount_cap_applies():
    capped = make_reward(kind='percent_off', value='20.00', max_discount='15.00')
    result = run([capped], cart_total='200.00')
    assert result.chosen_rewards[0].savings == Decimal('15.00')


def test_stackable_rewards_combine_but_codes_do_not():
    coded = make_reward(kind='percent_off', value='10.00', code='TEN', stackable=True)
    codeless = make_reward(kind='amount_off', value='4.00', stackable=True)
    other_code = make_reward(kind='amount_off', value='3.00', code='THREE', stackable=True)
    result = run([coded, codeless, other_code], cart_total='100.00')
    chosen_ids = {c.reward_id for c in result.chosen_rewards}
    assert chosen_ids == {coded.id, codeless.id}  # one code + the codeless stackable
    assert result.final_price == Decimal('86.00')
    codes = [c.reward.code for c in result.chosen_rewards if c.reward.code]
    assert len(codes) == 1


def test_non_stackable_pair_mutually_exclusive():
    a = make_reward(kind='amount_off', value='6.00', stackable=False)
    b = make_reward(kind='amount_off', value='4.00', stackable=False)
    result = run([a, b], cart_total='100.00')
    assert [c.reward_id for c in result.chosen_rewards] == [a.id]
    assert any('not stackable' in line for line in result.explanations)


def test_cashback_card_choice_uses_card_rate():
    base_only = make_card(name='Flat', base_rate='1.5')
    bonus = make_card(name='Bonus', base_rate='1.0', category_rates=[
        {'category': 'Clothing', 'mcc_codes': ['5651'], 'rate': '5.0'}])
    wrong_mcc = make_card(name='WrongMCC', base_rate='1.0', category_rates=[
        {'category': 'Department Stores', 'mcc_codes': ['5311'], 'rate': '6.0'}])
    result = run([make_reward(value='10.00')], cards=[base_only, bonus, wrong_mcc],
                 cart_total='100.00')
    assert result.recommended_card.id == bonus.id
    # 5% of the $90 remaining after the reward.
    assert result.card_cashback == Decimal('4.50')
    assert result.total_savings == Decimal('14.50')
    assert any('WrongMCC' in line and '1%' in line for line in result.explanations)


def test_deterministic_tie_break():
    twin_a = make_reward(id=UUID(int=1), kind='amount_off', value='5.00')
    twin_b = make_reward(id=UUID(int=2), kind='amount_off', value='5.00')
    card_a = make_card(id=UUID(int=3), name='A', base_rate='2.0')
    card_b = make_card(id=UUID(int=4), name='B', base_rate='2.0')
    results = [run([twin_b, twin_a], cards=[card_b, card_a]) for _ in range(5)]
    for result in results:
        assert [c.reward_id for c in result.chosen_rewards] == [twin_a.id]
        assert result.recommended_card.id == card_a.id


def test_exclusions_remove_matching_items_only():
    reward = make_reward(kind='percent_off', value='10.00',
                         exclusions=['Gift Cards', 'Clearance'])
    items = [
        {'name': 'Hollister Gift Card', 'category': 'Gift Cards', 'price': '25.00', 'quantity': 2},
        {'name': 'Clearance Hoodie', 'category': 'Tops', 'price': '10.00', 'quantity': 1},
        {'name': 'Jeans', 'category': 'Bottoms', 'price': '40.00', 'quantity': 1},
    ]
    result = run([reward], cart_total='100.00', items=items)
    # $100 - $50 gift cards - $10 clearance-named item = $40 eligible -> $4.00.
    assert result.chosen_rewards[0].savings == Decimal('4.00')


def test_all_items_excluded_reward_dropped():
    reward = make_reward(kind='percent_off', value='10.00', exclusions=['Gift Cards'])
    items = [{'name': 'Gift Card', 'category': 'Gift Cards', 'price': '100.00', 'quantity': 1}]
    result = run([reward], cart_total='100.00', items=items)
    assert result.chosen_rewards == []
    assert any('every cart item matches its exclusions' in line for line in result.explanations)


def test_greedy_fallback_when_solver_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise engine.SolverFailed('simulated')
    monkeypatch.setattr(engine, '_solve_cpsat', boom)
    coded_big = make_reward(kind='amount_off', value='10.00', code='BIG', stackable=True)
    coded_small = make_reward(kind='amount_off', value='5.00', code='SMALL', stackable=True)
    card = make_card(name='Best', base_rate='2.0')
    result = run([coded_big, coded_small], cards=[card])
    assert result.solver_status == 'greedy_fallback'
    assert [c.reward_id for c in result.chosen_rewards] == [coded_big.id]
    assert result.recommended_card.id == card.id
    assert result.card_cashback == Decimal('1.80')


def test_conflicting_merchant_identity_rejected(client):
    response = client.post('/stack', headers={'X-User-Id': DEMO}, json={
        'user_id': DEMO,
        'merchant_id': '11111111-1111-1111-1111-111111111101',  # Target
        'domain': 'hollisterco.com',
        'cart_total': '100.00',
        'items': [],
    })
    assert response.status_code == 400
