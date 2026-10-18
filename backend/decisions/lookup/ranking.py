"""Deterministic native-unit utility ranking, never a savings quotation."""
from datetime import datetime, timezone
from decimal import Decimal
import math

from backend.app.schemas import RewardKind, RewardStatus, ScoredReward
from backend.decisions.common import utc


def value_component(reward):
    # Separate native-unit scales. No cart, FX, points or item-value assumptions.
    if reward.kind == RewardKind.percent_off:
        return float(min(reward.value / Decimal('100'), Decimal(1)))
    if reward.kind == RewardKind.amount_off and reward.currency == 'USD':
        return float(min(reward.value / Decimal('50'), Decimal(1)))
    # Cashback unit is ambiguous in the current schema. Do not infer a dollar value.
    return 0.0


def rank_rewards(candidates, *, now, limit=3):
    if not 1 <= limit <= 10:
        raise ValueError('Invalid lookup limit')
    now = utc(now)
    scored = []
    for reward, match in candidates:
        # Defense in depth; SQL must already enforce eligibility and relevance.
        if reward.status != RewardStatus.active:
            continue
        if reward.starts_at and utc(reward.starts_at) > now:
            continue
        if reward.expires_at and utc(reward.expires_at) <= now:
            continue
        if not math.isfinite(match) or not 0 < match <= 1:
            continue
        days = (utc(reward.expires_at) - now).total_seconds() / 86400 if reward.expires_at else None
        urgency = 1 + math.exp(-days / 3) if days is not None else 1.0
        value = value_component(reward)
        scored.append(ScoredReward(reward=reward, score=value * match * urgency,
            value_component=value, match_component=match, urgency_component=urgency,
            days_until_expiry=math.floor(days) if days is not None else None))
    scored.sort(key=lambda s: (-s.score, -s.match_component,
        utc(s.reward.expires_at) if s.reward.expires_at else datetime.max.replace(tzinfo=timezone.utc),
        str(s.reward.id)))
    return scored[:limit]
