"""Component tests: pure optimizer + independently mounted HTTP router, no DB."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import random
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from backend.app.schemas import Card, Membership, Merchant, Reward, StackRequest, Wallet
from backend.decisions.dependencies import get_database
from backend.decisions.stacking.domain import RewardTerms, prepare
from backend.decisions.stacking.optimizer import SolverUnavailable, VerificationError, optimize
from backend.decisions.stacking.reference import exhaustive
from backend.decisions.stacking.router import router
from backend.decisions.stacking.service import solve_stacking

USER = UUID(int=1)
FOREIGN = UUID(int=2)
NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
MERCHANT = Merchant(id=UUID(int=10), name='Test Store', domain='test.com', mcc='5651', category='Clothing')
SEED = Path(__file__).resolve().parents[2] / 'shared' / 'seed'


def reward(i=1, **kwargs):
    values = dict(id=UUID(int=100 + i), user_id=USER, merchant_id=MERCHANT.id,
                  merchant_name=MERCHANT.name, category=MERCHANT.category, mcc=MERCHANT.mcc,
                  kind='amount_off', value='10', source='seed', stackable=True)
    values.update(kwargs)
    return Reward(**values)


def card(i=1, **kwargs):
    values = dict(id=UUID(int=200 + i), user_id=USER, issuer='Bank', network='visa',
                  name=f'Card {i}', base_rate='1')
    values.update(kwargs)
    return Card(**values)


def request(**kwargs):
    values = dict(user_id=USER, merchant_id=MERCHANT.id, domain=MERCHANT.domain, cart_total='100')
    values.update(kwargs)
    return StackRequest(**values)


def solve(rewards=(), cards=(), req=None, **kwargs):
    return solve_stacking(req or request(), list(rewards), list(cards), MERCHANT, now=NOW, **kwargs)


def ids(result):
    return [x.reward_id for x in result.chosen_rewards]


@pytest.mark.parametrize('flags,expected', [((True, False), '10.00'), ((False, False), '10.00'), ((True, True), '20.00')])
def test_bilateral_compatibility(flags, expected):
    result = solve([reward(1, stackable=flags[0]), reward(2, stackable=flags[1])])
    assert result.total_savings == Decimal(expected)
    assert result.solver_status == 'optimal'


def test_unknown_compatibility_and_one_promo_code():
    unknown = Reward.model_validate(reward().model_dump(exclude={'stackable'}))
    assert solve([unknown, reward(2)]).total_savings == 10
    assert len(solve([reward(1, code='A'), reward(2, code='B')]).chosen_rewards) == 1


def test_code_restriction_does_not_block_uncoded_offer():
    result = solve([reward(1, code='A'), reward(2, code='B', value='20'), reward(3)])
    assert result.total_savings == 30
    assert len(result.chosen_rewards) == 2


def test_minimum_spends_are_individual_not_added_or_rechecked_after_discount():
    result = solve([reward(1, min_spend='90'), reward(2, min_spend='90')])
    assert result.final_price == 80
    assert solve([reward(min_spend='100.01')]).final_price == 100


def test_percentage_compounding_caps_and_order():
    result = solve([reward(1, kind='percent_off', value='20'), reward(2, kind='percent_off', value='10'), reward(3)])
    assert result.final_price == 62
    assert [r.savings for r in result.chosen_rewards] == [20, 8, 10]
    assert solve([reward(kind='percent_off', value='50', max_discount='7.25')]).total_savings == Decimal('7.25')
    a, b = reward(1, value='20'), reward(2, kind='percent_off', value='50')
    assert solve([a, b], terms={a.id: RewardTerms(order=-1)}).final_price == 40
    assert solve([a, b]).final_price == 30


def test_half_up_once_per_reward_and_allocation_to_items():
    req = request(cart_total='.15', items=[dict(name='a', category='A', price='.05'),
                                        dict(name='b', category='B', price='.10')])
    result = solve([reward(kind='percent_off', value='10')], req=req)
    assert result.chosen_rewards[0].savings == Decimal('.02')
    assert result.final_price == Decimal('.13')
    assert solve([reward(kind='percent_off', value='33.333333')], req=request(cart_total='.03')).final_price == Decimal('.02')


def test_excluded_items_and_unknown_remainder_never_receive_restricted_discount():
    req = request(items=[dict(name='Regular top', category='Tops', price='50'),
                         dict(name='Gift Cards', category='Gift Cards', price='20')])
    r = reward(kind='percent_off', value='10', exclusions=['Gift Cards'])
    result = solve([r], req=req)
    assert result.chosen_rewards[0].savings == 5
    assert 'unclassified $30.00' in result.explanation
    assert not ids(solve([r.model_copy(update={'min_spend': Decimal('60')})], req=req))
    # An unrestricted discount allocates across all three buckets; a following
    # restricted reward uses only its eligible item's remaining balance.
    a = reward(2, kind='percent_off', value='20')
    assert solve([a, r], req=req, terms={r.id: RewardTerms(order=5)}).final_price == 76


@pytest.mark.parametrize('updates', [dict(status='expired'), dict(status='used'), dict(status='needs_review'),
                                    dict(starts_at=NOW + timedelta(microseconds=1)),
                                    dict(expires_at=NOW), dict(user_id=FOREIGN),
                                    dict(merchant_id=UUID(int=999)), dict(currency='EUR')])
def test_eligibility_filters(updates):
    assert not ids(solve([reward(**updates)]))


def test_start_inclusive_expiration_exclusive_and_urgency_ties():
    early = reward(2, starts_at=NOW, expires_at=NOW + timedelta(microseconds=1), stackable=False)
    late = reward(1, expires_at=NOW + timedelta(days=2), stackable=False)
    assert ids(solve([late, early])) == [early.id]
    assert ids(solve([early, late])) == [early.id]
    # Expiry urgency cannot trade away even one cent of savings.
    assert ids(solve([early, late.model_copy(update={'value': Decimal('10.01')})])) == [late.id]


def test_unknown_merchant_has_no_rewards_and_uses_card_base_only():
    c = card(base_rate='1', category_rates=[dict(category='Clothing', rate='99')])
    result = solve_stacking(request(merchant_id=UUID(int=999), domain='unknown.com'), [reward()], [c], None, now=NOW)
    assert not ids(result)
    assert result.card_cashback == 1


def test_payment_cards_mcc_category_base_and_ownership():
    cards = [card(1, base_rate='1.5'), card(2, category_rates=[dict(category='Clothing', rate='3')]),
             card(3, category_rates=[dict(category='wrong', mcc_codes=['5651'], rate='5')]),
             card(4, category_rates=[dict(category='Clothing', mcc_codes=['5311'], rate='99')]),
             card(5, user_id=FOREIGN, base_rate='100')]
    result = solve([reward(stackable=False)], cards)
    assert result.recommended_card.id == cards[2].id
    assert result.card_cashback == Decimal('4.50')
    assert result.final_price == 90
    assert result.total_savings == Decimal('14.50')


def test_joint_card_choice_can_change_reward_winner():
    cheap_card, good_card = card(1, base_rate='1'), card(2, base_rate='20')
    large, small = reward(1, value='20', stackable=False), reward(2, value='10', stackable=False)
    result = solve([large, small], [cheap_card, good_card], terms={large.id: RewardTerms(allowed_card_ids=frozenset([cheap_card.id]))})
    assert ids(result) == [small.id]
    assert result.recommended_card.id == good_card.id
    assert result.total_savings == 28


def test_explicit_payment_restrictions_and_suppression():
    visa, amex = card(1, base_rate='5'), card(2, network='amex', issuer='Other', base_rate='10')
    r = reward(stackable=False)
    result = solve([r], [visa, amex], terms={r.id: RewardTerms(allowed_networks=frozenset(['visa']))})
    assert result.recommended_card.id == visa.id
    assert result.total_savings == Decimal('14.50')
    assert not ids(solve([r], terms={r.id: RewardTerms(allowed_issuers=frozenset(['Bank']))}))
    result = solve([r], [visa], terms={r.id: RewardTerms(suppress_card_cashback=True)})
    assert result.card_cashback == 0
    assert result.final_price == 90


def test_pair_specific_restrictions_require_both_sides():
    a, b = reward(1), reward(2)
    assert solve([a, b], terms={a.id: RewardTerms(compatible_reward_ids=frozenset([b.id])),
                              b.id: RewardTerms(compatible_reward_ids=frozenset())}).total_savings == 10


def test_membership_program_tier_owner_and_expiry():
    r = reward()
    terms = {r.id: RewardTerms(membership_program='Club', membership_tier='Gold')}
    m = Membership(id=UUID(int=88), user_id=USER, merchant_id=MERCHANT.id,
                   merchant_name='Test Store', program_name='Club', tier='Gold')
    assert not ids(solve([r], terms=terms))
    assert ids(solve([r], terms=terms, memberships=[m])) == [r.id]
    for update in [dict(user_id=FOREIGN), dict(is_active=False), dict(tier='Silver'),
                   dict(expires_at=NOW), dict(merchant_id=UUID(int=9))]:
        assert not ids(solve([r], terms=terms, memberships=[m.model_copy(update=update)]))
    assert solve([], memberships=[m.model_copy(update={'annual_reward_rate': Decimal('100')})]).total_savings == 0


def test_reward_cashback_distinct_from_coupon_and_payment_earnings():
    discount, cashback = reward(1), reward(2, kind='cashback', value='10')
    result = solve([discount, cashback], [card(base_rate='5')], terms={cashback.id: RewardTerms(cashback_unit='percent')})
    assert result.final_price == 90
    assert [r.savings for r in result.chosen_rewards] == [10, 9]
    assert result.card_cashback == Decimal('4.50')
    assert result.total_savings == Decimal('23.50')
    assert solve([cashback], terms={cashback.id: RewardTerms(cashback_unit='amount')}).total_savings == 10
    ambiguous = solve([cashback])
    assert not ids(ambiguous)
    assert 'cashback unit is unknown' in ambiguous.explanation


@pytest.mark.parametrize('kind', ['points', 'free_item', 'bogo'])
def test_no_invented_redemption_values(kind):
    result = solve([reward(kind=kind, value='150')])
    assert not ids(result)
    assert 'unsupported' in result.explanation


def test_zero_cart_no_rewards_no_cards_and_oversized_fixed_discount():
    result = solve([reward()], req=request(cart_total='0'))
    assert result.final_price == result.total_savings == result.savings_percent == 0
    assert solve().recommended_card is None
    assert solve([reward(value='200')]).final_price == 0
    assert solve([], [card(base_rate='5')]).total_savings == 5


@pytest.mark.parametrize('kwargs', [dict(cart_total='-1'), dict(cart_total='1.001'), dict(cart_total='1000001'),
                                   dict(items=[dict(name='x', price='1', quantity=0)]),
                                   dict(items=[dict(name='x', price='1', quantity=-1)]),
                                   dict(items=[dict(name='x', price='-1')]),
                                   dict(items=[dict(name='x', price='101')])])
def test_invalid_cart_values(kwargs):
    with pytest.raises(ValueError):
        solve(req=request(**kwargs))


def test_solver_timeout_is_never_called_optimal():
    result = solve([reward()], time_limit=0)
    assert result.solver_status == 'reference_verified_solver_timeout'
    assert result.final_price == 90
    with pytest.raises(SolverUnavailable):
        solve([reward(i) for i in range(9)], time_limit=0)


def test_reference_mismatch_never_returns_optimal(monkeypatch):
    from dataclasses import replace
    from backend.decisions.stacking import optimizer
    real = optimizer.exhaustive
    monkeypatch.setattr(optimizer, 'exhaustive', lambda p: replace(real(p), key=(999999,)))
    with pytest.raises(VerificationError):
        solve([reward()])


def test_deterministic_random_solver_reference_agreement():
    rng = random.Random(90421)
    for case in range(35):
        rewards = [reward(i, kind=rng.choice(['amount_off', 'percent_off', 'cashback']),
                          value=str(rng.randrange(1, 35)), stackable=rng.choice([True, True, False]),
                          code=('CODE' + str(i)) if rng.choice([False, True]) else None,
                          min_spend=str(rng.randrange(0, 120)),
                          max_discount=str(rng.randrange(1, 25)),
                          exclusions=['B'] if rng.choice([False, True]) else [])
                   for i in range(5)]
        cards = [card(1, base_rate='1.5'), card(2, base_rate='7')]
        terms = {r.id: RewardTerms(cashback_unit=rng.choice(['amount', 'percent']),
                                  allowed_card_ids=frozenset([cards[0].id]) if rng.randrange(4) == 0 else None)
                 for r in rewards}
        req = request(items=[dict(name='a', category='A', price='45.03'),
                             dict(name='b', category='B', price='50.07')])
        problem = prepare(req, rewards, cards, [], MERCHANT, now=NOW, terms=terms)
        actual, status = optimize(problem, time_limit=10)
        assert status == 'optimal', case
        assert actual == exhaustive(problem), case


def seed_data():
    fixture = json.loads((SEED / 'fixtures' / 'hollister_500_cart.json').read_text())
    rewards = [Reward.model_validate(r) for r in json.loads((SEED / 'seed_rewards.json').read_text())['rewards']]
    cards = [Card.model_validate(c) for c in json.loads((SEED / 'seed_cards.json').read_text())['cards']]
    merchants = [Merchant.model_validate(m) for m in json.loads((SEED / 'seed_merchants.json').read_text())['merchants']]
    merchant = next(m for m in merchants if m.domain == 'hollisterco.com')
    return StackRequest.model_validate(fixture['request']), rewards, cards, merchant


def test_hollister_golden_with_explicit_eligibility_and_rate_corrections():
    req, rewards, cards, merchant = seed_data()
    voucher = rewards[0]
    cash_plus = cards[-1]
    # Required shared seed corrections, deliberately not applied to shared files:
    # add MCC 5651 to the DEMO rate; establish remainder passes exclusions.
    cash_plus.category_rates[0].mcc_codes.append('5651')
    result = solve_stacking(req, rewards, cards, merchant, now=NOW,
                            terms={voucher.id: RewardTerms(remainder_eligible=True)})
    assert result.chosen_rewards[0].savings == Decimal('50.00')
    assert result.final_price == Decimal('450.00')
    assert result.card_cashback == Decimal('22.50')
    assert result.total_savings == Decimal('72.50')
    assert result.savings_percent == Decimal('14.50')
    assert result.recommended_card.id == cash_plus.id
    assert result.solver_status == 'optimal'


def test_unmodified_hollister_seed_never_fabricates_eligibility_or_card_rate():
    req, rewards, cards, merchant = seed_data()
    result = solve_stacking(req, rewards, cards, merchant, now=NOW)
    assert result.chosen_rewards[0].savings == Decimal('47.97')
    assert result.final_price == Decimal('452.03')
    assert result.card_cashback == Decimal('6.78')
    assert result.total_savings == Decimal('54.75')
    assert result.recommended_card.name == 'Freedom Unlimited (DEMO)'


class FakeRepo:
    def __init__(self, rewards=(), cards=()):
        self.rewards, self.cards = list(rewards), list(cards)
        self.revealed = []

    async def resolve_merchant(self, merchant_id=None, domain=None):
        if merchant_id and domain and domain != MERCHANT.domain:
            raise ValueError('conflict')
        return MERCHANT if merchant_id == MERCHANT.id or domain == MERCHANT.domain else None

    async def list_rewards(self, **kwargs):
        return [r.model_copy(update={'code': None}) for r in self.rewards]

    async def get_reward(self, reward_id, reveal_code=False):
        self.revealed.append(reveal_code)
        return next(r for r in self.rewards if r.id == reward_id)

    async def get_wallet(self, **kwargs):
        return Wallet(user_id=USER, cards=self.cards)


class FakeDatabase:
    def __init__(self, repo):
        self.repo, self.users = repo, []

    @asynccontextmanager
    async def transaction(self, user_id):
        self.users.append(user_id)
        yield self.repo


def client(repo=None):
    app = FastAPI()
    app.include_router(router)
    database = FakeDatabase(repo or FakeRepo())
    app.dependency_overrides[get_database] = lambda: database
    return TestClient(app), database


def test_http_router_independent_di_and_redacted_code_reveal():
    repo = FakeRepo([reward(1, code='A'), reward(2, code='B')], [card()])
    http, db = client(repo)
    response = http.post('/stack', json=request().model_dump(mode='json'))
    assert response.status_code == 200, response.text
    assert len(response.json()['chosen_rewards']) == 1
    assert response.json()['solver_status'] == 'optimal'
    assert repo.revealed == [True, True]
    assert db.users == [USER]


def test_http_conflicting_identity_and_merchants_invalid_cart_and_missing_db():
    http, _ = client()
    body = request().model_dump(mode='json')
    assert http.post('/stack', json=body, headers={'X-User-Id': str(FOREIGN)}).status_code == 400
    assert http.post('/stack', json={**body, 'domain': 'wrong.com'}).status_code == 400
    assert http.post('/stack', json={**body, 'cart_total': '-1'}).status_code == 422
    assert http.post('/stack', json={**body, 'merchant_id': None, 'domain': None}).status_code == 422
    app = FastAPI()
    app.include_router(router)
    assert TestClient(app).post('/stack', json=body).status_code == 503


def test_http_failed_verification_is_503(monkeypatch):
    from backend.decisions.stacking import router as module
    def fail(*args, **kwargs):
        raise VerificationError('mismatch')
    monkeypatch.setattr(module, 'solve_stacking', fail)
    http, _ = client()
    assert http.post('/stack', json=request().model_dump(mode='json')).status_code == 503


def test_feasible_solver_response_never_reports_optimal(monkeypatch):
    from ortools.sat.python import cp_model
    real_solve = cp_model.CpSolver.solve
    def feasible(self, model, *args, **kwargs):
        assert real_solve(self, model, *args, **kwargs) == cp_model.OPTIMAL
        return cp_model.FEASIBLE
    monkeypatch.setattr(cp_model.CpSolver, 'solve', feasible)
    result = solve([reward()])
    assert result.solver_status == 'feasible'
    assert 'optimality was not established' in result.explanation


def test_timeout_during_tie_breaking_retains_feasible_result(monkeypatch):
    from ortools.sat.python import cp_model
    real_solve = cp_model.CpSolver.solve
    calls = []
    def expire(self, model, *args, **kwargs):
        calls.append(1)
        return real_solve(self, model, *args, **kwargs) if len(calls) == 1 else cp_model.UNKNOWN
    monkeypatch.setattr(cp_model.CpSolver, 'solve', expire)
    assert solve([reward()]).solver_status == 'feasible'


@pytest.mark.parametrize('updates', [dict(value='-1'), dict(value='1.0000001', kind='percent_off'),
                                    dict(value='101', kind='percent_off'), dict(value='1.001'),
                                    dict(max_discount='-.01'), dict(min_spend='1.001')])
def test_invalid_reward_money_and_rates(updates):
    with pytest.raises(ValueError):
        solve([reward(**updates)])


def test_large_invalid_amounts_and_card_rates_are_validation_errors():
    with pytest.raises(ValueError):
        solve(req=request(cart_total='1e100'))
    with pytest.raises(ValueError):
        solve(cards=[card(base_rate='101')])
    with pytest.raises(ValueError):
        solve(cards=[card(category_rates=[dict(category='Clothing', rate='1.0000001')])])


def test_direct_service_rejects_conflicting_merchant_and_duplicate_records():
    with pytest.raises(ValueError):
        solve(req=request(domain='wrong.com'))
    with pytest.raises(ValueError):
        solve([reward(), reward()])
    with pytest.raises(ValueError):
        solve(cards=[card(), card()])
    assert solve(req=request(domain='https://WWW.TEST.COM./checkout')).final_price == 100


def test_http_rejects_fractional_boolean_and_nonfinite_quantities_or_amounts():
    http, _ = client()
    body = request().model_dump(mode='json')
    for quantity in [True, 1.5, 0, -1]:
        response = http.post('/stack', json={**body, 'items': [dict(name='x', price='1', quantity=quantity)]})
        assert response.status_code == 422
    for amount in ['NaN', 'Infinity', '1e100', '1.001']:
        assert http.post('/stack', json={**body, 'cart_total': amount}).status_code == 422


def test_reference_bound_includes_eight_rewards_and_all_card_options():
    rewards = [reward(i, kind='percent_off', value='5') for i in range(8)]
    problem = prepare(request(), rewards, [card(1, base_rate='1'), card(2, base_rate='5')], [], MERCHANT, now=NOW)
    actual, status = optimize(problem)
    assert actual == exhaustive(problem)
    assert len(actual.selected) == 8
    assert actual.card_index == 2
    assert status == 'optimal'
