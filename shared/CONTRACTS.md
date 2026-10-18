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

**Note**: Use either `merchant_id` OR `domain`, not both.

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

**Headers**: `X-User-Id: <uuid>`

**Query Params**:
- `since` (optional): Only return changes since this timestamp

**Response** `200 OK`:
```json
{
  "user_id": "00000000-0000-0000-0000-000000000001",
  "rewards": [ "...array of active Reward objects..." ],
  "wallet": { "...Wallet object..." },
  "last_sync": "2026-10-18T12:00:00Z",
  "pending_events": []
}
```

---

### Events (SSE)

```
GET /events
```

Server-Sent Events for real-time updates.

**Headers**:
- `X-User-Id: <uuid>`
- `Accept: text/event-stream`

**Event Types**:

| Event | Description |
|-------|-------------|
| `reward_added` | New reward extracted from email |
| `reward_expiring` | Reward expiring within 24 hours |
| `reward_updated` | Reward status or details changed |
| `reward_used` | Reward marked as used |
| `sync_complete` | Initial sync completed |

**Event Format**:
```
event: reward_added
data: {"event_type":"reward_added","timestamp":"2026-10-18T12:00:00Z","user_id":"...","reward_id":"...","data":{}}

event: reward_expiring
data: {"event_type":"reward_expiring","timestamp":"2026-10-18T12:00:00Z","user_id":"...","reward_id":"...","data":{"expires_in_hours":12}}
```

**Frontend Usage**:
```typescript
const eventSource = new EventSource('/events', {
  headers: { 'X-User-Id': userId }
});

eventSource.addEventListener('reward_added', (e) => {
  const event = JSON.parse(e.data);
  // Handle new reward
});
```

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
