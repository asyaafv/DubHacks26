"""In-memory fallback for demo mode (DATABASE_URL unset).

Reads the same module-level caches intake writes to (backend.app.main.get_rewards
and friends) so extracted rewards, wallet counts, redemptions and savings stay
consistent without Postgres. Demo redemptions load from shared/seed. This path is
taken only when DATABASE_URL is not configured; a configured-but-unavailable
database still fails loudly with 503 instead of silently serving demo data.
"""
from datetime import timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException

from backend.app.schemas import Reward, RewardStatus, Wallet
from backend.decisions.common import exact_number, utc

SEED_DIR = Path(__file__).resolve().parents[2] / 'shared' / 'seed'
_redemptions: list | None = None


def in_memory_mode(app) -> bool:
    return getattr(app.state, 'database', None) is None and not os.getenv('DATABASE_URL')


def _main():
    from backend.app import main
    return main


def _store() -> list:
    # Imported lazily: the savings package imports this module at load time.
    from backend.decisions.savings.schemas import Redemption
    global _redemptions
    if _redemptions is None:
        path = SEED_DIR / 'seed_redemptions.json'
        rows = json.loads(path.read_text())['redemptions'] if path.exists() else []
        _redemptions = [Redemption.model_validate(row) for row in rows]
    return _redemptions


def reset():
    """Test helper: drop cached redemptions so the seed reloads."""
    global _redemptions
    _redemptions = None


def _eligible(reward: Reward, now) -> bool:
    return (reward.status == RewardStatus.active
            and (reward.starts_at is None or utc(reward.starts_at) <= now)
            and (reward.expires_at is None or utc(reward.expires_at) > now))


def get_wallet(user_id: UUID) -> Wallet:
    main, now = _main(), utc()
    eligible = [r for r in main.get_rewards() if r.user_id == user_id and _eligible(r, now)]
    soon = now + timedelta(days=3)
    return Wallet(
        user_id=user_id,
        cards=[c for c in main.get_cards() if c.user_id == user_id],
        memberships=[m for m in main.get_memberships() if m.user_id == user_id],
        active_rewards_count=len(eligible),
        expiring_soon_count=sum(1 for r in eligible if r.expires_at and utc(r.expires_at) <= soon),
    )


def list_redemptions(user_id: UUID) -> list:
    items = [r for r in _store() if r.user_id == user_id]
    items.sort(key=lambda r: (utc(r.redeemed_at), str(r.id)), reverse=True)
    return items


def redeem(user_id: UUID, reward_id: UUID, saved: Decimal | None) -> Reward:
    from backend.decisions.savings.schemas import Redemption
    from backend.decisions.savings.service import describe, face_value
    reward = next((r for r in _main().get_rewards()
                   if r.user_id == user_id and r.id == reward_id), None)
    if reward is None:
        raise HTTPException(404, 'Reward not found')
    already = reward.status == RewardStatus.used or any(
        r.reward_id == reward_id for r in list_redemptions(user_id))
    if not already:
        if saved is None:
            saved = face_value(reward)
        try:
            amount = exact_number(saved, 2).quantize(Decimal('0.01'))
        except (ValueError, ArithmeticError):
            raise HTTPException(422, 'saved must be a non-negative amount with at most 2 decimals') from None
        _store().append(Redemption(id=uuid4(), user_id=user_id, reward_id=reward_id,
                                   merchant_name=reward.merchant_name, description=describe(reward),
                                   saved=amount, redeemed_at=utc()))
    reward.status = RewardStatus.used
    reward.updated_at = utc()
    return reward
