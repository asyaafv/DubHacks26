# Savings tracking

Run `python -m backend.decisions.storage migrate` before starting the API. Migration
003 adds the ledger to existing databases; 001 and 002 remain unchanged. Current
configuration uses `LAPSE_ENCRYPTION_KEY`; retain the existing key value. The shared
Wallet model now includes eligible owned `rewards` with their known `expires_at`.
Unknown expiration dates remain null; the calendar should omit those dates rather
than inventing deadlines.

## API

Both endpoints use the existing `X-User-Id` UUID header and user-scoped transaction.

`POST /rewards/{id}/redeem` accepts `{"saved":"12.50"}` and returns the used Reward
with its code redacted. Reward status, redemption row and durable `reward_used`
event commit atomically. Unknown/foreign rewards return 404; unavailable rewards
return 409. Concurrent/repeated requests record only the first amount and return
the current Reward without duplicating a row/event. One reward has one redemption.

If `saved` is absent (including an absent body), an optional `cart_total` computes
percent/amount-off savings with minimum spend, discount caps, subtotal bounds and
ROUND_HALF_UP cents. The cart must be the known eligible subtotal, not an inferred
previous request. Other reward kinds need explicit `saved` when a cart is provided.
Without a cart, the requested fallback records the nominal reward face value,
rounded to cents. This policy is not a conversion of points or percentages to a
verified checkout amount. Applied-stack clients should always send exact savings.
The ledger aggregates USD only; other currencies return 422 rather than mixing units.

`GET /savings` returns required `total`, `items`, and `series`. All money is a
two-decimal JSON string. Items are newest first, with stable ID tie-breaking.
Points use UTC dates in ascending order, combine all redemptions on the same day,
and accumulate from zero over the full ledger. Empty history returns
`{"total":"0.00","items":[],"series":[]}`. Card cashback is not separately
recorded by this reward ledger; do not add it to every chosen reward's savings.

## Demo history

Startup loads `shared/seed/seed_redemptions.json` once for the demo user when a
database is configured. Eight records total exactly $103.51. Their dates span
40 days ago through yesterday, anchored to the first startup/import and preserved
thereafter. A separate seed ledger plus deterministic IDs prevents duplicates on
restart or explicit reseeding. Historical backing rewards have their own IDs and
are marked used; the live Hollister voucher and other active seed offers remain
available. `python -m backend.decisions.storage seed` also imports this history.
Startup still does not run DDL or reset the existing wallet/reward seed datasets.

## Integration handoff

The savings router is registered in the current application. The extension checkout
implementation is not present in this branch. Its owner can call the tested
`frontend/api/redemptions.mjs` helper `redeemAppliedStack(stack, {baseUrl, userId})`
only after confirming the selected rewards were actually applied. It posts each
`ChosenReward.savings` without JavaScript arithmetic. Retrying after a partial
failure is safe. Do not call redemption merely when requesting `/stack`.

The event is in the canonical durable outbox consumed by the separately developed
delivery router. Current merged main still contains a stub `/events` handler;
the teammate integrating delivery must replace it with
`backend.decisions.delivery.router` to expose these events on the live stream.
This branch does not claim that the stub streams persisted redemptions.

New public models, Wallet's additive reward list, JSON schemas, TypeScript types,
and OpenAPI are regenerated together. No external team messages were sent.

## Verification

Run against a disposable migrated PostgreSQL database with pgvector/pgcrypto:

```sh
TEST_DATABASE_URL=postgresql://... python -m pytest backend/tests/test_savings.py backend/tests/test_storage_wallet.py -q
node --test frontend/api/redemptions.test.mjs
python scripts/gen_contracts.py
```

The live-stream test runs when `backend.decisions.delivery` is available; it skips
explicitly on the current foundation-only main. To verify against the existing
delivery worktree without merging that component, set LAPSE_DELIVERY_CHECKOUT to
its path and run from this checkout:

```sh
TEST_DATABASE_URL=postgresql://... LAPSE_DELIVERY_CHECKOUT=/absolute/path/to/lapse-delivery python - <<'PY'
import os
from pathlib import Path
import backend.decisions
import pytest
backend.decisions.__path__.append(str(Path(os.environ['LAPSE_DELIVERY_CHECKOUT']) / 'backend/decisions'))
raise SystemExit(pytest.main(['backend/tests/test_savings.py', 'backend/tests/test_storage_wallet.py', '-q']))
PY
```

Actual result: **23 backend tests passed** on isolated native PostgreSQL with the
existing delivery component available, including HTTP SSE, concurrent retries,
atomic rollback, cross-user checks, existing-database upgrade, repeatable startup
history, exact rounding and day grouping. **2 client-helper tests passed**. Contract
generation is repeatable and `git diff --check` passed.

The broader existing API contract run had **40 passes and 2 failures**. Both
failures are `/inbound` checks that require the absent `gliner2` package/model in
this environment; extraction source was unchanged. The complete extraction suite
and production email-to-extension flow are not claimed as verified here.
