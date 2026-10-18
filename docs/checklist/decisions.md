# Audit checklist — decisions + database + savings + security

Audited 2026-10-18 on a fresh branch off main (with `cursor/gliner-graceful-degrade-2679` merged).
Environment: Dockerized `pgvector/pgvector:0.8.1-pg17` via `compose.yaml`, `DATABASE_URL` +
`PERK_ENCRYPTION_KEY` set per `docs/database-setup.md`.

## Status per promised feature

| Feature | Status | Evidence |
|---|---|---|
| Postgres + pgvector via compose.yaml | Works | `docker compose up -d --wait` → healthy; vector/pgcrypto/uuid-ossp extensions enabled by migrations |
| Migrations apply cleanly from empty | Works | `python -m backend.decisions.storage migrate` on a freshly created DB → `schema_migrations`: 001, 002, 003 (003 added by this audit); repeat run is a no-op |
| Demo seed loads (rewards/cards/memberships/merchants) | Works | `python -m backend.decisions.storage seed` → 33 rewards (23 active, 2 needs_review, 8 used), 5 cards, 5 memberships; reseeding never resurrects removed data (ledger, covered by tests) |
| Demo redemptions totaling $103.51 | Works (added by this audit) | `SELECT count(*), sum(saved) FROM redemptions` → `8, 103.51`; seeded from `shared/seed/seed_redemptions.json`, each row references a `status=used` seed reward |
| GET /wallet from DB | Works | `curl -H 'X-User-Id: <demo>' :8000/wallet` → 5 cards, 5 memberships, active=22, expiring_soon=6 (Starbucks BOGO correctly excluded: `starts_at` is tomorrow); 401 without identity when `PERK_ALLOW_DEMO_IDENTITY` unset; <20 ms. With `DATABASE_URL` **unset** it now serves the in-memory demo store instead of 503 (same counts); configured-but-unavailable Postgres still fails loudly with 503 |
| POST /wallet | Works | Suite covers atomic add/remove, 400 on conflicting identities, 422 on card-number data, member_id pgcrypto-encrypted |
| GET /sync from DB | Partial | The DB-backed durable `/sync` lives in `backend/decisions/delivery/` and works (33 rewards all statuses, full wallet, `X-Event-Cursor: <uuid>:33`, since/409/400 semantics tested) but is **not wired** — `backend/app/main.py` still serves the stub, which returns seed-JSON rewards (23) **including 20 plaintext codes** and the wallet via the bridge. The bridge no longer 503s without `DATABASE_URL` (in-memory wallet fallback); Postgres behavior unchanged. Durable-router wiring is integration-owned |
| GET /events (SSE) | Partial | Same wiring gap. Delivery router verified live on a scratch app: cursor replay from `<demo>:32` returned reward_added/reward_used/reward_expiring, foreign-user cursor → 400, codes never in event payloads |
| POST /stack (CP-SAT) | Broken (P0) | Not CP-SAT: greedy stub over seed JSON; `ortools` is not even in requirements. Hollister $500 → picks HCOFALL10 ($50, matches fixture) but recommends `cards[0]` → $4.50 cashback vs fixture's US Bank Cash+ $22.50 (total 54.50 vs 72.50). Target $100 → applies **two promo codes** (CIRCLE15 + TARGET5), violating the max-one-code constraint; cart item in excluded category ("Apple") still discounted. Min-spend respected (Target $50 → only $5 off). Per-user isolation OK. Latency p50 0.7 ms / p95 1.0 ms (in-memory) |
| POST /rewards/{id}/redeem | Works (implemented by this audit) | `backend/decisions/savings/`, mounted in `main.py`: marks reward used, inserts redemption, emits `reward_used`; idempotent (replay returns 200, no 2nd row, amount unchanged — DB-enforced by unique `(user_id, reward_id)`); omitted `saved` falls back to face value; 404 unknown/foreign id, 422 negative or >2dp amounts; response decrypts the code for the owner; 18 ms live. Also works without Postgres against the in-memory store |
| GET /savings | Works (implemented by this audit) | Mounted in `main.py`. Seeded: `{"total": "103.51", items: 8, series: 8 points}`; after redeeming Hollister with saved=50.00 → total 153.51, item newest-first, new series point for today; series is cumulative and date-ascending (verified live in both Postgres and in-memory modes + tests) |
| Expiry alert logic (expiring within N days) | Works | `python -m backend.decisions.jobs.expire --window-hours 48` → `{"users": 2, "expired": 0, "alerts": 3}` (Nike, Target, McDonald's all expire 2026-10-19); rerun → 0 alerts (deduped per expiry version + window); expired transition + paging covered by suite. No in-app scheduler — must be cron'd (P2) |
| Per-user isolation on every endpoint | Works | Second user (…0002) on every endpoint: /wallet empty, /sync 0 rewards, /savings `{"total":"0.00"}`, /stack no rewards/card, redeem of demo's reward id → 404 and demo's reward stays active; every query is user_id-scoped inside `Database.transaction(user_id)`; redemptions use a composite FK `(user_id, reward_id) → rewards(user_id, id)` so a row can never reference another user's reward |
| Reward codes pgcrypto-encrypted at rest, decrypted in responses | Works | Raw column: `code_encrypted` hex starts `c30d0407…` (PGP symmetric packet), `::text LIKE '%HCOFALL10%'` → false; redeem response returns decrypted `HCOFALL10` for the owner; membership `member_id` also encrypted; wrong-key and cross-user decryption attempts covered by suite. Note: sync/events intentionally never return codes (asserted by delivery tests) — see P1 |
| No data via id guessing | Works | Foreign reward id → 404 (no existence oracle beyond that), foreign SSE cursor → 400, removing another user's card/membership is a no-op (suite) |

Counts: **9 Works / 3 Partial–Broken** (sync + events unwired, stack broken) of the items in scope.

## Fixes made (this PR)

- `backend/decisions/storage/migrations/003_redemptions.sql` — redemptions table, `(user_id, redeemed_at)` index, unique `(user_id, reward_id)` (idempotency), composite owner FK.
- `shared/seed/seed_redemptions.json` — 8 demo redemptions over the past 6 weeks totaling exactly $103.51 (Hollister, Taco Bell, Ulta, H&M, PacSun, McDonald's, Aéropostale, Target).
- `shared/seed/seed_rewards.json` — 8 matching historical `status=used` rewards so every redemption references a real, consistent reward.
- `backend/decisions/storage/seed.py`, `repository.py` — redemptions dataset in the seed ledger; `add_redemption` / `get_redemption_for_reward` / `list_redemptions`.
- `backend/decisions/savings/` (new) — `POST /rewards/{id}/redeem` and `GET /savings` per the README "NEW: Savings tracking" spec; money validated with the shared `exact_number` helper (rejects negatives and >2 decimals instead of silently rounding).
- `backend/tests/decisions/test_savings.py` — 5 tests: redeem marks used + row + single `reward_used` event + idempotency + at-rest ciphertext; face-value fallback + 422 validation; total==sum(items), items newest-first, series cumulative/sorted with same-day merge; per-user isolation + id guessing; seeded $103.51 with reseed no-op.
- `backend/decisions/memory.py` + router/service fallbacks — in-memory demo mode when `DATABASE_URL` is unset: GET /wallet, the /sync wallet bridge, redeem and /savings read the same in-memory store intake writes to (`backend.app.main.get_rewards()`), with seeded $103.51 redemptions; Postgres path identical when configured, and a configured-but-unavailable DB still 503s (pinned in `test_storage_wallet.py`).
- `backend/app/main.py` (authorized follow-up) — mounted the savings router and routed the wallet bridge through `wallet_snapshot` so `/sync` works in both modes.
- `backend/tests/decisions/test_memory_mode.py` — 3 tests running the real app without `DATABASE_URL`: wallet+sync 200 with isolation; seeded savings + idempotent redeem updating total/series; id-guessing 404s.

## Needs fix elsewhere (not this area's files)

| Where | Change | Priority |
|---|---|---|
| `backend/app/main.py` | ~~Mount savings router~~ (done in this PR, authorized follow-up); still: replace `/sync`+`/events` stubs with `backend.decisions.delivery.router` and call its `startup/shutdown` in lifespan (stub /sync leaks all plaintext codes from seed JSON and ignores `since`) | P0 → P1 after savings mount |
| `backend/app/main.py` + new `backend/decisions/stacking/` + `requirements.txt` | Real CP-SAT /stack: add `ortools`, read rewards/cards from the DB, enforce non-combinable pairs, max-one-promo-code, exclusions, and pick the best card via existing `backend.decisions.common.card_rate` (stub recommends `cards[0]`: $4.50 vs $22.50 on the Hollister fixture) | P0 (flagship demo moment) |
| `backend/app/schemas.py` + `scripts/gen_contracts.py` | Move `RedeemRequest`/`Redemption`/`SavingsPoint`/`SavingsSummary` from `backend/decisions/savings/schemas.py` into the public schemas and regenerate `shared/types.ts`/`openapi.json` | P1 |
| Stacking integration | Decide how decrypted codes reach checkout autofill: delivery tests assert sync/events never carry codes, and only the redeem response decrypts today; /stack results need owner-scoped `get_reward(reveal_code=True)` | P1 |
| Deploy (cron/Render job) | Schedule `python -m backend.decisions.jobs.expire` daily; nothing runs it automatically | P2 |
| `backend/tests/intake/test_service_e2e.py` | `chipotle_plaintext.eml` expects a GLiNER-extracted value; without ML models installed the fallback extracts a different value → env-dependent failure | P2 (passes with ML deps) |

## Test runs (DB up, `DATABASE_URL` + `TEST_DATABASE_URL` set)

- Full suite: `pytest backend/tests` → **419 passed, 1 failed, 20 skipped** (failure + skips are ML-model availability in intake/extraction, outside this area).
- This area: `test_storage_wallet.py` 13 passed · `test_delivery.py` 11 passed, 1 skipped (real-Chromium client; needs NODE_BINARY/Playwright) · `test_contracts.py` 42 passed (incl. the wallet/sync contract tests that need Postgres) · `decisions/test_savings.py` 5 passed · `decisions/test_memory_mode.py` 3 passed (app run without `DATABASE_URL`).
