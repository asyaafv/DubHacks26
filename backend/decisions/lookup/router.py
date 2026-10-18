"""Integration imports router; no application wiring or model loads here."""
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from backend.app.schemas import LookupRequest, LookupResult
from backend.decisions.common import resolve_user, utc
from backend.decisions.dependencies import get_database
from .service import LookupService, EncoderUnavailable

router = APIRouter()


def get_lookup_service(request: Request):
    return LookupService(getattr(request.app.state, 'query_encoder', None),
                         getattr(request.app.state, 'lookup_clock', utc))


@router.post('/lookup', response_model=LookupResult, tags=['Lookup'])
async def lookup_rewards(body: LookupRequest,
    x_user_id: str | None = Header(None, alias='X-User-Id'),
    database=Depends(get_database), service=Depends(get_lookup_service)):
    user_id = resolve_user(x_user_id, body.user_id)
    try:
        async with database.transaction(user_id) as repo:
            return await service.lookup(repo, body)
    except EncoderUnavailable as exc:
        raise HTTPException(503, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
