""""Use it before you lose it": pure rule helpers plus /lookup and /stack
wiring, end-to-end through the merchant demo console (in-memory mode).
"""
import math
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.schemas import Reward, ScoredReward
from backend.decisions.use_first import apply_use_first, stack_exclusions, value_label

DEMO = '00000000-0000-0000-0000-000000000001'
USER = UUID(DEMO)
NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
MERCHANT_ID = uuid4()
HCOFALL10_EXPIRES = datetime(2026, 10, 20, 23, 59, 59, tzinfo=timezone.utc)  # seed


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


def make_reward(**updates):
    data = dict(id=uuid4(), user_id=USER, merchant_id=MERCHANT_ID, merchant_name='Shop',
                category='Family Clothing Stores', mcc='5651', kind='percent_off',
                value='10.00', source='manual', stackable=False,
                created_at=NOW, updated_at=NOW)
    data.update(updates)
    return Reward(**data)


def scored(reward, score):
    return ScoredReward(reward=reward, score=score, value_component=0.5,
                        match_component=1.0, urgency_component=1.0)


def expiry_phrase(days):
    return 'today' if days == 0 else ('in 1 day' if days == 1 else f'in {days} days')


# ---------------------------------------------------------------------------
# Pure rule
# ---------------------------------------------------------------------------

def test_value_label_all_kinds():
    assert value_label(make_reward(kind='percent_off', value='25.00')) == '25% off'
    assert value_label(make_reward(kind='amount_off', value='5.00')) == '$5.00 off'
    assert value_label(make_reward(kind='cashback', value='2.00')) == '$2.00 cashback'
    assert value_label(make_reward(kind='points', value='150.00')) == '150 points'
    assert value_label(make_reward(kind='free_item', value='1.00')) == 'Free item'
    assert value_label(make_reward(kind='bogo', value='1.00')) == 'BOGO'


def test_rule_applies_at_boundary_7_days_and_plus_14():
    a = make_reward(kind='amount_off', value='5.00', code='A5',
                    expires_at=NOW + timedelta(days=7))
    b = make_reward(kind='percent_off', value='25.00', code='B25',
                    expires_at=NOW + timedelta(days=7) + timedelta(days=14))
    out = apply_use_first([scored(b, 2.0), scored(a, 1.0)], NOW)

    assert [s.reward.id for s in out] == [a.id, b.id]  # A reordered first
    first, later = out
    assert first.use_first and not first.save_for_later
    b_date = (NOW + timedelta(days=21)).strftime('%b %-d')  # Nov 8
    assert first.recommendation == (
        f'Use first: expires in 7 days. Your 25% off is good until {b_date}.')
    assert later.save_for_later and not later.use_first
    assert later.recommendation == f'Save for later — good until {b_date}'


def test_rule_not_applied_at_8_days_or_13_day_gap():
    # A at 8 days: outside the expiring window.
    a8 = make_reward(code='A', expires_at=NOW + timedelta(days=8))
    b = make_reward(code='B', expires_at=NOW + timedelta(days=60))
    items = [scored(b, 2.0), scored(a8, 1.0)]
    assert apply_use_first(items, NOW) == items

    # B only 13 days after A: not enough safety gap.
    a = make_reward(code='A', expires_at=NOW + timedelta(days=3))
    b13 = make_reward(code='B', expires_at=NOW + timedelta(days=3) + timedelta(days=13))
    items = [scored(b13, 2.0), scored(a, 1.0)]
    assert apply_use_first(items, NOW) == items
    for item in apply_use_first(items, NOW):
        assert not item.use_first and not item.save_for_later
        assert item.recommendation is None


def test_rule_not_applied_when_rewards_can_combine():
    # Both stackable with at most one code: they can share one order.
    a = make_reward(code='A', stackable=True, expires_at=NOW + timedelta(days=2))
    b = make_reward(code=None, stackable=True, expires_at=NOW + timedelta(days=60))
    items = [scored(b, 2.0), scored(a, 1.0)]
    assert apply_use_first(items, NOW) == items


def test_rule_not_applied_across_different_merchants():
    a = make_reward(code='A', expires_at=NOW + timedelta(days=2))
    b = make_reward(code='B', merchant_id=uuid4(), expires_at=NOW + timedelta(days=60))
    items = [scored(b, 2.0), scored(a, 1.0)]
    assert apply_use_first(items, NOW) == items


def test_never_expiring_b_wording():
    a = make_reward(kind='amount_off', value='5.00', code='A5',
                    expires_at=NOW + timedelta(days=2))
    b = make_reward(kind='percent_off', value='25.00', code='B25', expires_at=None)
    first, later = apply_use_first([scored(b, 2.0), scored(a, 1.0)], NOW)
    assert first.recommendation == 'Use first: expires in 2 days. Your 25% off is not expiring.'
    assert later.recommendation == 'Save for later — no expiration'


def test_stack_exclusions_sentence_and_no_op():
    a = make_reward(kind='amount_off', value='5.00', code='A5',
                    expires_at=NOW + timedelta(days=2))
    b = make_reward(kind='percent_off', value='25.00', code='B25',
                    expires_at=NOW + timedelta(days=30))
    excluded, note = stack_exclusions([a, b], MERCHANT_ID, NOW)
    b_date = (NOW + timedelta(days=30)).strftime('%b %-d')
    assert excluded == {b.id}
    assert note == f'Saved for later: 25% off (B25) — good until {b_date}.'

    # No code -> no parenthetical.
    b_nocode = make_reward(kind='points', value='150.00', code=None,
                           expires_at=NOW + timedelta(days=30))
    excluded, note = stack_exclusions([a, b_nocode], MERCHANT_ID, NOW)
    assert excluded == {b_nocode.id}
    assert note == f'Saved for later: 150 points — good until {b_date}.'

    # No merchant or no qualifying pair -> exactly the old behavior.
    assert stack_exclusions([a, b], None, NOW) == (set(), None)
    assert stack_exclusions([a], MERCHANT_ID, NOW) == (set(), None)


# ---------------------------------------------------------------------------
# End-to-end: Hollister demo (seed HCOFALL10 + injected HCOWINTER25)
# ---------------------------------------------------------------------------

def _inject_hcowinter25(client):
    """Send the templated demo email through the merchant console."""
    response = client.post('/demo/console/send', json={
        'template_id': 'hollister_10',
        'overrides': {'value': 25, 'code': 'HCOWINTER25', 'expiry_days': 30},
        'mode': 'instant',
        'force': True,
    })
    assert response.status_code == 200, response.text
    rewards = response.json()['rewards']
    assert [r['code'] for r in rewards] == ['HCOWINTER25'], rewards
    return datetime.fromisoformat(rewards[0]['expires_at'])


def test_lookup_orders_expiring_hollister_reward_first(client):
    winter_expires = _inject_hcowinter25(client)
    now = datetime.now(timezone.utc)

    body = client.post('/lookup', json={'user_id': DEMO, 'domain': 'hollisterco.com',
                                        'limit': 10},
                       headers={'X-User-Id': DEMO}).json()
    assert body['merchant']['name'] == 'Hollister'

    # HCOFALL10 scores lower (10% vs 25%) but must be ranked first.
    first = body['rewards'][0]
    assert first['reward']['code'] == 'HCOFALL10'
    assert first['use_first'] and not first['save_for_later']
    days = math.floor((HCOFALL10_EXPIRES - now).total_seconds() / 86400)
    b_date = winter_expires.strftime('%b %-d')  # Nov 17 when run on Oct 18
    assert first['recommendation'] == (
        f'Use first: expires {expiry_phrase(days)}. Your 25% off is good until {b_date}.')

    winter = next(s for s in body['rewards'] if s['reward']['code'] == 'HCOWINTER25')
    assert winter['save_for_later'] and not winter['use_first']
    assert winter['recommendation'] == f'Save for later — good until {b_date}'


def test_stack_spends_expiring_reward_and_explains(client):
    winter_expires = _inject_hcowinter25(client)
    b_date = winter_expires.strftime('%b %-d')
    request = {'user_id': DEMO, 'domain': 'hollisterco.com',
               'cart_total': '500.00', 'items': []}

    data = client.post('/stack', headers={'X-User-Id': DEMO}, json=request).json()
    # The 25% code would save more now, but it is withheld for later.
    assert [c['reward']['code'] for c in data['chosen_rewards']] == ['HCOFALL10']
    sentence = f'Saved for later: 25% off (HCOWINTER25) — good until {b_date}.'
    assert sentence in data['explanations']
    assert data['explanation'].endswith(sentence)

    # Opting out restores pure savings maximization: the 25% code wins.
    data = client.post('/stack', headers={'X-User-Id': DEMO},
                       json={**request, 'prefer_expiring': False}).json()
    assert [c['reward']['code'] for c in data['chosen_rewards']] == ['HCOWINTER25']
    assert not any('Saved for later' in line for line in data['explanations'])
    assert 'Saved for later' not in data['explanation']
