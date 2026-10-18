"""Redeem + savings summary logic; every query runs inside the owner transaction."""
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import HTTPException

from backend.app.schemas import Reward, RewardKind, RewardStatus
from backend.decisions.common import exact_number, utc
from .schemas import Redemption, SavingsPoint, SavingsSummary

CENTS = Decimal('0.01')


def face_value(reward: Reward) -> Decimal:
    """Fallback savings when the caller supplies no cart-derived amount."""
    if reward.kind in (RewardKind.amount_off, RewardKind.cashback):
        return Decimal(reward.value).quantize(CENTS, rounding=ROUND_HALF_UP)
    if reward.kind == RewardKind.percent_off and reward.min_spend:
        return (Decimal(reward.value) * Decimal(reward.min_spend) / 100).quantize(CENTS, rounding=ROUND_HALF_UP)
    if reward.kind in (RewardKind.free_item, RewardKind.bogo):
        # Team convention: free_item/bogo carry value 1.00 (extraction standard).
        return Decimal(reward.value).quantize(CENTS, rounding=ROUND_HALF_UP)
    return Decimal('0.00')


def describe(reward: Reward) -> str:
    if reward.kind == RewardKind.percent_off:
        return f"{Decimal(reward.value).normalize()}% off"
    if reward.kind in (RewardKind.amount_off, RewardKind.cashback):
        return f"${Decimal(reward.value).quantize(CENTS)} {reward.kind.value.replace('_', ' ')}"
    return reward.kind.value.replace('_', ' ')


async def redeem(repo, reward_id, saved: Decimal | None) -> Reward:
    """Mark used + insert redemption + emit reward_used, idempotently."""
    reward = await repo.get_reward(reward_id, reveal_code=True)
    if reward is None:
        raise HTTPException(404, 'Reward not found')
    already = reward.status == RewardStatus.used or await repo.get_redemption_for_reward(reward_id) is not None
    if not already:
        if saved is None:
            saved = face_value(reward)
        try:
            amount = exact_number(saved, 2).quantize(CENTS)
            await repo.add_redemption(Redemption(
                id=uuid4(), user_id=repo.user_id, reward_id=reward_id,
                merchant_name=reward.merchant_name, description=describe(reward),
                saved=amount, redeemed_at=utc()))
        except (ValueError, ArithmeticError):
            raise HTTPException(422, 'saved must be a non-negative amount with at most 2 decimals') from None
    # set_reward_status appends the reward_used event; no-op if already used.
    await repo.set_reward_status(reward_id, RewardStatus.used)
    return await repo.get_reward(reward_id, reveal_code=True)


def build_summary(items: list[Redemption]) -> SavingsSummary:
    """Pure summary over redemption rows; shared by the DB and in-memory paths."""
    total = sum((item.saved for item in items), Decimal('0.00'))
    series, running = [], Decimal('0.00')
    for item in sorted(items, key=lambda i: (utc(i.redeemed_at), str(i.id))):
        running += item.saved
        day = utc(item.redeemed_at).date()
        if series and series[-1].date == day:
            series[-1] = SavingsPoint(date=day, cumulative=running)
        else:
            series.append(SavingsPoint(date=day, cumulative=running))
    return SavingsSummary(total=total.quantize(CENTS), items=items, series=series)


async def savings_summary(repo) -> SavingsSummary:
    return build_summary(await repo.list_redemptions())
