"""Integration exports router; shared app/main.py is intentionally untouched."""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from backend.app.schemas import StackRequest, StackResult
from backend.decisions.common import resolve_user, utc
from backend.decisions.dependencies import get_database
from .optimizer import SolverUnavailable, VerificationError
from .service import load_checkout, solve_stacking

router = APIRouter(tags=['Stacking'])


@router.post('/stack', response_model=StackResult)
async def stack(request: StackRequest, http_request: Request,
                x_user_id: str | None = Header(None, alias='X-User-Id'),
                database=Depends(get_database)):
    user_id = resolve_user(x_user_id, request.user_id)
    if not request.merchant_id and not request.domain:
        raise HTTPException(422, 'Supply merchant_id or domain')
    raw = await http_request.json()
    if any(isinstance(item.get('quantity'), bool) for item in raw.get('items', [])):
        raise HTTPException(422, 'Item quantities cannot be booleans')
    now = utc()
    try:
        async with database.transaction(user_id) as repo:
            rewards, cards, merchant, memberships = await load_checkout(repo, request, now=now)
    except ValueError:
        raise HTTPException(400, 'Invalid or conflicting merchant identity') from None
    try:
        return await run_in_threadpool(solve_stacking, request, rewards, cards, merchant,
                                       memberships, now=now)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except (VerificationError, SolverUnavailable):
        raise HTTPException(503, 'A verified stacking recommendation is unavailable') from None
