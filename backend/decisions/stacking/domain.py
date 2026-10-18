"""Internal terms and validated inputs; public contracts remain unchanged."""
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, DecimalException
from uuid import UUID

from backend.app.schemas import Card, Membership, Merchant, Reward, StackRequest
from backend.decisions.common import canonical_domain, card_rate, exact_number, utc

SCALE = 100_000_000  # six decimal places of percentage points
MAX_CENTS = 100_000_000  # bounds products below CP-SAT's signed int64 limit


def cents(value):
    try:
        numeric = Decimal(str(value))
        if not numeric.is_finite() or numeric < 0 or numeric > MAX_CENTS // 100:
            raise ValueError('Money must be finite, nonnegative, and at most $1,000,000')
        return int(exact_number(numeric, 2) * 100)
    except DecimalException:
        raise ValueError('Invalid monetary amount') from None


def rate(value):
    try:
        numeric = Decimal(str(value))
        if not numeric.is_finite() or not 0 <= numeric <= 100:
            raise ValueError('Rate must be finite and between zero and 100 percent')
        return int(exact_number(numeric, 6, maximum=100) * 1_000_000)
    except DecimalException:
        raise ValueError('Invalid percentage rate') from None


def dollars(value):
    return (Decimal(value) / 100).quantize(Decimal('.01'))


@dataclass(frozen=True)
class RewardTerms:
    """Trusted normalized terms, never inferred from benefit text or reward names.

    Default order: percentage discounts, fixed discounts, then reward cashback.
    Each threshold uses ORIGINAL eligible merchandise, independently of other offers.
    Cashback requires an explicit unit. Card earnings use FINAL checkout merchandise.
    """
    order: int | None = None
    cashback_unit: str | None = None  # 'amount' dollars or 'percent' percentage points
    membership_program: str | None = None
    membership_tier: str | None = None
    allowed_card_ids: frozenset[UUID] | None = None
    allowed_networks: frozenset[str] | None = None
    allowed_issuers: frozenset[str] | None = None
    suppress_card_cashback: bool = False
    remainder_eligible: bool = False  # explicit evidence for unclassified merchandise
    compatible_reward_ids: frozenset[UUID] | None = None


@dataclass(frozen=True)
class Offer:
    reward: Reward
    terms: RewardTerms
    buckets: tuple[int, ...]
    percent: int | None
    amount: int
    cap: int


@dataclass
class Problem:
    request: StackRequest
    total: int
    balances: tuple[int, ...]
    offers: list[Offer]
    cards: list[Card | None]
    rates: list[int]
    notes: list[str] = field(default_factory=list)


def compatible(a, b):
    return (a.reward.stackable is True and b.reward.stackable is True
            and (a.terms.compatible_reward_ids is None or b.reward.id in a.terms.compatible_reward_ids)
            and (b.terms.compatible_reward_ids is None or a.reward.id in b.terms.compatible_reward_ids))


def card_allowed(offer, card):
    t = offer.terms
    if card is None:
        return t.allowed_card_ids is None and t.allowed_networks is None and t.allowed_issuers is None
    return ((t.allowed_card_ids is None or card.id in t.allowed_card_ids)
            and (t.allowed_networks is None or card.network.value in t.allowed_networks)
            and (t.allowed_issuers is None or card.issuer.casefold() in {v.casefold() for v in t.allowed_issuers}))


def urgency(reward):
    return (utc(reward.expires_at).isoformat() if reward.expires_at else '9999', str(reward.id))


def prepare(request: StackRequest, rewards: list[Reward], cards: list[Card],
            memberships: list[Membership], merchant: Merchant | None, *,
            now: datetime | None = None, terms: dict[UUID, RewardTerms] | None = None):
    now, terms = utc(now), terms or {}
    if not request.merchant_id and not request.domain:
        raise ValueError('Supply merchant_id or domain')
    total = cents(request.cart_total)
    if len(request.items) > 64 or len(rewards) > 64 or len(cards) > 32:
        raise ValueError('Supported limits: 64 cart lines, 64 rewards, 32 cards')
    balances = []
    for item in request.items:
        if item.quantity <= 0 or item.quantity > 1_000_000:
            raise ValueError('Item quantities must be positive and bounded')
        balances.append(cents(item.price) * item.quantity)
    if sum(balances) > total:
        raise ValueError('Item subtotal exceeds authoritative cart total')
    balances.append(total - sum(balances))  # partial-cart remainder is a separate bucket
    problem = Problem(request, total, tuple(balances), [], [None], [0])
    if merchant and ((request.merchant_id and request.merchant_id != merchant.id)):
        raise ValueError('Merchant ID disagrees with resolved merchant')
    if merchant and request.domain and canonical_domain(request.domain) not in {
        canonical_domain(v) for v in [merchant.domain, *merchant.aliases]
    }:
        raise ValueError('Merchant domain disagrees with resolved merchant')
    if len({c.id for c in cards}) != len(cards):
        raise ValueError('Duplicate card ID')
    for card in sorted(cards, key=lambda c: str(c.id)):
        if card.user_id != request.user_id:
            continue
        rate(card.base_rate)
        for bonus in card.category_rates:
            rate(bonus.rate)
        problem.cards.append(card)
        problem.rates.append(rate(card_rate(card, merchant.category if merchant else None,
                                                merchant.mcc if merchant else None)))
    seen = set()
    for reward in rewards:
        if reward.id in seen:
            raise ValueError('Duplicate reward ID')
        seen.add(reward.id)
        if reward.user_id != request.user_id or merchant is None or reward.merchant_id != merchant.id:
            continue
        if (reward.status.value != 'active' or reward.currency != 'USD'
                or (reward.starts_at and utc(reward.starts_at) > now)
                or (reward.expires_at and utc(reward.expires_at) <= now)):
            continue
        t = terms.get(reward.id, RewardTerms())
        if reward.kind.value in ('points', 'bogo', 'free_item'):
            problem.notes.append(f'Reward {reward.id}: unsupported redemption/cart information.')
            continue
        if reward.kind.value == 'cashback' and t.cashback_unit not in ('amount', 'percent'):
            problem.notes.append(f'Reward {reward.id}: cashback unit is unknown; excluded.')
            continue
        if t.membership_tier and not t.membership_program:
            raise ValueError('Membership tier requires a program')
        if t.membership_program and not any(
            m.user_id == request.user_id and m.merchant_id == merchant.id and m.is_active
            and (not m.expires_at or utc(m.expires_at) > now)
            and m.program_name.casefold() == t.membership_program.casefold()
            and (not t.membership_tier or (m.tier or '').casefold() == t.membership_tier.casefold())
            for m in memberships
        ):
            continue
        excluded = [s.strip().casefold() for s in reward.exclusions]
        # Literal item/category exclusions only. Unknown remainder/categories never
        # establish eligibility for restricted offers. No scaling partial cart lines.
        buckets = tuple(i for i, item in enumerate(request.items)
                        if not excluded or (item.category and not any(
                            s in item.name.casefold() or s in item.category.casefold() for s in excluded)))
        if not excluded or t.remainder_eligible:
            buckets += (len(balances) - 1,)
        eligible = sum(balances[i] for i in buckets)
        if excluded and balances[-1] and not t.remainder_eligible:
            problem.notes.append(f'Reward {reward.id}: unclassified ${dollars(balances[-1])} excluded from eligible subtotal.')
        minimum = cents(reward.min_spend) if reward.min_spend is not None else 0
        cap = cents(reward.max_discount) if reward.max_discount is not None else total
        percent = (rate(reward.value) if reward.kind.value == 'percent_off'
                   or (reward.kind.value == 'cashback' and t.cashback_unit == 'percent') else None)
        amount = cents(reward.value) if percent is None else 0
        if eligible and eligible >= minimum and (percent or amount) and cap:
            problem.offers.append(Offer(reward, t, buckets, percent, amount, cap))
    problem.offers.sort(key=lambda o: (
        o.reward.kind.value == 'cashback',
        o.terms.order if o.terms.order is not None else (0 if o.percent is not None else 1),
        urgency(o.reward)))
    return problem
