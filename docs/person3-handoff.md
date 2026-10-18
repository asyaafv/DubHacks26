# Foundation and wallet handoff

Branch: `codex/person3-foundation`. Initial foundation milestone: `648d082`.
Checkout: `lapse-foundation/` inside the original empty local repository; the outer
repository was left untouched. This implementation is based on origin/main at a2e1def.

## Exact integration points

- `backend.decisions.storage.Database.connect()` / `close()` for lifecycle.
- `async with database.transaction(user_id) as repo:` for a complete atomic operation.
- `backend.decisions.dependencies.get_database(request)` for FastAPI DI.
- `backend.decisions.wallet.router.router` exports the already-wired wallet router.
- `backend.decisions.common.resolve_user(header, body_user_id=None)`, `utc()`,
  `canonical_domain(value)`, `card_rate(card, category=None, mcc=None)`.
- Persons 1/2: `repo.claim_email(...)`, `save_reward(Reward, dedupe_key=...,
  embedding=...)`, `set_email_result(...)` in one transaction.
- Lookup/stacking: `repo.resolve_merchant(...)`, `list_rewards(...)`,
  `search_rewards(...)`, `get_reward(id, reveal_code=True)` only when needed,
  `get_wallet()`. These return public Pydantic models.
- Delivery: `repo.list_events(after=sequence, limit=100)` returns StoredEvent
  objects containing id, sequence and public Event. `append_event(...)` deduplicates
  alerts via dedupe_key; `set_reward_status(...)` changes status and emits an event
  atomically. Use `list_rewards(eligible_only=False)` for status reconciliation.
  Supply an explicit user ID to each expiry job transaction; no unscoped reward scan
  or global mutation helper is exported.

See person3-contract.md for signatures, semantics, ownership and transaction rules.
Never share the raw connection or log decrypted model values.

## Actual verification

- Real PostgreSQL 17.11 with pgvector 0.8.7 and pgcrypto, isolated temporary cluster.
- Python 3.10.11 on this host; code/generator remain compatible with the repository's
  Python 3.11+ target.
- Full backend suite: **53 passed**, including 11 new storage/wallet tests. Three
  deprecation warnings come from the retained startup hook and TestClient/AnyIO.
- Tested encryption/correct-key decryption/wrong-key rejection, cross-user code,
  vector, wallet, event, deletion and status attempts, composite event owner FK,
  reward/email/event rollback, concurrent commit-order replay, per-user email and
  reward deduplication, alert deduplication, exact rates and query-time counts,
  wallet atomicity and API identity handling, repeat migration/seed and reconnection.
- Additionally stopped and restarted the actual Postgres server process: wallet,
  decrypted reward values and ordered event IDs/cursors were identical afterward.
- Contract generation succeeded; JSON schemas, TypeScript and public models are
  unchanged. Generated OpenAPI changes only the two wallet descriptions. The script
  needed a pre-existing f-string syntax repair and canonical backend package imports.
- `compileall` and `git diff --check` passed.
- Docker is absent here: the Compose recipe was not launched. Native Postgres
  exercised the migrations, extensions, encryption path and backend tests.

## Remaining coordination

P2 must confirm `sentence-transformers/all-MiniLM-L6-v2`, 384 dimensions, cosine.
Catalog writes currently insert-only; adding embeddings to existing catalog rows
should be coordinated with foundation rather than changing schema independently.
Integration owns applying shared identity/merchant semantics and persisted reads to
stack/lookup/sync/delivery and replacing the remaining stub health/service labels.
Those routes keep their previous behavior in this branch, including the old demo
fallback, until their owners adopt resolve_user. The existing sync stub has only a
wallet compatibility bridge; its rewards/events are still the delivery owner's work.
The existing on_event startup hook is superseded by the new lifespan; remaining
stub routes load their JSON caches lazily. Integration should remove that stale hook.

Cart items are partial: Hollister has $479.65 listed versus $500 total. The $20.35
remainder is unknown, so full fixture savings require an explicit eligibility
assumption by the stacking owner. Membership text alone never creates cash offers.

Run explicit migration/seed commands from database-setup.md before starting the API.
Keep encryption keys outside source and DB. X-User-Id is demo identification, not
authentication. No external team messages or notifications were sent.

## Delivery storage additions

Foundation also provides bounded `Database.list_user_ids(...)` for trusted scheduler
registry enumeration, plus user-locked `Repository.list_expiration_candidates(...)`,
`snapshot_time()` and `list_events_since(...)`. Exact signatures and the admin-only
registry boundary are documented in person3-contract.md. They add no HTTP endpoints,
public models or global reward/event reads. New real-Postgres tests cover keyset
pagination through status mutations, overdue backlog, cross-user exclusion, UTC DB
watermarks and replay of events whose reward timestamps predate the watermark.

Additive-interface verification: **13 storage/wallet tests passed** against the same
real PostgreSQL cluster (one existing TestClient/AnyIO deprecation warning).

`Repository.event_watermark() -> int` additionally provides the locked owner
maximum sequence (0 empty) for snapshot-to-SSE handoff without history retrieval.

Shared API documentation now describes delivery's full/all-status snapshots,
inclusive incremental upserts, replacement wallets, database-clock watermark,
outbox hydration, X-Event-Cursor handoff and fetch-based header-bearing SSE client.
These semantics require the integration owner to replace the remaining route stubs;
this documentation update changes no public models, generated schemas or wiring.
