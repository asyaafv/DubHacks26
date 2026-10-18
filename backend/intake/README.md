# Intake Module (Person 1)

Email ingestion pipeline: Postmark webhook → PII redaction → dedupe → classification handoff.

## Ownership

- `POST /inbound` - Postmark webhook endpoint
- `POST /demo/inject` - Test email replay
- PII redaction (Presidio)
- Email deduplication
- Demo merchant console (sends test reward emails)

## Pipeline Flow

```
Postmark Webhook
      ↓
Parse InboundEmail
      ↓
Presidio PII Redaction ──→ Redact: card numbers, phones, emails, addresses
      ↓
Dedupe Check ──→ Skip if MessageID already processed
      ↓
Hand off to Extraction module (SetFit + NER)
      ↓
Return InboundResult
```

## Inputs

### InboundEmail (from Postmark)

```python
class InboundEmail(BaseModel):
    MessageID: str
    FromFull: dict[str, Any]  # {"Email": "...", "Name": "..."}
    ToFull: list[dict[str, Any]]
    Subject: str
    TextBody: str | None
    HtmlBody: str | None
    Date: str
    MailboxHash: str  # For user routing
    Attachments: list[InboundEmailAttachment]
    Headers: list[dict[str, str]]
```

### DemoInjectRequest

```python
class DemoInjectRequest(BaseModel):
    eml_filename: str  # File from shared/seed/emails/
    user_id: UUID | None
```

## Outputs

### InboundResult

```python
class InboundResult(BaseModel):
    message_id: str
    classification: EmailClassification  # reward|receipt|promo|other
    rewards_extracted: int
    reward_ids: list[UUID]
    needs_review: bool
    processing_time_ms: int
```

## Implementation Tasks

### 1. Postmark Webhook Handler

```python
@app.post("/inbound")
async def process_inbound_email(email: InboundEmail) -> InboundResult:
    # 1. Parse MailboxHash to get user_id
    # 2. Check dedupe (skip if MessageID exists)
    # 3. Run Presidio redaction on TextBody and HtmlBody
    # 4. Call extraction module
    # 5. Return result
```

### 2. Presidio PII Redaction

Install: `pip install presidio-analyzer presidio-anonymizer`

Redact ONLY these PII types:
- `CREDIT_CARD` - Card numbers
- `PHONE_NUMBER` - Phone numbers  
- `EMAIL_ADDRESS` - Email addresses (except sender/recipient)
- `LOCATION` - Street addresses

**Do NOT redact**: Names, dates, amounts, promo codes

```python
from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine

analyzer = AnalyzerEngine()
anonymizer = AnonymizerEngine()

def redact_pii(text: str) -> str:
    results = analyzer.analyze(
        text=text,
        entities=["CREDIT_CARD", "PHONE_NUMBER", "EMAIL_ADDRESS", "LOCATION"],
        language="en"
    )
    return anonymizer.anonymize(text=text, analyzer_results=results).text
```

### 3. Deduplication

Store processed MessageIDs in database. Skip if already seen.

```python
async def is_duplicate(message_id: str) -> bool:
    # Check if message_id exists in processed_emails table
    pass

async def mark_processed(message_id: str, user_id: UUID):
    # Insert into processed_emails table
    pass
```

### 4. Demo Inject Endpoint

```python
@app.post("/demo/inject")
async def inject_demo_email(request: DemoInjectRequest) -> InboundResult:
    # 1. Load .eml file from shared/seed/emails/
    # 2. Parse into InboundEmail format
    # 3. Run through same pipeline as /inbound
    pass
```

### 5. Demo Merchant Console (Optional)

Simple web UI that sends test reward emails to the user's lapse.app address.

## Test Emails

Available in `shared/seed/emails/`:

| File | Type | Features |
|------|------|----------|
| `hollister_10_percent.eml` | reward | JSON-LD DiscountOffer |
| `target_jsonld_offer.eml` | reward | JSON-LD Offer |
| `chipotle_plaintext.eml` | reward | Plain text only |
| `nike_promo.eml` | promo | JSON-LD DiscountOffer |
| `amazon_receipt.eml` | receipt | Order receipt |

## Acceptance Criteria

- [ ] `/inbound` accepts Postmark webhook format
- [ ] PII is redacted (card numbers, phones, addresses)
- [ ] Duplicate emails are skipped
- [ ] `/demo/inject` replays test emails
- [ ] Result includes classification from extraction module
- [ ] Processing time is tracked

## Dependencies

```
presidio-analyzer>=2.2.0
presidio-anonymizer>=2.2.0
```

## Database Tables (coordinate with Person 3)

```sql
CREATE TABLE processed_emails (
    message_id TEXT PRIMARY KEY,
    user_id UUID NOT NULL,
    received_at TIMESTAMPTZ DEFAULT NOW()
);
```

## Notes

- **No SPF/DKIM check**: Intentionally skipped for hackathon
- **No prompt injection scan**: Intentionally skipped for hackathon
- Route to correct user via `MailboxHash` (e.g., `user123@lapse.app` → hash = `user123`)
