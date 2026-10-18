# Extraction Module (Person 2)

Email classification and reward extraction: SetFit → JSON-LD → GLiNER2 → parsers → regex.

## Ownership

- Email classification (SetFit)
- JSON-LD extraction (extruct/schema.org)
- NER extraction (GLiNER2)
- Date/price parsing
- Regex fallback
- Embeddings generation (MiniLM)
- `POST /classify-merchant`

## Extraction Cascade

```
Email (HtmlBody + TextBody)
           ↓
    SetFit Classifier ──→ reward | receipt | promo | other
           ↓ (if reward/promo)
    JSON-LD Extraction ──→ schema.org DiscountOffer/Offer/PromotionCard
           ↓ (if not found)
    GLiNER2 NER ──→ Extract: merchant, code, value, date, min_spend
           ↓ (fill gaps)
    dateparser + price-parser ──→ Normalize dates and amounts
           ↓ (final fallback)
    Regex Patterns ──→ Common coupon code patterns
           ↓
    Confidence Scoring ──→ Overall + per-field confidence
           ↓
    Create Reward(s) ──→ status = needs_review if confidence < 0.7
```

## Inputs

Receives redacted email content from Intake module:
- `HtmlBody`: HTML content (may contain JSON-LD in `<script>` tags)
- `TextBody`: Plain text content
- `Date`: Email date (for RELATIVE_BASE in date parsing)
- `Subject`: Email subject line

## Outputs

### Reward (created for each extracted offer)

```python
class Reward(BaseModel):
    id: UUID
    user_id: UUID
    merchant_id: UUID | None
    merchant_name: str
    category: str
    mcc: str
    kind: RewardKind  # percent_off | amount_off | points | free_item | bogo | cashback
    value: Decimal
    currency: str = "USD"
    min_spend: Decimal | None
    max_discount: Decimal | None
    code: str | None  # Encrypted at rest
    expires_at: datetime | None
    starts_at: datetime | None
    stackable: bool = False
    exclusions: list[str]
    source: RewardSource  # email_jsonld | gliner | regex
    source_email_id: str
    field_confidence: FieldConfidence
    overall_confidence: float
    status: RewardStatus  # active | needs_review
```

### FieldConfidence

```python
class FieldConfidence(BaseModel):
    value: float  # 0.0 - 1.0
    expires_at: float
    code: float
    min_spend: float
    merchant: float
```

## Implementation Tasks

### 1. SetFit Email Classifier

Train on ~100 labeled emails per category.

```python
from setfit import SetFitModel

# Load pre-trained or fine-tuned model
model = SetFitModel.from_pretrained("sentence-transformers/paraphrase-MiniLM-L6-v2")

def classify_email(subject: str, body: str) -> EmailClassification:
    text = f"{subject}\n\n{body[:1000]}"  # Truncate for efficiency
    prediction = model.predict([text])[0]
    return EmailClassification(prediction)
```

### 2. JSON-LD Extraction (schema.org)

```python
import extruct
from w3lib.html import get_base_url

def extract_jsonld(html: str, url: str = "") -> list[dict]:
    base_url = get_base_url(html, url)
    data = extruct.extract(html, base_url=base_url, syntaxes=['json-ld'])
    
    offers = []
    for item in data.get('json-ld', []):
        if item.get('@type') in ['DiscountOffer', 'Offer', 'PromotionCard']:
            offers.append(item)
    return offers

def jsonld_to_reward(jsonld: dict, email_date: datetime) -> Reward:
    """Convert schema.org JSON-LD to Reward model."""
    # Map fields:
    # - discountCode → code
    # - discount / price → value
    # - discountType → kind
    # - validThrough → expires_at
    # - eligibleTransactionVolume.minPrice → min_spend
    # - seller.name → merchant_name
    pass
```

### 3. GLiNER2 NER Extraction

```python
from gliner import GLiNER

model = GLiNER.from_pretrained("urchade/gliner_large-v2.1")

LABELS = [
    "merchant_name",
    "promo_code", 
    "discount_percent",
    "discount_amount",
    "expiration_date",
    "minimum_spend",
    "excluded_items"
]

def extract_entities(text: str) -> dict[str, list]:
    entities = model.predict_entities(text, LABELS)
    
    result = {label: [] for label in LABELS}
    for entity in entities:
        result[entity["label"]].append({
            "text": entity["text"],
            "score": entity["score"]
        })
    return result
```

### 4. Date Parsing

```python
import dateparser

def parse_date(text: str, email_date: datetime) -> datetime | None:
    """Parse date with RELATIVE_BASE set to email date."""
    settings = {
        'RELATIVE_BASE': email_date,
        'PREFER_DATES_FROM': 'future'
    }
    return dateparser.parse(text, settings=settings)
```

### 5. Price Parsing

```python
from price_parser import Price

def parse_price(text: str) -> tuple[Decimal, str] | None:
    """Extract price and currency from text."""
    price = Price.fromstring(text)
    if price.amount:
        return (Decimal(str(price.amount)), price.currency or "USD")
    return None
```

### 6. Regex Fallback Patterns

```python
import re

PATTERNS = {
    'code': [
        r'(?:code|promo|coupon)[:\s]+([A-Z0-9]{4,20})',
        r'use\s+([A-Z0-9]{4,20})\s+at\s+checkout',
    ],
    'percent': [
        r'(\d+)%\s*off',
        r'save\s+(\d+)%',
    ],
    'amount': [
        r'\$(\d+(?:\.\d{2})?)\s*off',
        r'save\s+\$(\d+(?:\.\d{2})?)',
    ],
    'min_spend': [
        r'(?:min|minimum)[:\s]*\$(\d+)',
        r'spend\s+\$(\d+)\s+(?:or\s+more)?',
    ],
}
```

### 7. Embeddings Generation

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')  # 384-dim

def generate_embedding(text: str) -> list[float]:
    """Generate 384-dim embedding for pgvector storage."""
    return model.encode(text).tolist()
```

### 8. Merchant Classification Endpoint

```python
@app.post("/classify-merchant")
async def classify_merchant(request: ClassifyMerchantRequest) -> ClassifyMerchantResult:
    # 1. Check seed merchants by domain
    # 2. If not found, use embedding similarity search (pgvector)
    # 3. If still no match, infer category from page_title or domain
    # 4. Return with confidence score
    pass
```

## Confidence Scoring

```python
def calculate_confidence(
    source: RewardSource,
    field_values: dict,
    field_confidences: dict
) -> tuple[FieldConfidence, float]:
    """
    Calculate per-field and overall confidence.
    
    Source weights:
    - email_jsonld: 1.0 (structured data)
    - gliner: 0.85 (NER extraction)
    - regex: 0.6 (pattern matching)
    """
    source_weight = {
        RewardSource.email_jsonld: 1.0,
        RewardSource.gliner: 0.85,
        RewardSource.regex: 0.6,
    }.get(source, 0.5)
    
    # Combine NER confidence with source weight
    field_conf = FieldConfidence(
        value=field_confidences.get('value', 1.0) * source_weight,
        expires_at=field_confidences.get('expires_at', 1.0) * source_weight,
        code=field_confidences.get('code', 1.0) * source_weight,
        min_spend=field_confidences.get('min_spend', 1.0) * source_weight,
        merchant=field_confidences.get('merchant', 1.0) * source_weight,
    )
    
    # Overall = weighted average
    overall = (
        field_conf.value * 0.3 +
        field_conf.expires_at * 0.2 +
        field_conf.code * 0.2 +
        field_conf.merchant * 0.3
    )
    
    return field_conf, overall
```

## Status Assignment

```python
def determine_status(overall_confidence: float) -> RewardStatus:
    if overall_confidence >= 0.7:
        return RewardStatus.active
    else:
        return RewardStatus.needs_review
```

## Acceptance Criteria

- [ ] SetFit classifies emails into 4 categories
- [ ] JSON-LD extraction handles DiscountOffer, Offer, PromotionCard
- [ ] GLiNER2 extracts merchant, code, value, date, min_spend
- [ ] Dates parsed relative to email date
- [ ] Prices parsed with currency
- [ ] Regex fallback catches common patterns
- [ ] Per-field confidence scores calculated
- [ ] Low confidence rewards marked `needs_review`
- [ ] `/classify-merchant` works for known and unknown domains

## Dependencies

```
setfit>=1.0.0
gliner>=0.2.0
sentence-transformers>=2.3.0
extruct>=0.16.0
dateparser>=1.2.0
price-parser>=0.3.0
```

## Notes

- **RELATIVE_BASE**: Always set to email's `Date` header for date parsing
- **Stackability**: Default to `stackable=False` unless explicitly stated
- **Embedding model**: `all-MiniLM-L6-v2` produces 384-dimensional vectors
