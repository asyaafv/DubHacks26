"""Exported HTTP routes for redemptions and the savings dashboard.

With DATABASE_URL configured these run on Postgres; without it they fall back to
the shared in-memory demo store (backend.decisions.memory) that intake writes to.
"""
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request

from backend.app.schemas import Reward
from backend.decisions import memory
from backend.decisions.common import resolve_user
from .schemas import RedeemRequest, SavingsSummary
from .service import build_summary, redeem, savings_summary

router = APIRouter(tags=['Savings'])


def _database(request: Request):
    database = getattr(request.app.state, 'database', None)
    if database is None and not memory.in_memory_mode(request.app):
        raise HTTPException(503, 'Database is not configured')
    return database


@router.post('/rewards/{reward_id}/redeem', response_model=Reward)
async def redeem_reward(request: Request, reward_id: UUID, body: RedeemRequest | None = None,
                        x_user_id: str | None = Header(None, alias='X-User-Id')) -> Reward:
    """Mark the reward used, record a redemption and emit reward_used; idempotent."""
    user = resolve_user(x_user_id)
    saved = body.saved if body else None
    database = _database(request)
    if database is None:
        return memory.redeem(user, reward_id, saved)
    async with database.transaction(user) as repo:
        return await redeem(repo, reward_id, saved)


@router.get('/savings', response_model=SavingsSummary)
async def get_savings(request: Request,
                      x_user_id: str | None = Header(None, alias='X-User-Id')) -> SavingsSummary:
    """Total savings, itemized redemptions (newest first), cumulative daily series."""
    user = resolve_user(x_user_id)
    database = _database(request)
    if database is None:
        return build_summary(memory.list_redemptions(user))
    async with database.transaction(user) as repo:
        return await savings_summary(repo)
