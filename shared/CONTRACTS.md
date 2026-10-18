# Lapse API Contracts

Complete API documentation for frontend and backend integration.

> **Source of Truth**: `backend/app/schemas.py`  
> **Generated Specs**: `shared/openapi.json`, `shared/types.ts`

## Base URL

- Development: `http://localhost:8000`
- Production: TBD

## Authentication

**Hackathon simplification**: Pass user ID in header.

```
X-User-Id: 00000000-0000-0000-0000-000000000001
```

Demo user ID: `00000000-0000-0000-0000-000000000001`

## Error Format

Errors raised by endpoint handlers return:

```json
{
  "error": "HTTP_400",
  "message": "Human-readable error message",
  "details": {}
}
```

**Caveat (verified)**: two error classes bypass this shape today — unknown
routes return FastAPI's default `{"detail": "Not Found"}` (404) and request
validation failures return `{"detail": [...]}` (422). Clients should fall back
to `response.status` when `message` is absent (both frontends already do).

---

## Endpoints

### Health Check

```
GET /health
```

**Response** `200 OK`:
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "timestamp": "2026-10-18T12:00:00Z",
  "services": {
    "database": "healthy",
    "email_intake": "healthy",
    "extraction": "healthy",
    "stacking": "healthy"
  }
}
```

---

### Inbound Email (Postmark Webhook)

```
POST /inbound
```

**Headers**:
- `Content-Type: application/json`
- `X-User-Id: <uuid>` (optional, can derive from MailboxHash)

**Request Body** (Postmark inbound format):
```json
{
  "MessageID": "msg-001",
  "FromFull": {"Email": "rewards@hollisterco.com", "Name": "Hollister Co."},
  "ToFull": [{"Email": "demo@lapse.app", "Name": ""}],
  "Subject": "Your 10% Off Voucher",
  "TextBody": "...",
  "HtmlBody": "...",
  "Date": "Tue, 15 Oct 2026 10:30:00 -0700",
  "MailboxHash": "user123",
  "Attachments": [],
  "Headers": []
}
```

**Response** `200 OK`:
```json
{
  "message_id": "msg-001",
  "classification": "reward",
  "rewards_extracted": 1,
  "reward_ids": ["22222222-2222-2222-2222-222222222201"],
  "needs_review": false,
  "processing_time_ms": 150,
  "duplicate": false,
  "note": null
}
```

**Classification values**: `reward`, `receipt`, `promo`, `other`

The live service returns a superset of `InboundResult` (verified against the
running app): `duplicate` is `true` when the MessageID was already processed,
and `note` is `null` or one of `"duplicate"`, `"unknown_recipient"`,
`"extraction_error"`. All of those outcomes still return 200 with
`rewards_extracted: 0` so Postmark never retries. Only a non-JSON body gets 400.

---

### Demo Email Injection

```
POST /demo/inject
```

Replay a stored `.eml` file through the pipeline for testing.

**Request**:
```json
{
  "eml_filename": "hollister_10_percent.eml",
  "user_id": "00000000-0000-0000-0000-000000000001",
  "force": true
}
```

`force` (optional, default `false`) bypasses the dedupe check so the same email
can be replayed repeatedly during a demo. Without it, a second inject of the
same file returns `duplicate: true` with `rewards_extracted: 0`.

**Available test emails**:
- `hollister_10_percent.eml` - JSON-LD discount offer
- `target_jsonld_offer.eml` - JSON-LD offer
- `chipotle_plaintext.eml` - Plain text only
- `nike_promo.eml` - Promotional email
- `amazon_receipt.eml` - Receipt (not a reward)

**Response**: Same as `/inbound`

### List Demo Emails

```
GET /demo/emails
```

**Response** `200 OK`: `{"emails": ["amazon_receipt.eml", "chipotle_plaintext.eml", ...]}`
(the filenames accepted by `/demo/inject`).

A demo merchant console UI is served at `GET /demo/console` (redirects to its
index page) when the console module is present.

---

### Get Wallet

```
GET /wallet
```

**Headers**: `X-User-Id: <uuid>`

**Response** `200 OK`:
```json
{
  "user_id": "00000000-0000-0000-0000-000000000001",
  "cards": [
    {
      "id": "33333333-3333-3333-3333-333333333301",
      "user_id": "00000000-0000-0000-0000-000000000001",
      "issuer": "Chase",
      "network": "visa",
      "name": "Sapphire Preferred (DEMO)",
      "last_four": "4242",
      "base_rate": "1.0",
      "category_rates": [
        {"category": "Dining", "mcc_codes": ["5812", "5813", "5814"], "rate": "3.0"}
      ],
      "is_demo": true,
      "created_at": "2026-01-15T10:00:00Z"
    }
  ],
  "memberships": [
    {
      "id": "44444444-4444-4444-4444-444444444401",
      "merchant_name": "Costco",
      "program_name": "Executive Membership",
      "tier": "Executive",
      "benefits": ["2% annual reward on qualified purchases"],
      "annual_reward_rate": "2.0"
    }
  ],
  "active_rewards_count": 25,
  "expiring_soon_count": 5
}
```

---

Wallet now requires configured Postgres and an externally supplied encryption key;
missing database configuration returns 503. Startup does not seed or migrate. Missing
identity uses the demo user only with `PERK_ALLOW_DEMO_IDENTITY=true`; conflicting
body/header identities return 400. Counts exclude expired, future, used, and review
rewards. See `docs/database-setup.md` for explicit migration/seed commands.

### Update Wallet

```
POST /wallet
```

**Request**:
```json
{
  "add_cards": [
    {
      "issuer": "Amex",
      "network": "amex",
      "name": "Blue Cash Preferred",
      "base_rate": "1.0",
      "category_rates": []
    }
  ],
  "remove_card_ids": [],
  "add_memberships": [],
  "remove_membership_ids": []
}
```

**Response**: Updated `Wallet` object

---

### Calculate Stack

```
POST /stack
```

Calculate optimal reward stacking for a purchase.

**Request**:
```json
{
  "user_id": "00000000-0000-0000-0000-000000000001",
  "merchant_id": "11111111-1111-1111-1111-111111111110",
  "domain": "hollisterco.com",
  "cart_total": "500.00",
  "items": [
    {"name": "Signature Hoodie", "category": "Tops", "price": "89.95", "quantity": 2}
  ]
}
```

**Response** `200 OK`:
```json
{
  "chosen_rewards": [
    {
      "reward_id": "22222222-2222-2222-2222-222222222201",
      "reward": { "...full Reward object..." },
      "savings": "50.00",
      "applied_order": 1
    }
  ],
  "recommended_card": {
    "id": "33333333-3333-3333-3333-333333333305",
    "name": "US Bank Cash+ (DEMO)",
    "base_rate": "1.0"
  },
  "card_cashback": "22.50",
  "original_price": "500.00",
  "final_price": "450.00",
  "total_savings": "72.50",
  "savings_percent": "14.50",
  "explanation": "Applied HCOFALL10 for percent_off (50.00 savings). Use US Bank Cash+ for 22.50 cashback. Total savings: $72.50",
  "alternatives": [],
  "solver_status": "optimal"
}
```

**Note**: Supply `merchant_id`, `domain`, or both. When both are supplied they must resolve to the same merchant; conflicting identities must be rejected. Cart items are partial and `cart_total` is authoritative. See `docs/person3-contract.md` for the Hollister fixture discrepancy and conservative eligibility policy (integration adoption pending).

---

### Lookup Rewards

```
POST /lookup
```

Find top relevant rewards for a merchant.

**Request**:
```json
{
  "user_id": "00000000-0000-0000-0000-000000000001",
  "merchant_id": null,
  "domain": "target.com",
  "query": null,
  "limit": 3
}
```

**Response** `200 OK`:
```json
{
  "merchant": {
    "id": "11111111-1111-1111-1111-111111111101",
    "name": "Target",
    "domain": "target.com",
    "mcc": "5311",
    "category": "Department Stores"
  },
  "rewards": [
    {
      "reward": { "...full Reward object..." },
      "score": 1.85,
      "value_component": 0.3,
      "match_component": 1.0,
      "urgency_component": 1.65,
      "days_until_expiry": 1
    }
  ],
  "total_available": 25
}
```

**Ranking formula**: `score = value_usd × match × (1 + exp(-days_left/3))`

---

### Sync (Polling)

```
GET /sync?since=2026-10-18T00:00:00Z
```

**Integration note**: This section and Events below describe the durable delivery
router in `backend/decisions/delivery/`. Integration must replace the existing
`/sync` and `/events` stubs and wire the delivery lifecycle before these semantics
are available in the shared application. See that module's `README.md` for wiring
and its `fetch-events.mjs` browser client.

> **Current behavior of the running app (verified)** — until the delivery router
> is wired in, `/sync` differs from the description below:
> - Without `DATABASE_URL` set, `/sync` returns **503** ("Database is not
>   configured") because it builds the wallet from Postgres. There is no
>   in-memory fallback. `/lookup`, `/stack` and `/events` still work in-memory.
> - It returns only `active` rewards (not used/expired/needs_review), ignores
>   `since`, always returns `pending_events: []`, and does **not** set the
>   `X-Event-Cursor` response header.
> - A missing `X-User-Id` header is resolved by the wallet layer, which returns
>   401 unless `PERK_ALLOW_DEMO_IDENTITY=true`. Always send the header.

**Headers**: `X-User-Id: <uuid>`

**Query Params**:
- `since` (optional): Inclusive UTC change watermark from the previous `last_sync`.
  Future watermarks return 400; legacy naive datetimes are interpreted as UTC.

**Response** `200 OK`:
```json
{
  "user_id": "00000000-0000-0000-0000-000000000001",
  "rewards": [ "...Reward objects, including used/expired/needs_review statuses..." ],
  "wallet": { "...complete authoritative Wallet object..." },
  "last_sync": "2026-10-18T12:00:00Z",
  "pending_events": []
}
```

**Response header**: `X-Event-Cursor: <user UUID>:<durable sequence>`.

With no `since`, replace the local reward set using this full snapshot (all
statuses); `pending_events` is empty rather than replaying historical events.
With `since`, upsert returned rewards by ID. Preserve status tombstones locally;
used, expired and needs_review records must leave active recommendation displays.
Every response's wallet is a full replacement, including empty cards/memberships
after removals. Never append its arrays to a cached wallet.

The service captures database UTC time after acquiring the owner lock, then reads
the reward snapshot/delta, full wallet, event watermark and pending events within
that same user transaction. The next watermark is the returned `last_sync`, never
the client's wall clock. Change predicates are inclusive (`updated_at >= since`,
event `created_at >= since`), so repeated boundary records/events are expected;
apply updates idempotently. Rewards referenced by selected durable events are
hydrated even if their caller-supplied `updated_at` is older than `since`.
Time-only expirations crossing `since` are projected as expired even before the
scheduled expiration job updates storage. Incremental event backlogs above 10,000
return 409 requesting a full snapshot, never a truncated successful delta.

Persist the applied snapshot and `X-Event-Cursor` together. Connect `/events` with
that value as `Last-Event-ID` to receive subsequent commits without a snapshot/replay
gap. Keep cursor state separate for each backend and user. Integration must expose
`X-Event-Cursor` through CORS for browser clients.

---

### Events (SSE)

```
GET /events
```

Server-Sent Events for durable replay and live updates.

**Headers**:
- `X-User-Id: <uuid>`
- `Accept: text/event-stream`
- `Last-Event-ID: <user UUID>:<durable sequence>` (optional)

Missing identity returns 401 unless explicit demo fallback is enabled through
`PERK_ALLOW_DEMO_IDENTITY=true`. X-User-Id remains demo identification, not
authentication. Invalid UUIDs or malformed, foreign-user or future cursors return
400. Never manufacture cursors; use server-issued values from sync or SSE.

Without `Last-Event-ID`, replay starts at sequence zero. With a cursor, only greater
sequences for that user are returned. Events are delivered at least once; apply
idempotently and persist a checkpoint only after the corresponding local state
update succeeds. Each client owns its own checkpoint. Sequence gaps caused by
rollbacks or other users are normal. Periodic sync still reconciles wallet changes.

**Event Types**:

| Event | Description |
|-------|-------------|
| `reward_added` | New reward committed |
| `reward_expiring` | Reward approaching expiry within the configured alert window |
| `reward_updated` | Reward status or details changed, including expiry |
| `reward_used` | Reward marked as used |
| `sync_complete` | Initial event catch-up marker; not a reward mutation |

**Event Format** (the ID prefix is the complete user UUID):
```
id: 00000000-0000-0000-0000-000000000001:42
event: reward_added
data: {"event_type":"reward_added","timestamp":"2026-10-18T12:00:00Z","user_id":"00000000-0000-0000-0000-000000000001","reward_id":"...","data":{"status":"active","expires_at":null}}

id: 00000000-0000-0000-0000-000000000001:43
event: reward_expiring
data: {"event_type":"reward_expiring","timestamp":"2026-10-18T12:00:00Z","user_id":"00000000-0000-0000-0000-000000000001","reward_id":"...","data":{"status":"active","expires_at":"2026-10-19T00:00:00+00:00"}}
```

Events contain safe status/expiry metadata, never plaintext reward codes or
membership identifiers. Fetch current models through `/sync` as needed. Comment
heartbeats keep idle connections alive; reconnect after disconnects using the last
successfully applied cursor.

> **Current behavior of the running app (verified)** — until the delivery router
> is wired in, `/events` is an in-memory stream that differs from the above:
> - No `id:` lines are sent and `Last-Event-ID` is ignored; there is no durable
>   replay. Events queued before the first connect are delivered once, then lost.
> - A `sync_complete` event is sent on connect, and a stub `reward_expiring`
>   event (data: `{"message": ...}`) fires every 30 seconds.
> - `reward_added` events are emitted by intake with `data` =
>   `{"merchant_name", "kind", "value", "code", "source"}` — note this currently
>   **does include the plaintext code**, which the extension uses for its toast
>   text. The durable router will drop codes from events; the frontend must then
>   fetch the code via `/sync` (toast should degrade to merchant + kind).
> - `timestamp` is a naive datetime with **no timezone suffix** (e.g.
>   `2026-10-18T07:44:04.206305`); treat it as UTC. Aware fields elsewhere
>   serialize with `Z`.
> - A missing `X-User-Id` falls back to the demo user (no 401).

**Frontend Usage**:

Native `EventSource` does not support custom request headers. Passing a `headers`
option does not send X-User-Id or Last-Event-ID; use the delivery module's tested
fetch-stream client instead. Import/vendor `backend/decisions/delivery/fetch-events.mjs`
into the extension and supply an application callback that applies changes and
checkpoints atomically:

```javascript
import {connectEvents} from './fetch-events.mjs';

const controller = new AbortController();
await connectEvents({
  url: `${apiBase}/events`,
  userId,
  lastEventId: savedCursor, // X-Event-Cursor after applying sync, or a saved SSE ID
  signal: controller.signal,
  apply: async (event, id) => {
    await applyAndCheckpoint(event, id);
  },
});
// controller.abort() disconnects; persist state/cursors across MV3 worker restarts.
```

The client uses `fetch` with X-User-Id, Accept and Last-Event-ID headers, parses
streamed SSE frames, and reconnects with its checkpoint. Integration must allow
these request headers and expose X-Event-Cursor through CORS. The extension also
requires host permission for the backend origin.

---

### Classify Merchant

```
POST /classify-merchant
```

Classify an unknown merchant by domain.

**Request**:
```json
{
  "domain": "unknownstore.com",
  "page_title": "Unknown Store - Home"
}
```

**Response** `200 OK`:
```json
{
  "domain": "unknownstore.com",
  "merchant_id": null,
  "merchant_name": "Unknown Store",
  "category": "Miscellaneous Retail",
  "mcc": "5999",
  "confidence": 0.3,
  "is_new": true
}
```

For known merchants:
```json
{
  "domain": "target.com",
  "merchant_id": "11111111-1111-1111-1111-111111111101",
  "merchant_name": "Target",
  "category": "Department Stores",
  "mcc": "5311",
  "confidence": 0.95,
  "is_new": false
}
```

### Savings & Redemption (planned, Person 3 — NOT yet implemented; both return 404 today)

| Endpoint | Description | Status |
|----------|-------------|--------|
| `POST /rewards/{id}/redeem` | Mark a reward used, record a redemption, emit `reward_used` | planned, Person 3 |
| `GET /savings` | Total savings, itemized redemptions (newest first), cumulative daily series | planned, Person 3 |

The web dashboard (`frontend/web/src/api/savings.ts`) is already built against
this exact contract (mocked by default). Agreed shapes:

```
POST /rewards/{id}/redeem
Headers: X-User-Id
Body: {"saved": "12.50"}        // decimal dollars string; optional per spec
-> 200: the updated Reward object (status = "used")

GET /savings
Headers: X-User-Id
-> 200: {
  "total": "103.51",
  "items": [
    {"reward_id": "...", "merchant_name": "Hollister", "description": "...",
     "saved": "10.00", "redeemed_at": "2026-09-08T18:12:00Z"}
  ],                                            // newest first
  "series": [{"date": "2026-09-08", "cumulative": "10.00"}]
                 // one point per UTC day with a redemption, running total
}
```

Money is a decimal-dollars string (never cents); `date` is `YYYY-MM-DD` UTC.
Demo seed must total exactly **$103.51**.
See `backend/decisions/README.md` ("NEW: Savings tracking") for the full spec.

---

## Enums

### RewardKind

| Value | Description |
|-------|-------------|
| `percent_off` | Percentage discount (e.g., 10% off) |
| `amount_off` | Fixed amount discount (e.g., $5 off) |
| `points` | Points reward (e.g., 150 Starbucks stars) |
| `free_item` | Free item reward (e.g., free guacamole) |
| `bogo` | Buy One Get One |
| `cashback` | Cashback reward |

### RewardSource

| Value | Description |
|-------|-------------|
| `email_jsonld` | Extracted from schema.org JSON-LD in email |
| `gliner` | Extracted via GLiNER2 NER |
| `regex` | Extracted via regex fallback |
| `manual` | User-entered |
| `seed` | Demo/test seed data |

### RewardStatus

| Value | Description |
|-------|-------------|
| `active` | Ready to use |
| `needs_review` | Low confidence, user should verify |
| `used` | Already redeemed |
| `expired` | Past expiration date |

### CardNetwork

| Value | Description |
|-------|-------------|
| `visa` | Visa |
| `mastercard` | Mastercard |
| `amex` | American Express |
| `discover` | Discover |

### EmailClassification

| Value | Description |
|-------|-------------|
| `reward` | Contains extractable reward/coupon |
| `receipt` | Purchase receipt |
| `promo` | Promotional (no specific offer) |
| `other` | Not shopping-related |

---

## Type Definitions

Full TypeScript types are available in `shared/types.ts`.

```typescript
import { Reward, StackResult, Wallet } from '../shared/types';
```

Full JSON Schema files are in `shared/schemas/`.

---

## CORS

The API intends to allow requests from:
- `chrome-extension://*`
- `http://localhost:*`
- `http://127.0.0.1:*`

**Known gap (verified)**: Starlette's `allow_origins` does exact string matching,
so the `http://localhost:*` / `http://127.0.0.1:*` entries in
`backend/app/main.py` match nothing. Only `chrome-extension://.*` works today
(via `allow_origin_regex`). Preflight from `http://localhost:5173` (the web
dashboard dev server) currently returns **400 "Disallowed CORS origin"**. Fix
in `main.py`: replace `allow_origin_regex` with
`r"chrome-extension://.*|https?://(localhost|127\.0\.0\.1)(:\d+)?"`.

---

## Rate Limits

No rate limits implemented for hackathon. In production, consider:
- `/stack`: 10 req/min per user
- `/lookup`: 30 req/min per user
- `/events`: 1 connection per user

---

## Frontend integration notes (contracts audit, Oct 18)

Verified against a running in-memory backend (`uvicorn backend.app.main:app`,
no `DATABASE_URL`). Applies to `cursor/web-dashboard-2556` and
`cursor/lapse-extension-6787`.

**Works live today, as typed** (keep `VITE_USE_MOCKS=false` paths as-is):
- `POST /lookup`, `POST /stack`, `POST /classify-merchant`, `POST /inbound`,
  `POST /demo/inject` (supports `"force": true`), `GET /demo/emails`,
  `GET /health`. Shapes match `shared/types.ts` exactly; all money fields are
  decimal strings (`Number(value)` parses them — note `/stack` may return more
  than 2 decimal places, e.g. `"50.0000"`; your `money()`/`toCents()` helpers
  already handle this). Enum values match `shared/types.ts` enums exactly.
- `X-User-Id` header: send it on every call (you already do). On stub endpoints
  a missing header silently becomes the demo user; on `/wallet` and `/sync` it
  is a **401** unless the server sets `PERK_ALLOW_DEMO_IDENTITY=true`.

**Will fail in live mode until backend changes land — keep mocks as default:**
1. `GET /savings` and `POST /rewards/{id}/redeem` → **404** (not implemented).
   The shapes in `frontend/web/src/api/savings.ts` match the agreed backend spec
   exactly (including `saved` as decimal dollars and `date` as `YYYY-MM-DD`), so
   no frontend change needed when they land.
2. `GET /sync` and `GET /wallet` → **503** without Postgres. The extension's
   `/sync` polling fallback and the web dashboard's `getSync` both hit this.
   No frontend change needed; backend must restore an in-memory path or the
   demo must run with `DATABASE_URL` set.
3. Web dashboard CORS: `http://localhost:5173` is **blocked** by the current
   backend CORS config (see Known gap above). Extension origins are fine.

**SSE specifics for the extension** (`core/sse.ts` parser is compatible):
- No `id:` lines are sent; `Last-Event-ID` is ignored. Your parser ignoring
  `id:` is correct for now.
- `reward_added` `data` currently includes `merchant_name`, `kind`, `value`,
  `code`, `source` — your `toastMessage()` works. When the durable delivery
  router lands, `code` will disappear from events; keep the existing
  "no code → shorter toast" fallback.
- Event `timestamp` has no timezone suffix; treat as UTC (you only use it as a
  dedupe key, which is fine).
- Expect a stub `reward_expiring` every 30s with `data.message` only — don't
  render it as a real expiry alert yet.
- `/sync` polling as an events fallback yields no toasts even with a database:
  `pending_events` is always `[]` in the stub.
