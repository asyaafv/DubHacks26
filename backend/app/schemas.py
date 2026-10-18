"""
PerkSense Shared Contracts - Pydantic v2 Models

These models are the SOURCE OF TRUTH for all API contracts.
When modified:
1. Run scripts/gen_contracts.py to regenerate JSON schemas and TypeScript types
2. Commit shared/schemas/*.json, shared/types.ts, and shared/openapi.json together
3. Notify all team members of contract changes

Architecture: Chrome Extension + FastAPI Backend + Postgres/pgvector
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# =============================================================================
# ENUMS
# =============================================================================


class RewardKind(str, Enum):
    """Type of reward/discount offered."""
    percent_off = "percent_off"
    amount_off = "amount_off"
    points = "points"
    free_item = "free_item"
    bogo = "bogo"  # Buy One Get One
    cashback = "cashback"


class RewardSource(str, Enum):
    """How the reward was extracted/created."""
    email_jsonld = "email_jsonld"  # schema.org JSON-LD from email
    gliner = "gliner"  # GLiNER2 NER extraction
    regex = "regex"  # Regex fallback extraction
    manual = "manual"  # User-entered
    seed = "seed"  # Demo/test seed data


class RewardStatus(str, Enum):
    """Current status of the reward."""
    active = "active"
    needs_review = "needs_review"  # Low confidence, user should verify
    used = "used"
    expired = "expired"


class CardNetwork(str, Enum):
    """Payment card network."""
    visa = "visa"
    mastercard = "mastercard"
    amex = "amex"
    discover = "discover"


class EventType(str, Enum):
    """SSE event types for real-time updates."""
    reward_added = "reward_added"
    reward_expiring = "reward_expiring"
    reward_updated = "reward_updated"
    reward_used = "reward_used"
    sync_complete = "sync_complete"


class EmailClassification(str, Enum):
    """SetFit email classifier categories."""
    reward = "reward"
    receipt = "receipt"
    promo = "promo"
    other = "other"


# =============================================================================
# MERCHANT MODELS
# =============================================================================


class MerchantBase(BaseModel):
    """Base merchant model."""
    name: str = Field(..., description="Merchant display name", examples=["Target"])
    domain: str = Field(..., description="Primary domain", examples=["target.com"])
    mcc: str = Field(..., description="Merchant Category Code (4 digits)", examples=["5311"])
    category: str = Field(..., description="Human-readable category", examples=["Department Stores"])


class Merchant(MerchantBase):
    """Full merchant record with ID."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Unique merchant ID")
    aliases: list[str] = Field(default_factory=list, description="Alternative domains/names")
    logo_url: str | None = Field(None, description="Logo URL for display")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ClassifyMerchantRequest(BaseModel):
    """Request to classify an unknown merchant."""
    domain: str = Field(..., description="Domain to classify", examples=["unknownstore.com"])
    page_title: str | None = Field(None, description="Page title for context")


class ClassifyMerchantResult(BaseModel):
    """Merchant classification result."""
    domain: str
    merchant_id: UUID | None = Field(None, description="Matched merchant ID if known")
    merchant_name: str = Field(..., description="Merchant name (inferred if unknown)")
    category: str = Field(..., description="Inferred category")
    mcc: str = Field(..., description="Inferred MCC code")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Classification confidence")
    is_new: bool = Field(..., description="True if merchant was not in database")


# =============================================================================
# REWARD MODELS
# =============================================================================


class FieldConfidence(BaseModel):
    """Per-field extraction confidence scores."""
    value: float = Field(default=1.0, ge=0.0, le=1.0)
    expires_at: float = Field(default=1.0, ge=0.0, le=1.0)
    code: float = Field(default=1.0, ge=0.0, le=1.0)
    min_spend: float = Field(default=1.0, ge=0.0, le=1.0)
    merchant: float = Field(default=1.0, ge=0.0, le=1.0)


class RewardBase(BaseModel):
    """Base reward fields (for creation)."""
    merchant_id: UUID | None = Field(None, description="Linked merchant ID")
    merchant_name: str = Field(..., description="Merchant name", examples=["Target"])
    category: str = Field(..., description="Reward category", examples=["Department Stores"])
    mcc: str = Field(..., description="Merchant Category Code", examples=["5311"])
    kind: RewardKind = Field(..., description="Type of reward")
    value: Decimal = Field(..., description="Reward value (percentage or amount)", examples=["10.00"])
    currency: str = Field(default="USD", description="Currency code")
    min_spend: Decimal | None = Field(None, description="Minimum purchase to apply", examples=["50.00"])
    max_discount: Decimal | None = Field(None, description="Maximum discount cap", examples=["25.00"])
    code: str | None = Field(None, description="Promo/reward code (encrypted at rest)")
    expires_at: datetime | None = Field(None, description="Expiration datetime")
    starts_at: datetime | None = Field(None, description="Start datetime (if future)")
    stackable: bool = Field(default=False, description="Can combine with other rewards")
    exclusions: list[str] = Field(default_factory=list, description="Excluded items/categories")


class Reward(RewardBase):
    """Full reward record."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Unique reward ID")
    user_id: UUID = Field(..., description="Owner user ID")
    source: RewardSource = Field(..., description="How this reward was extracted")
    source_email_id: str | None = Field(None, description="Source email message ID")
    field_confidence: FieldConfidence = Field(default_factory=FieldConfidence)
    overall_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    status: RewardStatus = Field(default=RewardStatus.active)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class RewardCreate(RewardBase):
    """Reward creation payload."""
    source: RewardSource = Field(default=RewardSource.manual)
    source_email_id: str | None = None
    field_confidence: FieldConfidence | None = None


# =============================================================================
# CARD & MEMBERSHIP MODELS
# =============================================================================


class CategoryRate(BaseModel):
    """Cashback rate for a specific category or MCC."""
    category: str | None = Field(None, description="Category name", examples=["Dining"])
    mcc_codes: list[str] = Field(default_factory=list, description="Matching MCC codes")
    rate: Decimal = Field(..., description="Cashback rate (percentage)", examples=["3.0"])


class CardBase(BaseModel):
    """Payment card for cashback tracking."""
    issuer: str = Field(..., description="Card issuer", examples=["Chase"])
    network: CardNetwork = Field(..., description="Card network")
    name: str = Field(..., description="Card product name", examples=["Freedom Unlimited"])
    base_rate: Decimal = Field(..., description="Base cashback rate (%)", examples=["1.5"])
    category_rates: list[CategoryRate] = Field(
        default_factory=list,
        description="Bonus category rates"
    )


class Card(CardBase):
    """Full card record."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Unique card ID")
    user_id: UUID = Field(..., description="Owner user ID")
    last_four: str | None = Field(None, description="Last 4 digits (display only)")
    is_demo: bool = Field(default=False, description="Demo card flag")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MembershipBase(BaseModel):
    """Store membership/loyalty program."""
    merchant_id: UUID | None = Field(None, description="Linked merchant ID")
    merchant_name: str = Field(..., description="Merchant name", examples=["Costco"])
    program_name: str = Field(..., description="Membership program name", examples=["Executive"])
    tier: str | None = Field(None, description="Membership tier", examples=["Gold"])
    member_id: str | None = Field(None, description="Membership number (encrypted)")
    benefits: list[str] = Field(default_factory=list, description="Membership benefits")
    annual_reward_rate: Decimal | None = Field(None, description="Annual reward rate (%)")
    expires_at: datetime | None = Field(None, description="Membership expiration")


class Membership(MembershipBase):
    """Full membership record."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Unique membership ID")
    user_id: UUID = Field(..., description="Owner user ID")
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# WALLET MODEL
# =============================================================================


class Wallet(BaseModel):
    """User's complete wallet state."""
    user_id: UUID = Field(..., description="User ID")
    cards: list[Card] = Field(default_factory=list, description="Payment cards")
    memberships: list[Membership] = Field(default_factory=list, description="Store memberships")
    active_rewards_count: int = Field(default=0, description="Number of active rewards")
    expiring_soon_count: int = Field(default=0, description="Rewards expiring in 3 days")


class WalletUpdate(BaseModel):
    """Wallet update payload."""
    add_cards: list[CardBase] = Field(default_factory=list)
    remove_card_ids: list[UUID] = Field(default_factory=list)
    add_memberships: list[MembershipBase] = Field(default_factory=list)
    remove_membership_ids: list[UUID] = Field(default_factory=list)


# =============================================================================
# STACKING ENGINE MODELS
# =============================================================================


class CartItem(BaseModel):
    """Individual cart item for stacking calculation."""
    name: str = Field(..., description="Item name")
    category: str | None = Field(None, description="Item category")
    price: Decimal = Field(..., description="Item price")
    quantity: int = Field(default=1)


class StackRequest(BaseModel):
    """Request to calculate optimal reward stacking."""
    user_id: UUID = Field(..., description="User ID")
    merchant_id: UUID | None = Field(None, description="Merchant ID if known")
    domain: str | None = Field(None, description="Merchant domain if ID unknown")
    cart_total: Decimal = Field(..., description="Total cart value", examples=["150.00"])
    items: list[CartItem] = Field(default_factory=list, description="Cart items (for exclusion matching)")


class ChosenReward(BaseModel):
    """A reward chosen by the stacking solver."""
    reward_id: UUID
    reward: Reward
    savings: Decimal = Field(..., description="Savings from this reward")
    applied_order: int = Field(..., description="Order in which to apply")


class StackResult(BaseModel):
    """Optimal stacking result from CP-SAT solver."""
    chosen_rewards: list[ChosenReward] = Field(..., description="Rewards to use, in order")
    recommended_card: Card | None = Field(None, description="Best card for this purchase")
    card_cashback: Decimal = Field(default=Decimal("0"), description="Cashback from card")
    original_price: Decimal = Field(..., description="Original cart total")
    final_price: Decimal = Field(..., description="Price after all discounts")
    total_savings: Decimal = Field(..., description="Total savings (rewards + cashback)")
    savings_percent: Decimal = Field(..., description="Savings as percentage")
    explanation: str = Field(..., description="Human-readable explanation of stacking")
    alternatives: list[ChosenReward] = Field(
        default_factory=list,
        description="Other rewards that could be used but weren't optimal"
    )
    solver_status: str = Field(default="optimal", description="CP-SAT solver status")


# =============================================================================
# LOOKUP MODELS
# =============================================================================


class LookupRequest(BaseModel):
    """Request to find relevant rewards for a merchant."""
    user_id: UUID = Field(..., description="User ID")
    merchant_id: UUID | None = Field(None)
    domain: str | None = Field(None)
    query: str | None = Field(None, description="Optional text query for semantic search")
    limit: int = Field(default=3, ge=1, le=10)


class ScoredReward(BaseModel):
    """Reward with relevance score breakdown."""
    reward: Reward
    score: float = Field(..., description="Final ranking score")
    value_component: float = Field(..., description="Score from value_usd")
    match_component: float = Field(..., description="Score from merchant/category match")
    urgency_component: float = Field(..., description="Score from expiry urgency")
    days_until_expiry: int | None = None


class LookupResult(BaseModel):
    """Top rewards for a merchant lookup."""
    merchant: Merchant | None
    rewards: list[ScoredReward] = Field(..., description="Top rewards by score")
    total_available: int = Field(..., description="Total rewards available for user")


# =============================================================================
# EMAIL INTAKE MODELS
# =============================================================================


class InboundEmailAttachment(BaseModel):
    """Email attachment metadata (Postmark-compatible)."""
    Name: str
    Content: str = Field(..., description="Base64-encoded content")
    ContentType: str
    ContentLength: int


class InboundEmail(BaseModel):
    """Postmark inbound webhook payload (subset of fields we use)."""
    MessageID: str = Field(..., description="Unique message ID")
    FromFull: dict[str, Any] = Field(..., description="Sender info with Email and Name")
    ToFull: list[dict[str, Any]] = Field(..., description="Recipients")
    Subject: str
    TextBody: str | None = None
    HtmlBody: str | None = None
    Date: str = Field(..., description="Email date string")
    MailboxHash: str = Field(default="", description="Hash for user routing")
    Attachments: list[InboundEmailAttachment] = Field(default_factory=list)
    Headers: list[dict[str, str]] = Field(default_factory=list)


class InboundResult(BaseModel):
    """Result of processing an inbound email."""
    message_id: str
    classification: EmailClassification
    rewards_extracted: int = Field(default=0)
    reward_ids: list[UUID] = Field(default_factory=list)
    needs_review: bool = Field(default=False)
    processing_time_ms: int = Field(default=0)


class DemoInjectRequest(BaseModel):
    """Request to inject a demo/test email."""
    eml_filename: str = Field(..., description="Filename from shared/seed/emails/")
    user_id: UUID | None = Field(None, description="Override user ID")


# =============================================================================
# SYNC & SSE MODELS
# =============================================================================


class Event(BaseModel):
    """SSE event payload."""
    event_type: EventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: UUID
    reward_id: UUID | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class SyncResponse(BaseModel):
    """Polling sync response."""
    user_id: UUID
    rewards: list[Reward] = Field(default_factory=list)
    wallet: Wallet
    last_sync: datetime = Field(default_factory=datetime.utcnow)
    pending_events: list[Event] = Field(default_factory=list)


# =============================================================================
# ERROR MODELS
# =============================================================================


class ErrorDetail(BaseModel):
    """Standardized error response."""
    error: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable message")
    details: dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# HEALTH CHECK
# =============================================================================


class HealthCheck(BaseModel):
    """Health check response."""
    status: str = Field(default="healthy")
    version: str = Field(default="0.1.0")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    services: dict[str, str] = Field(
        default_factory=lambda: {
            "database": "stub",
            "email_intake": "stub",
            "extraction": "stub",
            "stacking": "stub"
        }
    )
