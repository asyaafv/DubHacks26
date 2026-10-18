from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header

from backend.app.schemas import RedeemRequest, Reward, SavingsSummary
from backend.decisions.common import resolve_user
from backend.decisions.dependencies import get_database
from .service import redeem_reward, savings_summary

router = APIRouter(tags=['Savings'])


@router.post('/rewards/{id}/redeem', response_model=Reward)
async def redeem(id: UUID, request: RedeemRequest = Body(default=RedeemRequest()),
                 x_user_id: str | None = Header(None, alias='X-User-Id'),
                 database=Depends(get_database)):
    """Atomically record a reward's savings and publish reward_used; retries are idempotent."""
    async with database.transaction(resolve_user(x_user_id)) as repo:
        return await redeem_reward(repo, id, request)


@router.get('/savings', response_model=SavingsSummary)
async def get_savings(x_user_id: str | None = Header(None, alias='X-User-Id'),
                      database=Depends(get_database)):
    """Exact total, newest-first redemption items and cumulative UTC daily points."""
    async with database.transaction(resolve_user(x_user_id)) as repo:
        return await savings_summary(repo)
