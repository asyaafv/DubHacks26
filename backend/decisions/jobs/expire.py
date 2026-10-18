"""Run with python -m backend.decisions.jobs.expire --window-hours 24."""
import argparse
import asyncio
from dataclasses import asdict, dataclass
from datetime import timedelta
from decimal import Decimal
import json

from backend.app.schemas import EventType, RewardStatus
from backend.decisions.common import utc
from backend.decisions.storage import Database


@dataclass
class Result:
    users: int = 0
    expired: int = 0
    alerts: int = 0


async def run_expiration(database, *, clock=utc, window=timedelta(hours=24), batch_size=100):
    if window <= timedelta(0) or not 1 <= batch_size <= 1000:
        raise ValueError('Window must be positive; batch size must be 1..1000')
    now = utc(clock())
    window_end = now + window
    result = Result()
    after_user = None
    while True:
        users = await database.list_user_ids(after=after_user, limit=batch_size)
        for user in users:
            result.users += 1
            after_reward = None
            while True:
                # Foundation locks the user before reading candidates, so two jobs
                # cannot race a used transition or expire/alert the same active row.
                async with database.transaction(user) as repo:
                    candidates = await repo.list_expiration_candidates(
                        now, window_end, after=after_reward, limit=batch_size)
                    expired = alerts = 0
                    for reward in candidates:
                        expiry = utc(reward.expires_at)
                        if expiry <= now:
                            expired += int(await repo.set_reward_status(reward.id, RewardStatus.expired))
                        elif reward.starts_at is None or utc(reward.starts_at) <= now:
                            # Dedupe by expiry version and configured window, never
                            # by invocation date. Rescheduled expiry may alert again.
                            key = f'expiring:{reward.id}:{expiry.isoformat()}:{window // timedelta(microseconds=1)}'
                            alerts += int(await repo.append_event(EventType.reward_expiring,
                                                                 reward.id, dedupe_key=key))
                # Count only committed batches. A failed batch rolls back atomically.
                result.expired += expired
                result.alerts += alerts
                if len(candidates) < batch_size:
                    break
                after_reward = candidates[-1].id
        if len(users) < batch_size:
            return result
        after_user = users[-1]


async def _main(args):
    database = await Database.connect()
    try:
        result = await run_expiration(database, window=timedelta(seconds=float(args.window_hours * 3600)),
                                      batch_size=args.batch_size)
        print(json.dumps(asdict(result)))
    finally:
        await database.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--window-hours', type=Decimal, default=Decimal('24'))
    parser.add_argument('--batch-size', type=int, default=100)
    args = parser.parse_args()
    if not args.window_hours.is_finite() or not 0 < args.window_hours <= 8760:
        parser.error('window-hours must be finite and in (0, 8760]')
    if not 1 <= args.batch_size <= 1000:
        parser.error('batch-size must be in [1, 1000]')
    asyncio.run(_main(args))


if __name__ == '__main__':
    main()
