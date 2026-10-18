"""'Use it before you lose it' (pure helpers, no FastAPI).

Rule (shared with the frontend):
- Scope: ACTIVE rewards of the SAME merchant (equal non-null merchant_id)
  that cannot combine in one order: both carry a promo code, OR either
  reward is not stackable.
- A = the soonest-expiring such reward with 0 <= days_until_expiry <= 7
  (days = floor((expires_at - now) / 86400s)).
- B = any other such reward that never expires or expires at least 14 days
  after A.
- When the rule applies, A should be used first and every qualifying B is
  flagged save-for-later; otherwise behavior is completely unchanged.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import UUID

from backend.app.schemas import Reward, RewardKind, RewardStatus, ScoredReward
from backend.decisions.common import utc

EXPIRING_WINDOW_DAYS = 7
SAFE_GAP_DAYS = 14


def _plain(value) -> str:
    """Trim trailing zeros without scientific notation (25.00 -> 25)."""
    return format(Decimal(value).normalize(), 'f')


def _money(value) -> str:
    return f"{Decimal(value):.2f}"


def value_label(reward: Reward) -> str:
    """Short human label for a reward's value ('25% off', '$5.00 off')."""
    if reward.kind == RewardKind.percent_off:
        return f"{_plain(reward.value)}% off"
    if reward.kind == RewardKind.amount_off:
        return f"${_money(reward.value)} off"
    if reward.kind == RewardKind.cashback:
        return f"${_money(reward.value)} cashback"
    if reward.kind == RewardKind.points:
        return f"{_plain(reward.value)} points"
    if reward.kind == RewardKind.free_item:
        return "Free item"
    return "BOGO"


def _days_until(reward: Reward, now: datetime) -> int | None:
    if reward.expires_at is None:
        return None
    return math.floor((utc(reward.expires_at) - now).total_seconds() / 86400)


def _cannot_combine(a: Reward, b: Reward) -> bool:
    """True when a and b cannot both apply to one order."""
    both_coded = a.code is not None and b.code is not None
    return both_coded or not a.stackable or not b.stackable


def _date_phrase(expires_at: datetime) -> str:
    return utc(expires_at).strftime('%b %-d')


def _expiry_phrase(days: int) -> str:
    if days == 0:
        return 'today'
    if days == 1:
        return 'in 1 day'
    return f'in {days} days'


def _find_pair(rewards: list[Reward], now: datetime) -> tuple[Reward, list[Reward]] | None:
    """Return (A, qualifying Bs) or None when the rule does not apply."""
    active = [r for r in rewards
              if r.status == RewardStatus.active and r.merchant_id is not None]
    expiring = []
    for r in active:
        days = _days_until(r, now)
        if days is not None and 0 <= days <= EXPIRING_WINDOW_DAYS:
            expiring.append(r)
    expiring.sort(key=lambda r: utc(r.expires_at))
    for a in expiring:
        threshold = utc(a.expires_at) + timedelta(days=SAFE_GAP_DAYS)
        bs = [r for r in active
              if r.id != a.id
              and r.merchant_id == a.merchant_id
              and _cannot_combine(a, r)
              and (r.expires_at is None or utc(r.expires_at) >= threshold)]
        if bs:
            return a, bs
    return None


def _best(bs: list[Reward]) -> Reward:
    return max(bs, key=lambda r: Decimal(r.value))


def apply_use_first(scored: list[ScoredReward], now: datetime | None = None) -> list[ScoredReward]:
    """Flag/reorder an already-scored, merchant-scoped lookup result.

    When the rule applies: A is moved to the front with use_first=True, every
    qualifying B gets save_for_later=True at its scored position, and the
    relative order of everything else is preserved. Otherwise the list is
    returned unchanged.
    """
    now = utc(now)
    pair = _find_pair([s.reward for s in scored], now)
    if pair is None:
        return scored
    a, bs = pair
    best = _best(bs)
    b_ids = {b.id for b in bs}

    days = _days_until(a, now) or 0
    if best.expires_at is None:
        tail = f"Your {value_label(best)} is not expiring."
    else:
        tail = f"Your {value_label(best)} is good until {_date_phrase(best.expires_at)}."
    a_note = f"Use first: expires {_expiry_phrase(days)}. {tail}"

    out: list[ScoredReward] = []
    a_scored: ScoredReward | None = None
    for item in scored:
        if item.reward.id == a.id:
            a_scored = item.model_copy(update={'use_first': True, 'recommendation': a_note})
        elif item.reward.id in b_ids:
            if item.reward.expires_at is None:
                note = 'Save for later — no expiration'
            else:
                note = f"Save for later — good until {_date_phrase(item.reward.expires_at)}"
            out.append(item.model_copy(update={'save_for_later': True, 'recommendation': note}))
        else:
            out.append(item)
    if a_scored is None:  # A not in the scored list; nothing to reorder
        return scored
    return [a_scored, *out]


def stack_exclusions(
    rewards: list[Reward],
    merchant_id: UUID | None,
    now: datetime | None = None,
) -> tuple[set[UUID], str | None]:
    """Save-for-later reward ids to withhold from the /stack solver.

    Returns (excluded reward ids, explanation sentence) when the rule applies
    for the given merchant, else (set(), None).
    """
    if merchant_id is None:
        return set(), None
    now = utc(now)
    scoped = [r for r in rewards
              if r.merchant_id == merchant_id and r.status == RewardStatus.active]
    pair = _find_pair(scoped, now)
    if pair is None:
        return set(), None
    _, bs = pair
    best = _best(bs)
    code = f" ({best.code})" if best.code else ""
    if best.expires_at is None:
        until = "no expiration"
    else:
        until = f"good until {_date_phrase(best.expires_at)}"
    sentence = f"Saved for later: {value_label(best)}{code} — {until}."
    return {b.id for b in bs}, sentence
