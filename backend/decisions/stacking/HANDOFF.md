# Person 3 stacking handoff

Branch: `codex/person3-stacking`.

## Integration

Export: `backend.decisions.stacking.router.router` (`fastapi.APIRouter`).
Integration must remove the old POST /stack handler and include this router in
backend/app/main.py. That file, public schemas, contracts, shared helpers, storage,
seed files, and dependency manifests were not edited by this implementation.

The router uses foundation `get_database`, `resolve_user`, and ONE scoped
`database.transaction(user_id)` to resolve the merchant and read rewards/wallet.
No replacement storage or implicit seeding exists. After the transaction closes,
CP-SAT runs in Starlette's worker pool so it does not block the async event loop.
`get_database` can be overridden when mounting this router in a small test app.
Missing database configuration remains 503. Conflicting body/header users and
merchant identifiers are 400; invalid monetary/cart data is 422; failed verification
or a solver timeout with no available verified recommendation is 503.

Foundation's list_rewards deliberately redacts codes. `load_checkout` therefore
calls scoped `get_reward(id, reveal_code=True)` for matching merchant rewards
BEFORE solving, ensuring the one-code constraint does not disappear through
redaction. No SQL, schema change, logging of decrypted values, or mutation is used.
Chosen Reward objects retain their actual code as required by the public schema.

Pure entry point:

```python
from backend.decisions.stacking.service import solve_stacking
result = solve_stacking(
    request, rewards, cards, merchant, memberships,
    now=aware_utc_datetime, terms=trusted_reward_terms_by_uuid, time_limit=3.0,
)
```

`prepare` and `optimize` are also independently callable. `reference.exhaustive`
independently enumerates all subsets AND all payment options; `reference.evaluate`
replays a selection using Python integer arithmetic without any CP-SAT dependency.

## Required foundation/shared changes (not made here)

1. Add **`ortools==9.15.6755`** to the core Python dependencies (the tested version).
   It was installed only into the existing local .venv for component verification.
   Runtime dependencies are resolved by pip; no ML dependencies are needed.
   OR-Tools 9.15's duplicate-column presolver aborts natively on some proportional
   allocation/division models exercised by the random test. This implementation
   disables CP-SAT presolve explicitly; the actual optimizer remains CP-SAT.
2. Resolve the Hollister seed conflicts described below. Do not change production
   card rates to match demo assumptions.
3. Public Reward has no structured membership, payment, ordering, cashback-unit,
   pair-specific compatibility, or remainder-eligibility metadata. `RewardTerms`
   is an INTERNAL immutable input, not a public model or new storage interface.
   It supports membership program/tier, allowed card IDs/networks/issuers, explicit
   card-earnings suppression, bilateral pair allowlists, application order,
   amount/percent cashback units, and verified eligibility of unclassified items.
   Foundation/extraction need to coordinate persistence/read interfaces for these
   normalized terms. The current HTTP adapter has no such committed interface,
   so it uses public fields and conservative defaults. Service callers can already
   supply trusted terms; clients cannot inject them through the unchanged request.
   Known structured terms are fully enforced and tested by the pure service.
4. Public cashback rewards do not specify whether `value` means dollars or percent.
   Such rewards are explicitly excluded until trusted `cashback_unit` is supplied.
   Membership benefit prose/annual reward rates never manufacture monetary offers.

## Monetary and eligibility policy

- USD merchandise only; cart_total is authoritative, items may be partial. Negative,
  nonfinite, excess precision, invalid quantity, item subtotal above total, and
  out-of-bound inputs are rejected. Limits: $1,000,000 per checkout/money field,
  64 cart lines, 64 supplied rewards, 32 supplied cards. Limits bound CP-SAT int64
  products and exhaustive work; no silent truncation occurs.
- Integer cents throughout. Percentage points support six decimals, scaled by
  1,000,000; percentage denominator is 100,000,000. Each aggregate reward and card
  earning rounds ONCE to cents, ROUND_HALF_UP, including half-cent discounts.
  No binary floating point is used for money. Savings percent rounds to .01 points.
- Merchant must resolve exactly through foundation's ID/domain/alias rules. An
  unknown merchant permits no merchant reward and earns only owned-card base
  cashback. Category/MCC proximity never substitutes for merchant ownership.
- Owner/status/start/expiration/currency are checked again in the pure service.
  starts_at <= now is eligible; expires_at <= now is ineligible. Naive timestamps
  follow foundation UTC semantics. Cards/memberships must belong to the user;
  membership must be active, unexpired, and match merchant/program/required tier.
- Eligibility buckets are original cart lines. Exclusions match normalized literal
  substrings in item name/category; under exclusions a missing item category is
  conservatively ineligible. The unclassified cart remainder never passes an
  exclusion unless trusted terms establish its eligibility. No fabricated cart
  lines, scaling of supplied items, or semantic interpretation of offer prose.
- Each reward checks its OWN minimum against ORIGINAL eligible merchandise only.
  Thresholds are not added together and are not rechecked after prior discounts.
- Default application order is percentage discounts, amount discounts, then reward
  cashback. Within each discount class order is expiry then UUID. Trusted `order`
  overrides discount precedence; cashback always follows checkout discounts.
  This is an explicitly documented engine policy because public data lacks
  merchant application-order metadata. Merchants requiring other order/minimum
  semantics need normalized terms before the engine can claim their real rules.
- Discounts use the remaining eligible subtotal, compound sequentially, and are
  capped by remaining eligible merchandise and max_discount. Allocate aggregate
  discount proportionally using floor shares, then distribute leftover pennies
  in stable cart-line order. This defines allocation deterministically when
  subsequent rewards have overlapping exclusion scopes. Merchant-specific
  allocation rules need normalized metadata if different from this policy.
- Reward cashback uses FINAL eligible merchandise, does not lower checkout price,
  and is capped by that merchandise and max_discount. Multiple cashback rewards
  do not compound by subtracting cashback from the purchase amount.
- Two promotional rewards combine only if BOTH stackable flags are true and any
  supplied pair allowlists permit the other reward on BOTH sides. At most one
  actual nonempty code may be used. Unknown stackability defaults false.
- A coupon's stackable flag never blocks ordinary card cashback. Explicit allowed
  card/network/issuer terms and card-earnings suppression are enforced jointly
  with reward selection inside CP-SAT, never by choosing a card afterward.
- Owned-card rate uses foundation card_rate: matching MCC first constrains an
  MCC-listed bonus; category-only bonuses require exact normalized categories;
  no matching bonus means base. Rates do not add. Cashback is rounded on FINAL
  checkout merchandise. No automatic top-category inference or invented caps.
- Points, BOGO and free-item rewards lack required redemption/item metadata and
  are excluded with an explicit explanation; no nominal dollars are invented.
- Objective is complete savings NOW: immediate discounts + known reward cashback
  + ordinary payment-card cashback. No future shopping assumptions or LLM math.
  Strict secondary objectives are greater checkout discount, fewer rewards, then
  selecting expiring rewards earlier (UUID breaks equal expiry), then card UUID
  order (no-card wins a zero-earnings tie). Tie-breaking never costs a cent.

## Verification and timeout semantics

CP-SAT uses binary reward/card choices and integer sequential balances, percentage
rounding, caps, proportional allocation and card-dependent restrictions. One worker
and fixed seed make proven optima deterministic. Lexicographic phases share a
three-second default wall-clock solve budget; model construction and bounded
reference verification occur outside that solver budget.

For <=8 eligible rewards, exhaustive reference evaluation always runs alongside
CP-SAT. It uses the same validated/normalized eligibility inputs, independently
checks pairing, codes and card restrictions, replays all discounted item balances,
and compares the complete objective AND deterministic ties across all card choices.
It does not reuse CP-SAT results or sum original-cart nominal discounts. Larger
sets still receive an independent arithmetic/constraint replay of the chosen plan.

A proven optimal solver/reference disagreement raises VerificationError and the
router returns 503. Every solver candidate's individual reward savings, checkout,
card cashback and total are independently replayed before a response is allowed.
`optimal` is emitted only when ALL CP-SAT objective/tie phases prove optimal.
FEASIBLE or a later tie-phase timeout is `feasible`. If CP-SAT finds no candidate
but bounded enumeration completes, status is `reference_verified_solver_timeout`,
explicitly explaining that CP-SAT optimality was not established. With >8 rewards
and no solver candidate, return 503. An invalid/infeasible model fails verification;
the engine never presents an arbitrary empty result as an optimal solution.

## Hollister fixture: confirmed shared conflicts

The unchanged fixture lines sum to **$479.65**, with **$20.35** unclassified.
The voucher excludes Gift Cards/Clearance, so that unknown remainder cannot be
asserted eligible. Also, seed Cash+ 5% Department Stores bonuses list ONLY MCC
5311; Hollister is MCC 5651. Foundation's card_rate correctly rejects that bonus.

Consequently the unchanged committed seeds honestly produce:
$47.97 voucher discount, $452.03 checkout, Freedom Unlimited at 1.5% earning $6.78,
and **$54.75 total savings**. Both optimizer and exhaustive oracle agree.

The golden test provides TWO EXPLICIT test-only corrections: add MCC 5651 to the
DEMO Cash+ 5% bonus and supply trusted remainder_eligible=True for this voucher.
Then both evaluators verify **$50.00 immediate discount; $450.00 checkout;
$22.50 card cashback; $72.50 total savings; 14.50%**. Cashback never lowers checkout.

For the live demo, foundation/integration should either supply a complete eligible
$500 cart plus a corrected demo card rate, or coordinate trusted remainder terms
plus that card correction. Neither arithmetic contradiction is hardcoded around
inside the optimizer. Public fixture/contract changes remain team-owned.

## Exact local verification

Runtime: existing repository .venv, Python 3.10.11, OR-Tools 9.15.6755. Repository
README targets Python 3.11; rerun on the deployment runtime during integration.

- `.venv/bin/python -m pytest backend/tests/test_stacking.py -q --tb=short`
  **56 passed, 1 warning in 0.66s.** Includes 35 fixed-seed randomized complete
  objective comparisons, explicit eight-offer enumeration, incompatible pairs,
  unknown compatibility, multiple codes, independent thresholds, caps, percent
  compounding/order, cent allocation/exclusions, expiry boundaries, memberships,
  card choice/restrictions, ordinary vs reward cashback, unsupported redemptions,
  invalid inputs, zero carts, feasible/timeout statuses, forced oracle mismatch,
  independently mounted HTTP/DI, scoped decrypted code reads, and both demo cases.
- `.venv/bin/python -m pytest backend/tests/ -q --tb=short`
  **110 passed, 12 skipped, 4 failed, 3 warnings in 0.76s.** All four failures are
  existing test_contracts.py tests expecting wallet/sync 200 without DB config:
  TestWalletEndpoint.test_get_wallet_returns_200 / test_get_wallet_valid_schema,
  TestSyncEndpoint.test_sync_returns_200 / test_sync_valid_schema. Foundation's
  database-backed wallet instead returns 503; stacking did not modify those routes.
  Skips include database-backed foundation tests. Deprecation warnings concern
  FastAPI startup lifecycle and Starlette/AnyIO TestClient.

No real database integration/E2E run was performed; those remain integration's scope.
Concurrent lookup/storage changes in this checkout were left outside this work.
