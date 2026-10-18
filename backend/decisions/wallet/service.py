from uuid import uuid4
from backend.app.schemas import Card, Membership
from backend.decisions import memory
from backend.decisions.common import utc


async def wallet_snapshot(app, user_id):
    """Postgres wallet when configured; in-memory demo wallet when DATABASE_URL is unset."""
    database = getattr(app.state, 'database', None)
    if database is None and memory.in_memory_mode(app):
        return memory.get_wallet(user_id)
    if database is None:
        from fastapi import HTTPException
        raise HTTPException(503, 'Database is not configured')
    async with database.transaction(user_id) as repo:
        return await repo.get_wallet()


async def update_wallet(repo, update):
    for card_id in update.remove_card_ids:
        await repo.remove_card(card_id)
    for membership_id in update.remove_membership_ids:
        await repo.remove_membership(membership_id)
    for card in update.add_cards:
        await repo.add_card(Card(**card.model_dump(), id=uuid4(), user_id=repo.user_id, created_at=utc()))
    for membership in update.add_memberships:
        await repo.add_membership(Membership(**membership.model_dump(), id=uuid4(), user_id=repo.user_id, created_at=utc()))
    return await repo.get_wallet()
