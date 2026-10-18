from fastapi import APIRouter, Depends, Header, HTTPException, Request
from backend.app.schemas import Wallet, WalletUpdate
from backend.decisions.common import resolve_user
from backend.decisions.dependencies import get_database
from .service import update_wallet as apply_wallet_update, wallet_snapshot

router = APIRouter(tags=['Wallet'])


@router.get('/wallet', response_model=Wallet)
async def get_wallet(request: Request, x_user_id: str | None = Header(None, alias='X-User-Id')):
    """Wallet with eligible reward counts; in-memory fallback when DATABASE_URL is unset."""
    return await wallet_snapshot(request.app, resolve_user(x_user_id))


@router.post('/wallet', response_model=Wallet)
async def update_wallet(update: WalletUpdate, request: Request,
                      x_user_id: str | None = Header(None, alias='X-User-Id'), database=Depends(get_database)):
    """Atomically add/remove card products and encrypted memberships."""
    raw = await request.json()
    user_id = resolve_user(x_user_id, raw.get('user_id'))
    # Public models ignore extras. Reject payment data rather than silently collect it.
    allowed_card = {'issuer', 'network', 'name', 'base_rate', 'category_rates'}
    if any(set(card) - allowed_card for card in raw.get('add_cards', [])):
        raise HTTPException(422, 'Cards accept product information only')
    try:
        async with database.transaction(user_id) as repo:
            return await apply_wallet_update(repo, update)
    except ValueError:
        raise HTTPException(422, 'Invalid wallet data') from None
