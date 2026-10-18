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
scoped to the owner. StoredEvent has sequence and event (public Event model).
The delivery chat uses sequence as SSE cursor; timestamp-only polling may overlap
and must deduplicate by event/reward ID. `list_rewards(eligible_only=False,since=...)`
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
