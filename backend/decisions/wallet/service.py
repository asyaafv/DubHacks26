from uuid import uuid4
from backend.app.schemas import Card, Membership
from backend.decisions.common import utc


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
