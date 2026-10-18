# Person 3 foundation contract

The public source of truth remains backend/app/schemas.py. No public model changes
are required. This document defines internal interfaces and resolves ambiguities.

## Ownership and exports

Foundation owns decisions/storage, decisions/wallet, decisions/common.py, migrations,
database scripts and Python dependency manifests. Other chats own stacking, lookup,
delivery/expiration and integration. Intake/extraction remain Persons 1/2.
Each HTTP feature exports `router: APIRouter` from `backend.decisions.<feature>.router`.
Wallet exports `backend.decisions.wallet.router.router`. Integration owns subsequent
main.py wiring; this branch changes only lifecycle and wallet wiring.

## Database and dependency injection

`Database.connect()` reads DATABASE_URL and PERK_ENCRYPTION_KEY (at least 32 random
characters, supplied outside repo and DB). `close()` closes the pool. FastAPI lifespan
stores it in `app.state.database`; `get_database(request)` is overridable in tests.
Missing DB configuration produces wallet 503, never an in-memory persistence fallback.
Startup does not migrate or seed. `python -m backend.decisions.storage migrate|seed`
is explicit. Migrations run under one transaction/advisory lock; 001 preserves the
original docs/schema.sql. Existing manually initialized databases must record 001 in
schema_migrations after verifying that baseline, before applying 002.

`async with database.transaction(user_id) as repo:` is the only unit of work.
Repository methods do not commit. Exit commits; exceptions roll back all changes and
events. Do not open a second unit of work inside one. User row locks serialize writes
before event sequence allocation, guaranteeing replay cursor order for each user.
Use only the scoped repo (never raw conn) in feature services. Merchant catalog is
shared; every reward/card/membership/email/event operation is scoped to repo.user_id.
X-User-Id is demo identification, NOT authentication or a security boundary against
impersonation. Production requires authenticated identity before using this API.

## Normalized reward persistence (Persons 1 and 2)

`await repo.save_reward(reward: Reward, *, dedupe_key: str | None = None,
embedding: list[float] | None = None) -> bool`: insert validated normalized reward,
return false on an existing ID or per-user dedupe key; reject mismatched owner.
Code is encrypted via pgcrypto using a bound runtime key. Successful insert appends
reward_added in the same transaction. Provide a stable non-secret dedupe key (e.g.
HMAC of canonical offer); pipeline decides normalization and deduplication policy.
Do not put codes or membership identifiers in any other reward field.
`claim_email(message_id, classification, *, content_hash=None, rewards_extracted=0)`
returns bool, enforcing per-user message ID and optional content hash uniqueness.
`set_email_result(message_id, classification, rewards_extracted)` updates metadata.
Claim, save all extracted rewards, and set result in ONE transaction. On extraction
failure roll back the transaction or explicitly persist failure outside it; never
commit a claim that must be retried. No email body is stored here.

`get_reward(id, reveal_code=False)`, `list_rewards(eligible_only=True, now=None,
since=None)`, `search_rewards(embedding, limit=10, now=None)` return Reward models.
Default reads redact codes. `set_reward_status(id, status)` emits reward_used or
reward_updated atomically and returns false for missing/foreign/no-op changes.
Keep status tombstones; do not physically delete rewards needed by offline sync.
Vector searches never cross users. `resolve_merchant(merchant_id=None, domain=None)`
returns Merchant or None; both may be supplied only if they resolve to the same row.
`save_merchant(merchant, embedding=None)` is the shared catalog write boundary for P2.

## Durable delivery interfaces

`append_event(event_type, reward_id=None, *, dedupe_key=None) -> bool` accepts no
arbitrary payload. It stores only safe reward status/expiry metadata, never codes.
Use a stable expiring-alert dedupe key containing reward ID and expiration version.
`list_events(after=0, limit=100) -> list[StoredEvent]` is ordered by sequence and
scoped to the owner. StoredEvent has id, sequence and event (public Event model).
The delivery chat uses sequence as SSE cursor. Sequence is the authoritative
change feed: timestamp-only polling cannot guarantee replay of writes whose caller
supplied an old timestamp. Integration should reconcile through the durable sequence
and deduplicate overlapping snapshots by event/reward ID. `list_rewards(eligible_only=False,since=...)`
includes used/expired/review records for offline state reconciliation. Events are
retained regardless of the legacy delivered flag; do not globally consume events.
Delivery owns schedulers, expiry scans, SSE and sync HTTP behavior.

## Shared semantic decisions

All internal timestamps are aware UTC; legacy naive model defaults are interpreted
as UTC at the storage boundary. Use Decimal, decimal strings in JSON, integer cents
in optimizers, ROUND_HALF_UP only at final monetary boundaries. Money is validated
at two decimals; reward values/rates support six decimals. Rates are percentage
points (3 means 3%, not .03). No float arithmetic for money.

Eligible means status active, starts_at absent or <= now, expires_at absent or > now.
All query-time eligibility and wallet counts use this predicate. Expiring soon means
eligible and expires_at <= now + 3 days. Status transitions remain visible to sync.
Unknown compatibility defaults false, unknown eligibility defaults ineligible.
Membership text/annual rates alone never create monetary offers: structured scope,
thresholds, caps, exclusions and compatibility must first be known. No inferred
membership discount is supplied by foundation.

Canonical domains are lowercase hostnames, stripped of www. and a trailing dot.
No suffix/substring matching. Merchant ID and domain together must agree, including
the Hollister fixture. IDs are authoritative only when no domain is supplied.
Cart items are PARTIAL. cart_total is authoritative; Hollister items total $479.65
and cart_total is $500.00, leaving $20.35 unclassified. Never silently scale items or
assert that unlisted items pass exclusions. Stacking owns conservative eligibility
for that unknown remainder; fixture savings are conditional on its eligibility.

Embedding contract: vector(384), sentence-transformers/all-MiniLM-L6-v2, finite,
nonzero vectors, cosine distance; no mixed models. P2 must confirm this model before
writing embeddings; foundation validates dimensions and adds no ML dependency.
Changing model/dimension requires a coordinated schema migration and re-embedding.

`resolve_user(header, body_user_id=None)` rejects conflicting IDs with 400 and
invalid UUIDs with 400. Missing identity uses demo UUID ONLY when
PERK_ALLOW_DEMO_IDENTITY=true; otherwise 401. Wallet also checks a supplied extra
body user_id so Pydantic's ignored extras cannot conceal an identity conflict.
Integration must apply this helper to other endpoints; foundation leaves their
existing routes untouched. Never log SQL parameters, codes, keys or decrypted models.

## Wallet service

GET/POST /wallet preserve Wallet/WalletUpdate. Wallet additions accept product data,
never PANs, CVVs or last-four input. Removals include owner predicate and are no-ops
for unknown/foreign IDs. An entire update and resulting wallet read share one
transaction. `card_rate(card, category=None, mcc=None)` returns exact Decimal:
MCC-constrained rates require MCC match; category-only rates require exact normalized
category match; unknown categories (including auto-top-category) earn base only.

## Contract-generation handoff

Public models, operation IDs, header names, JSON schemas and TypeScript types are
unchanged. Shared merchant catalog writes currently insert-only; an existing
merchant ID/domain returns false rather than overwriting Person 2 classification.
The generator was repaired for Python 3.11-compatible f-strings and
canonical package imports, then rerun; only wallet OpenAPI descriptions changed.
Behavior changes from the stub: persistence, 503 for missing DB, explicit demo
fallback, 400 identity conflicts, 422 invalid rates/number-data fields, accurate
query-time counts, and last_four remains null. This is the team-facing notification;
no external messages are sent. Other endpoints retain their original behavior
until their owners adopt the documented shared helpers.

## Delivery scan and watermark additions

`await database.list_user_ids(after: UUID | None = None, limit=100) -> list[UUID]`
is a trusted background scheduler registry operation, never a user-facing route.
It returns only registered IDs in ascending UUID keyset pages, at most 1000/page.
Do not expose this administrative enumeration through demo identity endpoints.
Every owned-data operation following enumeration still requires
`database.transaction(user_id)`; there are no global reward/event scans.

Inside that locked transaction:

- `await repo.snapshot_time() -> datetime`: aware UTC `clock_timestamp()` from
  Postgres, sampled after acquiring the per-user lock; independent of host skew.
- `await repo.list_expiration_candidates(now, window_end, after=None, limit=100)
  -> list[Reward]`: owner-scoped, status active, expiration <= window_end, including
  expiration <= now. Null expiry, used/review/expired statuses and foreign users
  are excluded. Codes are redacted. UUID keyset order and a maximum of 1000/page
  allow status mutations while scanning; window_end must be >= now. Delivery owns
  start-time alert eligibility, expiry transitions and durable dedupe keys.
- `await repo.list_events_since(since, after=0, limit=100) -> list[StoredEvent]`:
  owner-scoped created_at >= since AND sequence > after, ordered by sequence, at
  most 1000/page. Uses durable insertion time even when callers supplied old reward
  timestamps. Pass the last sequence as after on every following page. Inclusive
  timestamp overlap requires deduplication by StoredEvent.id or sequence.

No public schema/router changes or new migrations are required for these additions.

`await repo.event_watermark() -> int` returns the maximum event sequence scoped to
that locked owner, or 0 when empty. Capture alongside snapshot_time and snapshot
reads in the SAME transaction for a snapshot-to-SSE boundary. It does not scan or
return event history and cannot reveal another user's cursor. The current
transaction's own writes are included; do not publish the watermark until commit.
Delivery may expose it as an X-Event-Cursor response header without model changes;
integration owns header/CORS wiring.
