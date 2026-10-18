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

All errors return:

```json
{
  "error": "HTTP_400",
  "message": "Human-readable error message",
  "details": {}
}
```

---

## Endpoints

### Savings tracking

`POST /rewards/{id}/redeem` uses `X-User-Id` and accepts `{"saved":"12.50"}`.
It returns the owned Reward with status `used`, atomically records its savings,
and appends a durable `reward_used` event. Requests are idempotent per user/reward.
The optional `cart_total` permits exact percent/amount-off calculation when saved
is omitted; without a cart the nominal face value is used. Applied stacks should
send each chosen reward's actual savings explicitly.

`GET /savings` uses the same header and returns:

```json
{
  "total": "103.51",
  "items": [{"reward_id":"77777777-7777-7777-7777-777777777708", "merchant_name":"Target", "description":"Circle offer on a previous purchase", "saved":"15.00", "redeemed_at":"2026-10-17T06:00:00Z"}],
  "series": [{"date":"2026-10-17", "cumulative":"103.51"}]
}
```

The arrays above are abbreviated. Items are newest first; series contains one
ascending UTC daily point per redemption day, with cumulative totals over the
complete history. All money is a two-decimal string. Empty history has total
`"0.00"` and empty arrays. Only USD is aggregated. `/wallet` additionally exposes
eligible owned `rewards`, preserving `expires_at` for calendar rendering.
See `docs/savings-tracking.md` for status/error, startup demo seed and integration
details, including the pending live delivery and extension hookup.

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
  "processing_time_ms": 150
}
```

**Classification values**: `reward`, `receipt`, `promo`, `other`

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
  "user_id": "00000000-0000-0000-0000-000000000001"
}
```

**Available test emails**:
- `hollister_10_percent.eml` - JSON-LD discount offer
- `target_jsonld_offer.eml` - JSON-LD offer
- `chipotle_plaintext.eml` - Plain text only
- `nike_promo.eml` - Promotional email
- `amazon_receipt.eml` - Receipt (not a reward)

**Response**: Same as `/inbound`

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
missing database configuration returns 503. Startup loads the one-time demo savings
history only; it does not migrate or reset the existing wallet/reward datasets. Missing
identity uses the demo user only with `LAPSE_ALLOW_DEMO_IDENTITY=true`; conflicting
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
`LAPSE_ALLOW_DEMO_IDENTITY=true`. X-User-Id remains demo identification, not
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

### Savings & Redemption (planned, Person 3)

| Endpoint | Description | Status |
|----------|-------------|--------|
| `POST /rewards/{id}/redeem` | Mark a reward used, record a redemption, emit `reward_used` | planned, Person 3 |
| `GET /savings` | Total savings, itemized redemptions (newest first), cumulative daily series | planned, Person 3 |

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

The API allows requests from:
- `chrome-extension://*`
- `http://localhost:*`
- `http://127.0.0.1:*`

---

## Rate Limits

No rate limits implemented for hackathon. In production, consider:
- `/stack`: 10 req/min per user
- `/lookup`: 30 req/min per user
- `/events`: 1 connection per user
