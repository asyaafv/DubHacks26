"""Exported HTTP routes for redemptions and the savings dashboard."""
from uuid import UUID

from fastapi import APIRouter, Depends, Header

from backend.app.schemas import Reward
from backend.decisions.common import resolve_user
from backend.decisions.dependencies import get_database
from .schemas import RedeemRequest, SavingsSummary
from .service import redeem, savings_summary

router = APIRouter(tags=['Savings'])


@router.post('/rewards/{reward_id}/redeem', response_model=Reward)
async def redeem_reward(reward_id: UUID, body: RedeemRequest | None = None,
                        x_user_id: str | None = Header(None, alias='X-User-Id'),
                        database=Depends(get_database)) -> Reward:
    """Mark the reward used, record a redemption and emit reward_used; idempotent."""
    user = resolve_user(x_user_id)
    async with database.transaction(user) as repo:
        return await redeem(repo, reward_id, body.saved if body else None)


@router.get('/savings', response_model=SavingsSummary)
async def get_savings(x_user_id: str | None = Header(None, alias='X-User-Id'),
                      database=Depends(get_database)) -> SavingsSummary:
    """Total savings, itemized redemptions (newest first), cumulative daily series."""
    user = resolve_user(x_user_id)
    async with database.transaction(user) as repo:
        return await savings_summary(repo)
