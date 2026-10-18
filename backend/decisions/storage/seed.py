"""Explicit, repeatable JSON import through the production encryption paths."""
import json
from pathlib import Path

from backend.app.schemas import Card, Membership, Merchant, Reward
from backend.decisions.common import DEMO_USER_ID

SEEDS = Path(__file__).resolve().parents[3] / 'shared' / 'seed'


async def seed(database, directory=SEEDS):
    # One transaction + per-user import ledger: restarting or reseeding cannot
    # resurrect removed products or reset status/code edits.
    async with database.transaction(DEMO_USER_ID) as repo:
        for filename, key, model, save in (
            ('seed_merchants.json', 'merchants', Merchant, repo.save_merchant),
            ('seed_cards.json', 'cards', Card, repo.add_card),
            ('seed_memberships.json', 'memberships', Membership, repo.add_membership),
            ('seed_rewards.json', 'rewards', Reward, repo.save_reward),
        ):
            claimed = await repo._conn.fetchval('INSERT INTO seed_imports(user_id,dataset) VALUES($1,$2) ON CONFLICT DO NOTHING RETURNING dataset', repo.user_id, filename)
            if claimed:
                data = json.loads((directory / filename).read_text())
                for row in data[key]:
                    await save(model.model_validate(row))
    # Keep a separate owner-locked transaction/ledger for the startup history.
    from backend.decisions.savings.seed import seed_redemptions
    await seed_redemptions(database, directory)
