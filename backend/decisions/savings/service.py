"""Money is Decimal throughout; status, ledger and outbox share one transaction."""
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from fastapi import HTTPException

from backend.app.schemas import RewardKind, RewardStatus, SavingsPoint, SavingsSummary
from backend.decisions.common import exact_number, utc

CENT = Decimal('0.01')
MAX_SAVED = Decimal('99999999.99')


def calculate_savings(reward, cart_total):
    """Known eligible subtotal only; stack clients should supply their actual savings."""
    cart_total = exact_number(cart_total, 2)
    if reward.min_spend is not None and cart_total < reward.min_spend:
        raise ValueError('Cart does not meet the reward minimum spend')
    if reward.kind == RewardKind.percent_off:
        rate = exact_number(reward.value, 6, maximum=100)
        saved = cart_total * rate / 100
    elif reward.kind == RewardKind.amount_off:
        saved = reward.value
    else:
        raise ValueError('Provide saved explicitly for this reward kind')
    if reward.max_discount is not None:
        saved = min(saved, reward.max_discount)
    return min(cart_total, saved).quantize(CENT, rounding=ROUND_HALF_UP)


def reward_description(reward):
    if reward.kind == RewardKind.percent_off:
        return f'{reward.value.normalize():f}% off'
    if reward.kind == RewardKind.amount_off:
        return f'${reward.value:.2f} off'
    return reward.kind.value.replace('_', ' ').capitalize()


async def redeem_reward(repo, reward_id, request, *, now=None, redemption_id=None):
    reward = await repo.get_reward(reward_id)
    if reward is None:
        raise HTTPException(404, 'Reward not found')
    # Safe to retry a request or an entire applied stack without inflating totals.
    if await repo.get_redemption(reward_id) is not None:
        return reward
    now = utc(now)
    if (reward.status != RewardStatus.active
            or (reward.starts_at is not None and utc(reward.starts_at) > now)
            or (reward.expires_at is not None and utc(reward.expires_at) <= now)):
        raise HTTPException(409, 'Reward is not available for redemption')
    if reward.currency != 'USD':
        raise HTTPException(422, 'Savings tracking currently records USD only')
    try:
        if request.saved is not None:
            saved = request.saved
        elif request.cart_total is not None:
            saved = calculate_savings(reward, request.cart_total)
        else:
            # Explicit product policy: without a cart, record the nominal face
            # value. This is not a claim about a percentage/points conversion.
            saved = reward.value.quantize(CENT, rounding=ROUND_HALF_UP)
        saved = exact_number(saved, 2, maximum=MAX_SAVED)
        await repo.record_redemption(reward.id, saved, reward_description(reward),
                                     redeemed_at=now, redemption_id=redemption_id)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    return await repo.get_reward(reward.id)


async def savings_summary(repo):
    items = await repo.list_redemptions()
    by_day = defaultdict(lambda: Decimal('0.00'))
    for item in items:
        by_day[utc(item.redeemed_at).date()] += item.saved
    total = Decimal('0.00')
    series = []
    for day in sorted(by_day):
        total += by_day[day]
        series.append(SavingsPoint(date=day, cumulative=total))
    return SavingsSummary(total=total, items=items, series=series)
