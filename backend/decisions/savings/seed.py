"""One-time rolling demo history, separate from live reward/wallet seed imports."""
from datetime import timedelta
from decimal import Decimal
import json
from uuid import UUID

from backend.app.schemas import Reward
from backend.decisions.common import DEMO_USER_ID, utc
from backend.decisions.storage.seed import SEEDS


async def seed_redemptions(database, directory=SEEDS, *, now=None):
    filename = 'seed_redemptions.json'
    now = utc(now)
    async with database.transaction(DEMO_USER_ID) as repo:
        claimed = await repo._conn.fetchval(
            'INSERT INTO seed_imports(user_id,dataset) VALUES($1,$2) '
            'ON CONFLICT DO NOTHING RETURNING dataset', DEMO_USER_ID, filename)
        if not claimed:
            return False
        data = json.loads((directory / filename).read_text())
        if UUID(data['demo_user_id']) != DEMO_USER_ID:
            raise ValueError('Redemption seed must belong to the demo user')
        rows = data['redemptions']
        if sum((Decimal(row['saved']) for row in rows), Decimal('0.00')) != Decimal(data['total']):
            raise ValueError('Redemption seed total does not match its items')
        for row in rows:
            if not isinstance(row['days_ago'], int) or not 1 <= row['days_ago'] <= 42:
                raise ValueError('Demo redemptions must be within the previous six weeks')
            redeemed_at = now - timedelta(days=row['days_ago'])
            historical = Reward(
                id=UUID(row['reward_id']), user_id=DEMO_USER_ID,
                merchant_name=row['merchant_name'], category=row['category'], mcc=row['mcc'],
                kind='amount_off', value=Decimal(row['saved']), source='seed',
                starts_at=redeemed_at - timedelta(days=14),
                expires_at=redeemed_at + timedelta(days=7),
                created_at=redeemed_at - timedelta(days=14), updated_at=redeemed_at)
            await repo.save_reward(historical)
            await repo.record_redemption(historical.id, Decimal(row['saved']), row['description'],
                                         redeemed_at=redeemed_at, redemption_id=UUID(row['id']))
        return True
