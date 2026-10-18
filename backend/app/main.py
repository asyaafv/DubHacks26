"""
Lapse API - Stub Implementation

This is a STUB implementation that returns seed data for frontend integration.
Backend developers should replace stub logic with real implementations.

Auth: Uses X-User-Id header (hackathon simplification - no real auth)
CORS: Configured for chrome-extension:// origins
"""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import AsyncGenerator
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from .schemas import (
    Card,
    CardBase,
    CategoryRate,
    ChosenReward,
    ClassifyMerchantRequest,
    ClassifyMerchantResult,
    DemoInjectRequest,
    EmailClassification,
    ErrorDetail,
    Event,
    EventType,
    FieldConfidence,
    HealthCheck,
    InboundEmail,
    InboundResult,
    LookupRequest,
    LookupResult,
    Membership,
    MembershipBase,
    Merchant,
    Reward,
    RewardKind,
    RewardSource,
    RewardStatus,
    ScoredReward,
    StackRequest,
    StackResult,
    SyncResponse,
    Wallet,
    WalletUpdate,
)

from backend.decisions.storage import Database
from backend.decisions.common import resolve_user
from backend.decisions.wallet.router import router as wallet_router
from backend.decisions.wallet.service import wallet_snapshot
from backend.decisions.savings import router as savings_router
from backend.decisions.search import router as search_router
from backend.decisions.stacking import solve_stack
from backend.decisions.stacking.engine import _resolve_merchant
from backend.decisions.use_first import apply_use_first, stack_exclusions

from backend.intake.service import (
    DemoInjectWithForce,
    IntakeInboundResult,
    coerce_inbound_email,
    drain_events as drain_intake_events,
    process_inbound,
)

# Demo merchant console (Agent D) may not have merged yet; mount if importable.
try:
    from backend.intake.console.router import router as demo_console_router
except ImportError:
    demo_console_router = None


@asynccontextmanager
async def lifespan(app):
    app.state.database = None
    if os.getenv("DATABASE_URL"):
        app.state.database = await Database.connect()
    try:
        yield
    finally:
        if app.state.database is not None:
            await app.state.database.close()


# =============================================================================
# APP SETUP
# =============================================================================

app = FastAPI(
    lifespan=lifespan,
    title="Lapse API",
    description="Find and stack store rewards, card cashback, and memberships",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS for the Chrome extension and local dashboards. Starlette matches
# allow_origins entries literally (no "*" globbing), so ports/extension ids
# must be covered by allow_origin_regex instead.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[],
    allow_origin_regex=r"chrome-extension://.*|https?://(localhost|127\.0\.0\.1)(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# SEED DATA LOADING
# =============================================================================

SEED_DIR = Path(__file__).parent.parent.parent / "shared" / "seed"
DEMO_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def load_seed_json(filename: str) -> dict:
    """Load a seed JSON file."""
    path = SEED_DIR / filename
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def get_seed_merchants() -> list[Merchant]:
    """Load seed merchants."""
    data = load_seed_json("seed_merchants.json")
    merchants = []
    for m in data.get("merchants", []):
        merchants.append(
            Merchant(
                id=UUID(m["id"]),
                name=m["name"],
                domain=m["domain"],
                mcc=m["mcc"],
                category=m["category"],
                aliases=m.get("aliases", []),
                logo_url=m.get("logo_url"),
                created_at=datetime.fromisoformat(m["created_at"]) if "created_at" in m else datetime.now(timezone.utc),
            )
        )
    return merchants


def get_seed_rewards() -> list[Reward]:
    """Load seed rewards."""
    data = load_seed_json("seed_rewards.json")
    rewards = []
    for r in data.get("rewards", []):
        fc = r.get("field_confidence", {})
        rewards.append(
            Reward(
                id=UUID(r["id"]),
                user_id=UUID(r["user_id"]),
                merchant_id=UUID(r["merchant_id"]) if r.get("merchant_id") else None,
                merchant_name=r["merchant_name"],
                category=r["category"],
                mcc=r["mcc"],
                kind=RewardKind(r["kind"]),
                value=Decimal(r["value"]),
                currency=r.get("currency", "USD"),
                min_spend=Decimal(r["min_spend"]) if r.get("min_spend") else None,
                max_discount=Decimal(r["max_discount"]) if r.get("max_discount") else None,
                code=r.get("code"),
                expires_at=datetime.fromisoformat(r["expires_at"].replace("Z", "+00:00")) if r.get("expires_at") else None,
                starts_at=datetime.fromisoformat(r["starts_at"].replace("Z", "+00:00")) if r.get("starts_at") else None,
                stackable=r.get("stackable", False),
                exclusions=r.get("exclusions", []),
                source=RewardSource(r["source"]),
                source_email_id=r.get("source_email_id"),
                field_confidence=FieldConfidence(
                    value=fc.get("value", 1.0),
                    expires_at=fc.get("expires_at", 1.0),
                    code=fc.get("code", 1.0),
                    min_spend=fc.get("min_spend", 1.0),
                    merchant=fc.get("merchant", 1.0),
                ),
                overall_confidence=r.get("overall_confidence", 1.0),
                status=RewardStatus(r["status"]),
                created_at=datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")),
                updated_at=datetime.fromisoformat(r.get("updated_at", r["created_at"]).replace("Z", "+00:00")),
            )
        )
    return rewards


def get_seed_cards() -> list[Card]:
    """Load seed cards."""
    data = load_seed_json("seed_cards.json")
    cards = []
    for c in data.get("cards", []):
        category_rates = []
        for cr in c.get("category_rates", []):
            category_rates.append(
                CategoryRate(
                    category=cr.get("category"),
                    mcc_codes=cr.get("mcc_codes", []),
                    rate=Decimal(cr["rate"]),
                )
            )
        cards.append(
            Card(
                id=UUID(c["id"]),
                user_id=UUID(c["user_id"]),
                issuer=c["issuer"],
                network=c["network"],
                name=c["name"],
                last_four=c.get("last_four"),
                base_rate=Decimal(c["base_rate"]),
                category_rates=category_rates,
                is_demo=c.get("is_demo", False),
                created_at=datetime.fromisoformat(c["created_at"].replace("Z", "+00:00")),
            )
        )
    return cards


def get_seed_memberships() -> list[Membership]:
    """Load seed memberships."""
    data = load_seed_json("seed_memberships.json")
    memberships = []
    for m in data.get("memberships", []):
        memberships.append(
            Membership(
                id=UUID(m["id"]),
                user_id=UUID(m["user_id"]),
                merchant_id=UUID(m["merchant_id"]) if m.get("merchant_id") else None,
                merchant_name=m["merchant_name"],
                program_name=m["program_name"],
                tier=m.get("tier"),
                member_id=m.get("member_id"),
                benefits=m.get("benefits", []),
                annual_reward_rate=Decimal(m["annual_reward_rate"]) if m.get("annual_reward_rate") else None,
                expires_at=datetime.fromisoformat(m["expires_at"].replace("Z", "+00:00")) if m.get("expires_at") else None,
                is_active=m.get("is_active", True),
                created_at=datetime.fromisoformat(m["created_at"].replace("Z", "+00:00")),
            )
        )
    return memberships


# Cache loaded data
_merchants: list[Merchant] | None = None
_rewards: list[Reward] | None = None
_cards: list[Card] | None = None
_memberships: list[Membership] | None = None


def get_merchants() -> list[Merchant]:
    global _merchants
    if _merchants is None:
        _merchants = get_seed_merchants()
    return _merchants


def get_rewards() -> list[Reward]:
    global _rewards
    if _rewards is None:
        _rewards = get_seed_rewards()
    return _rewards


def get_cards() -> list[Card]:
    global _cards
    if _cards is None:
        _cards = get_seed_cards()
    return _cards


def get_memberships() -> list[Membership]:
    global _memberships
    if _memberships is None:
        _memberships = get_seed_memberships()
    return _memberships


def get_user_id(x_user_id: str | None) -> UUID:
    """Parse user ID from header, default to demo user."""
    if not x_user_id:
        return DEMO_USER_ID
    try:
        return UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid X-User-Id format")


# =============================================================================
# HEALTH CHECK
# =============================================================================


@app.get("/health", response_model=HealthCheck, tags=["System"])
async def health_check() -> HealthCheck:
    """Health check endpoint."""
    return HealthCheck(
        status="healthy",
        version="0.1.0",
        timestamp=datetime.now(timezone.utc),
        services={
            "database": "stub",
            "email_intake": "stub",
            "extraction": "stub",
            "stacking": "stub",
        },
    )


# =============================================================================
# INBOUND EMAIL ENDPOINTS (Person 1: Intake)
# =============================================================================


@app.post("/inbound", response_model=IntakeInboundResult, tags=["Intake"])
async def process_inbound_email(
    request: Request,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> IntakeInboundResult:
    """
    Process inbound email from Postmark webhook.

    Accepts the raw Postmark inbound JSON (extra/missing fields tolerated) and
    runs the intake flow: routing -> dedupe -> redaction -> extraction ->
    persist -> reward_added events.

    Always returns 200 for a parseable JSON object so Postmark never retries
    forever; an unroutable recipient yields rewards_extracted=0 with
    note="unknown_recipient". Only a non-JSON body gets a 400.
    """
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 - body was not JSON at all
        raise HTTPException(status_code=400, detail="Request body must be JSON")
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Request body must be a JSON object")

    email = coerce_inbound_email(payload)
    # Explicit header overrides routing; otherwise the service resolves the
    # user from MailboxHash / recipient address.
    user_id = get_user_id(x_user_id) if x_user_id else None
    return process_inbound(email, user_id, source="postmark")


@app.post("/demo/inject", response_model=IntakeInboundResult, tags=["Intake"])
async def inject_demo_email(
    request: DemoInjectWithForce,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> IntakeInboundResult:
    """
    Replay a stored .eml file through the intake flow.

    Pass `"force": true` to bypass the dedupe check so demos can replay the
    same email repeatedly.
    """
    from backend.extraction.pipeline import parse_eml

    user_id = request.user_id or get_user_id(x_user_id)

    eml_path = SEED_DIR / "emails" / request.eml_filename
    if not eml_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Email file not found: {request.eml_filename}",
        )

    email = parse_eml(eml_path.read_bytes())
    return process_inbound(email, user_id, source="demo", force=request.force)


@app.get("/demo/emails", tags=["Intake"])
async def list_demo_emails() -> dict:
    """List the seed .eml files available for /demo/inject."""
    emails_dir = SEED_DIR / "emails"
    files = sorted(p.name for p in emails_dir.glob("*.eml")) if emails_dir.exists() else []
    return {"emails": files}


if demo_console_router is not None:
    app.include_router(demo_console_router, prefix="/demo/console", tags=["Demo Console"])


# =============================================================================
# WALLET ENDPOINTS (Person 3: Decisions)
# =============================================================================


app.include_router(wallet_router)
app.include_router(savings_router)
app.include_router(search_router)


async def get_wallet(x_user_id=None):
    """Compatibility bridge for the existing sync stub until integration wiring."""
    return await wallet_snapshot(app, resolve_user(x_user_id))


# =============================================================================
# STACKING ENGINE ENDPOINTS (Person 3: Decisions)
# =============================================================================


@app.post("/stack", response_model=StackResult, tags=["Stacking"])
async def calculate_stack(
    request: StackRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> StackResult:
    """
    Calculate optimal reward stacking for a purchase.

    CP-SAT solver (backend/decisions/stacking/) with max-one-promo-code,
    min-spend, exclusions and non-combinable constraints, best card via
    card_rate, and a greedy fallback if the solver fails within 200 ms.
    """
    user_id = get_user_id(x_user_id)
    rewards = get_rewards()

    # "Use it before you lose it": withhold longer-lived same-merchant rewards
    # that can't combine with one expiring this week, so the solver spends the
    # expiring one now. prefer_expiring=False restores the old behavior.
    exclusion_note = None
    if request.prefer_expiring:
        merchant = _resolve_merchant(request, get_merchants())
        merchant_id = request.merchant_id or (merchant.id if merchant else None)
        excluded_ids, exclusion_note = stack_exclusions(
            [r for r in rewards if r.user_id == user_id],
            merchant_id,
            datetime.now(timezone.utc),
        )
        if excluded_ids:
            rewards = [r for r in rewards if r.id not in excluded_ids]

    result = solve_stack(
        request,
        user_id=user_id,
        rewards=rewards,
        cards=get_cards(),
        merchants=get_merchants(),
    )
    if exclusion_note:
        result.explanations.append(exclusion_note)
        result.explanation = f"{result.explanation} {exclusion_note}"
    return result


# =============================================================================
# LOOKUP ENDPOINTS (Person 3: Decisions)
# =============================================================================


@app.post("/lookup", response_model=LookupResult, tags=["Lookup"])
async def lookup_rewards(
    request: LookupRequest,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> LookupResult:
    """
    Find top relevant rewards for a merchant.

    Ranking formula: score = value_usd * match * (1 + exp(-days_left/3))

    STUB: Returns top rewards by simple scoring.
    REAL: Uses pgvector for semantic search if query provided.
    """
    import math

    user_id = get_user_id(x_user_id)
    now = datetime.now(timezone.utc)

    # Find merchant
    merchant = None
    if request.merchant_id:
        merchant = next((m for m in get_merchants() if m.id == request.merchant_id), None)
    elif request.domain:
        merchant = next((m for m in get_merchants() if request.domain in m.aliases or m.domain == request.domain), None)

    # Get user's active rewards. A resolved merchant scopes the lookup
    # server-side so every direct reward survives any limit — low-scoring
    # direct rewards (e.g. Starbucks BOGO/points) must never be crowded out
    # of the page by higher-value rewards from other merchants.
    rewards = [r for r in get_rewards() if r.user_id == user_id and r.status == RewardStatus.active]
    if merchant is not None:
        rewards = [r for r in rewards if r.merchant_id == merchant.id]

    # Score rewards
    scored: list[ScoredReward] = []
    for reward in rewards:
        # Value component (normalize to 0-1 range, assume max value ~100)
        if reward.kind == RewardKind.percent_off:
            value_usd = float(reward.value)  # Treat as percentage
        elif reward.kind in (RewardKind.amount_off, RewardKind.cashback):
            value_usd = float(reward.value)
        else:
            value_usd = 5.0  # Default for free items, BOGO, points

        value_component = min(value_usd / 50.0, 1.0)

        # Match component
        match_component = 0.5  # Default partial match
        if merchant and reward.merchant_id == merchant.id:
            match_component = 1.0
        elif merchant and reward.category == merchant.category:
            match_component = 0.7

        # Urgency component
        days_until_expiry = None
        urgency_component = 1.0
        if reward.expires_at:
            exp = reward.expires_at.replace(tzinfo=timezone.utc) if reward.expires_at.tzinfo is None else reward.expires_at
            delta = exp - now
            days_until_expiry = max(0, delta.days)
            urgency_component = 1 + math.exp(-days_until_expiry / 3.0)

        score = value_component * match_component * urgency_component

        scored.append(
            ScoredReward(
                reward=reward,
                score=score,
                value_component=value_component,
                match_component=match_component,
                urgency_component=urgency_component,
                days_until_expiry=days_until_expiry,
            )
        )

    # Sort by score descending
    scored.sort(key=lambda x: x.score, reverse=True)

    # "Use it before you lose it": within a resolved merchant, surface an
    # expiring reward ahead of longer-lived ones it can't combine with.
    if merchant is not None:
        scored = apply_use_first(scored, now)

    return LookupResult(
        merchant=merchant,
        rewards=scored[: request.limit],
        total_available=len(rewards),
    )


# =============================================================================
# SYNC & SSE ENDPOINTS (Person 3: Decisions)
# =============================================================================


@app.get("/sync", response_model=SyncResponse, tags=["Sync"])
async def sync_rewards(
    x_user_id: str | None = Header(None, alias="X-User-Id"),
    since: datetime | None = Query(None, description="Return changes since this timestamp"),
) -> SyncResponse:
    """
    Polling endpoint for reward sync.

    STUB: Returns the full reward snapshot (all statuses, per CONTRACTS.md —
    clients filter used/expired locally and need needs_review for the review UI).
    REAL: Returns only rewards changed since `since` timestamp.
    """
    user_id = get_user_id(x_user_id)

    rewards = [r for r in get_rewards() if r.user_id == user_id]
    wallet = await get_wallet(x_user_id)

    return SyncResponse(
        user_id=user_id,
        rewards=rewards,
        wallet=wallet,
        last_sync=datetime.now(timezone.utc),
        pending_events=[],
    )


# Per-user SSE fan-out. The intake queue is single-consumer (drain pops), so
# with both the extension and the dashboard connected only one of them would
# get each event. Instead, whichever connection drains an event broadcasts it
# to every open connection for that user (including itself).
_sse_subscribers: dict[UUID, list[asyncio.Queue]] = {}


def broadcast_event(event: Event) -> None:
    """Deliver an event to every open /events connection for its user."""
    for queue in _sse_subscribers.get(event.user_id, []):
        queue.put_nowait(event)


async def event_generator(user_id: UUID) -> AsyncGenerator[str, None]:
    """Generate SSE events for a user."""
    # Send initial connection event
    event = Event(
        event_type=EventType.sync_complete,
        user_id=user_id,
        data={"message": "Connected to event stream"},
    )
    yield f"event: {event.event_type.value}\ndata: {event.model_dump_json()}\n\n"

    queue: asyncio.Queue = asyncio.Queue()
    _sse_subscribers.setdefault(user_id, []).append(queue)

    # Deliver events queued by intake and redemptions (1s poll, fanned out to
    # all connections), plus the original stub reward_expiring event every 30s.
    ticks = 0
    try:
        while True:
            await asyncio.sleep(1)
            ticks += 1
            for event in drain_intake_events(user_id):
                broadcast_event(event)
            while not queue.empty():
                event = queue.get_nowait()
                yield f"event: {event.event_type.value}\ndata: {event.model_dump_json()}\n\n"
            if ticks % 30 == 0:
                event = Event(
                    event_type=EventType.reward_expiring,
                    user_id=user_id,
                    data={"message": "Stub event - rewards expiring soon"},
                )
                yield f"event: {event.event_type.value}\ndata: {event.model_dump_json()}\n\n"
    finally:
        subscribers = _sse_subscribers.get(user_id, [])
        if queue in subscribers:
            subscribers.remove(queue)
        if not subscribers:
            _sse_subscribers.pop(user_id, None)


@app.get("/events", tags=["Sync"])
async def sse_events(
    request: Request,
    x_user_id: str | None = Header(None, alias="X-User-Id"),
) -> StreamingResponse:
    """
    Server-Sent Events endpoint for real-time updates.

    Events:
    - reward_added: New reward extracted from email
    - reward_expiring: Reward expiring within 24 hours
    - reward_updated: Reward status or details changed
    - reward_used: Reward marked as used
    - sync_complete: Initial sync completed

    STUB: Sends periodic test events.
    REAL: Publishes events when rewards change.
    """
    user_id = get_user_id(x_user_id)

    return StreamingResponse(
        event_generator(user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# =============================================================================
# MERCHANT CLASSIFICATION (Person 2: Extraction)
# =============================================================================


@app.post("/classify-merchant", response_model=ClassifyMerchantResult, tags=["Extraction"])
async def classify_merchant(
    request: ClassifyMerchantRequest,
) -> ClassifyMerchantResult:
    """
    Classify an unknown merchant by domain.

    STUB: Returns match from seed merchants or generic classification.
    REAL: Embeds domain/title, searches pgvector, falls back to LLM classification.
    """
    domain = request.domain.lower().replace("www.", "")

    # Search seed merchants
    for merchant in get_merchants():
        if domain == merchant.domain or domain in merchant.aliases:
            return ClassifyMerchantResult(
                domain=request.domain,
                merchant_id=merchant.id,
                merchant_name=merchant.name,
                category=merchant.category,
                mcc=merchant.mcc,
                confidence=0.95,
                is_new=False,
            )

    # Unknown merchant - return generic classification
    return ClassifyMerchantResult(
        domain=request.domain,
        merchant_id=None,
        merchant_name=request.page_title or domain.split(".")[0].title(),
        category="Miscellaneous Retail",
        mcc="5999",
        confidence=0.3,
        is_new=True,
    )


# =============================================================================
# ERROR HANDLERS
# =============================================================================


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Standardized error response."""
    from fastapi.responses import JSONResponse

    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorDetail(
            error=f"HTTP_{exc.status_code}",
            message=str(exc.detail),
            details={},
        ).model_dump(),
    )


# =============================================================================
# STARTUP
# =============================================================================


@app.on_event("startup")
async def startup():
    """Pre-load seed data on startup."""
    get_merchants()
    get_rewards()
    get_cards()
    get_memberships()
    print(f"Lapse API started. Loaded {len(get_merchants())} merchants, {len(get_rewards())} rewards.")
