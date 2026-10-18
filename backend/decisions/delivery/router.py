"""Exported HTTP routes; remove the corresponding stubs when integrating."""
import asyncio
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from asyncpg import PostgresError

from backend.app.schemas import SyncResponse
from backend.decisions.common import resolve_user, utc
from backend.decisions.dependencies import get_database
from .service import parse_cursor, read_page, stream, sync_snapshot

router = APIRouter()


def get_runtime(request: Request):
    runtime = getattr(request.app.state, 'delivery', None)
    if runtime is None:
        raise HTTPException(503, 'Delivery startup hook has not run')
    return runtime


@router.get('/events')
async def events(request: Request, x_user_id: str | None = Header(None),
                 last_event_id: str | None = Header(None),
                 database=Depends(get_database), runtime=Depends(get_runtime)):
    user = resolve_user(x_user_id)
    after = parse_cursor(last_event_id, user)
    runtime.reserve(user)
    try:
        page = await read_page(database, user, after, runtime.settings, validate_cursor=True)
    except (asyncio.TimeoutError, OSError, PostgresError):
        runtime.release(user)
        raise HTTPException(503, 'Event storage temporarily unavailable', headers={'Retry-After': '5'}) from None
    except BaseException:
        runtime.release(user)
        raise
    return StreamingResponse(stream(request, database, user, after, runtime, page),
                             media_type='text/event-stream',
                             headers={'Cache-Control': 'no-cache, no-transform',
                                      'X-Accel-Buffering': 'no'})


@router.get('/sync', response_model=SyncResponse)
async def sync(response: Response, since: datetime | None = None,
               x_user_id: str | None = Header(None), database=Depends(get_database),
               runtime=Depends(get_runtime)):
    user = resolve_user(x_user_id)
    # Existing clients accept naive timestamps; interpret them as UTC at the boundary.
    try:
        result, cursor = await asyncio.wait_for(
            sync_snapshot(database, user, utc(since) if since else None, runtime.settings),
            timeout=runtime.settings.query_timeout_seconds)
    except (asyncio.TimeoutError, OSError, PostgresError):
        raise HTTPException(503, 'Sync storage temporarily unavailable') from None
    response.headers['X-Event-Cursor'] = cursor
    response.headers['Cache-Control'] = 'no-store'
    return result
