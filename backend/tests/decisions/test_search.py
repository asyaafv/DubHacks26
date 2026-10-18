"""Reward search: /search + /search/suggestions over the in-memory demo store,
plus pure service-level matching/ranking and the optional semantic layer."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.schemas import (
    Card, CardNetwork, CategoryRate, Merchant, Reward, RewardKind,
    RewardSource, RewardStatus,
)
from backend.decisions.search.service import search_rewards, suggest_chips

DEMO = '00000000-0000-0000-0000-000000000001'
OTHER = '00000000-0000-0000-0000-000000000002'
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


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


def _search(client, query, user=DEMO, **extra):
    return client.post('/search', json={'query': query, **extra},
                       headers={'X-User-Id': user})


def _names(body):
    return [hit['reward']['merchant_name'] for hit in body['results']]


# ---------------------------------------------------------------------------
# Endpoint behavior (in-memory mode, seeded demo user)
# ---------------------------------------------------------------------------

def test_mexican_food_maps_to_restaurant_mccs(client):
    body = _search(client, 'mexican food').json()
    names = _names(body)
    assert 'Taco Bell' in names and 'Chipotle' in names
    # Only food merchants: no clothing/electronics leak in.
    assert not {'Gap', 'Hollister', 'Best Buy', 'Sephora'} & set(names)
    assert body['total_active'] > body['total_matched'] > 0
    for hit in body['results']:
        assert hit['reason']
        assert hit['score'] == pytest.approx(
            hit['value_component'] * hit['match_component'] * hit['urgency_component'])


def test_streetwear_maps_to_clothing_and_shoes(client):
    names = _names(_search(client, 'streetwear').json())
    assert 'Nike' in names  # shoes included
    assert {'Gap', 'Hollister'} & set(names)  # family clothing included


def test_broad_terms_food_and_clothing(client):
    food = _search(client, 'food').json()
    assert set(_names(food)) <= {'McDonald\'s', 'Taco Bell', 'Chipotle', 'Starbucks',
                                 'Uber Eats', 'Domino\'s Pizza'}
    assert len(food['results']) >= 5
    clothing = _search(client, 'clothing').json()
    assert {'Gap', 'Hollister', 'Abercrombie & Fitch', 'H&M', 'Old Navy'} == set(_names(clothing))


def test_merchant_name_outranks_category_matches(client):
    body = _search(client, 'hollister rewards').json()
    assert _names(body)[0] == 'Hollister'
    top = body['results'][0]
    assert top['match_component'] == 1.0
    assert top['reward']['code'] == 'HCOFALL10'
    assert top['expiring_soon'] is True  # Oct 20 expiry vs mid-Oct demo clock


def test_fuzzy_typo_still_matches(client):
    names = _names(_search(client, 'cloths').json())
    assert 'Gap' in names or 'Hollister' in names


def test_results_include_code_expiry_and_best_card(client):
    body = _search(client, 'clothing').json()
    for hit in body['results']:
        assert hit['reward']['code']
        assert hit['days_until_expiry'] is not None
        # US Bank Cash+ pays 5% on MCC 5651 in the demo wallet.
        assert hit['best_card']['name'] == 'US Bank Cash+ (DEMO)'
        assert float(hit['best_card']['rate']) == 5.0


def test_used_and_needs_review_rewards_are_excluded(client):
    body = _search(client, 'clothing', limit=20).json()
    codes = {hit['reward']['code'] for hit in body['results']}
    assert 'PACSUN25' not in codes and 'AERO30' not in codes  # used
    body = _search(client, 'department', limit=20).json()
    assert 'FRIENDS30' not in {h['reward']['code'] for h in body['results']}  # needs_review


def test_no_match_returns_empty_not_error(client):
    body = _search(client, 'zzgibberishqq').json()
    assert body['results'] == [] and body['total_matched'] == 0
    assert body['total_active'] > 0


def test_other_user_sees_no_results(client):
    body = _search(client, 'food', user=OTHER).json()
    assert body['results'] == [] and body['total_active'] == 0


def test_query_validation(client):
    assert _search(client, '   ').status_code == 400
    assert client.post('/search', json={}, headers={'X-User-Id': DEMO}).status_code == 422
    assert _search(client, 'food', limit=50).status_code == 422


def test_suggestions_reflect_seeded_categories(client):
    chips = client.get('/search/suggestions', headers={'X-User-Id': DEMO}).json()['chips']
    by_label = {c['label']: c for c in chips}
    assert by_label['Food']['count'] >= 5
    assert by_label['Clothing']['query'] == 'clothing'
    assert by_label['Streetwear']['count'] > by_label['Shoes']['count']
    # Chips only appear for categories the user actually has rewards in.
    other = client.get('/search/suggestions', headers={'X-User-Id': OTHER}).json()
    assert other['chips'] == []


# ---------------------------------------------------------------------------
# Service-level: ranking, eligibility, semantic fallback
# ---------------------------------------------------------------------------

def _reward(**overrides):
    base = dict(
        id=uuid4(), user_id=DEMO, merchant_id=None, merchant_name='Chipotle',
        category='Eating Places & Restaurants', mcc='5812',
        kind=RewardKind.percent_off, value='10', currency='USD',
        source=RewardSource.manual, status=RewardStatus.active,
        created_at=NOW, updated_at=NOW,
    )
    base.update(overrides)
    return Reward.model_validate(base)


def test_urgency_breaks_value_ties():
    soon = _reward(expires_at=NOW + timedelta(days=1))
    later = _reward(expires_at=NOW + timedelta(days=30))
    hits, matched, active = search_rewards(
        'food', rewards=[later, soon], merchants=[], cards=[], now=NOW)
    assert matched == active == 2
    assert [h.reward.id for h in hits] == [soon.id, later.id]
    assert hits[0].expiring_soon and not hits[1].expiring_soon


def test_value_outranks_within_same_match_and_urgency():
    big = _reward(value='40', expires_at=NOW + timedelta(days=10))
    small = _reward(value='5', expires_at=NOW + timedelta(days=10))
    hits, _, _ = search_rewards('food', rewards=[small, big], merchants=[], cards=[], now=NOW)
    assert hits[0].reward.id == big.id


def test_expired_and_future_rewards_never_match():
    rewards = [
        _reward(expires_at=NOW - timedelta(seconds=1)),
        _reward(starts_at=NOW + timedelta(days=1)),
        _reward(status=RewardStatus.expired),
    ]
    hits, matched, active = search_rewards(
        'food', rewards=rewards, merchants=[], cards=[], now=NOW)
    assert hits == [] and matched == 0 and active == 0


def test_merchant_alias_matches_via_catalog():
    merchant = Merchant(id=uuid4(), name='Abercrombie & Fitch', domain='abercrombie.com',
                        category='Family Clothing Stores', mcc='5651', aliases=['A&F'])
    reward = _reward(merchant_id=merchant.id, merchant_name='Abercrombie & Fitch',
                     category='Family Clothing Stores', mcc='5651')
    hits, _, _ = search_rewards("a&f", rewards=[reward], merchants=[merchant],
                                cards=[], now=NOW)
    assert hits and hits[0].match_component == 1.0


def test_best_card_uses_mcc_rate_over_base():
    dining = Card(id=uuid4(), user_id=DEMO, issuer='Chase', network=CardNetwork.visa,
                  name='Sapphire', base_rate='1.0',
                  category_rates=[CategoryRate(category='Dining', mcc_codes=['5812'], rate='3.0')],
                  created_at=NOW)
    flat = Card(id=uuid4(), user_id=DEMO, issuer='Citi', network=CardNetwork.mastercard,
                name='Double', base_rate='2.0', category_rates=[], created_at=NOW)
    hits, _, _ = search_rewards('food', rewards=[_reward()], merchants=[],
                                cards=[dining, flat], now=NOW)
    assert hits[0].best_card.name == 'Chase Sapphire'
    assert float(hits[0].best_card.rate) == 3.0


def test_semantic_similarities_rescue_unmatched_rewards():
    exotic = _reward(merchant_name='Blue Bottle', category='Coffee Houses', mcc='5499')
    hits, _, _ = search_rewards('artisanal pour over', rewards=[exotic], merchants=[],
                                cards=[], now=NOW, similarities={exotic.id: 0.8})
    assert hits and hits[0].match_component == pytest.approx(0.8)
    assert 'similar' in hits[0].reason.casefold()
    # Below the floor, the semantic layer stays silent.
    hits, _, _ = search_rewards('artisanal pour over', rewards=[exotic], merchants=[],
                                cards=[], now=NOW, similarities={exotic.id: 0.2})
    assert hits == []


def test_suggest_chips_counts_only_eligible():
    rewards = [
        _reward(),  # active restaurant
        _reward(status=RewardStatus.used),
        _reward(category='Family Clothing Stores', mcc='5651',
                expires_at=NOW - timedelta(days=1)),  # expired clothing
    ]
    chips = suggest_chips(rewards, now=NOW)
    labels = {c.label: c.count for c in chips}
    assert labels['Food'] == 1
    assert 'Clothing' not in labels
