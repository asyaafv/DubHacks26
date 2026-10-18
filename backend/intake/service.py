"""Intake service (Agent C: integrator).

process_inbound(email, user_id=None, *, source="postmark") runs the full
intake flow:

    resolve user (routing) -> dedupe check -> PII redaction
        -> backend.extraction.pipeline.run_pipeline -> persist rewards
        -> mark_processed -> emit reward_added events -> InboundResult

The sibling intake modules (routing, dedupe, redact, console) are being
written IN PARALLEL by other agents, so every import here is defensive: if a
real module is missing we use a minimal built-in implementation (clearly
marked FALLBACK). When the real modules land on main they take over
automatically with no edits here. INTAKE_FALLBACKS lists the stages that are
currently running on fallbacks.

Error-handling decisions (documented per the shared brief):

- Unknown recipient: process_inbound returns HTTP-200-style
  IntakeInboundResult(rewards_extracted=0, note="unknown_recipient") instead
  of raising HTTP 404. Postmark retries non-2xx webhook responses forever, so
  a mis-addressed email must still be acknowledged with 200.
- Duplicate email: returns IntakeInboundResult(rewards_extracted=0,
  duplicate=True, note="duplicate") WITHOUT re-running extraction.
  `force=True` (demo replays) bypasses the dedupe check.
- Extraction crash: returns rewards_extracted=0 with note="extraction_error"
  (again a 200 so Postmark does not retry a deterministically-failing email).
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import Counter, defaultdict, deque
from typing import Deque, Iterable
from uuid import UUID, uuid4

from backend.app.schemas import (
    DemoInjectRequest,
    EmailClassification,
    Event,
    EventType,
    InboundEmail,
    InboundResult,
    Reward,
    RewardStatus,
)

logger = logging.getLogger("lapse.intake.service")

DEMO_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

# Stages currently served by built-in fallbacks (real module missing/broken).
INTAKE_FALLBACKS: list[str] = []


# =============================================================================
# Public request/response models (schemas.py is frozen, so we extend here)
# =============================================================================


class IntakeInboundResult(InboundResult):
    """InboundResult plus intake-only metadata (superset stays contract-valid)."""

    duplicate: bool = False
    note: str | None = None


class DemoInjectWithForce(DemoInjectRequest):
    """DemoInjectRequest plus `force` to bypass dedupe for demo replays."""

    force: bool = False


# =============================================================================
# FALLBACK: routing.py  (resolve_user + inbox_address_for)
# =============================================================================

_HASH_TO_USER: dict[str, UUID] = {
    "aamir": DEMO_USER_ID,
    "demo": DEMO_USER_ID,
}


def _routing_candidates(email: InboundEmail) -> Iterable[str]:
    if email.MailboxHash:
        yield email.MailboxHash
    for recipient in email.ToFull or []:
        if not isinstance(recipient, dict):
            continue
        address = str(recipient.get("Email") or "")
        if "@" not in address:
            continue
        local = address.split("@", 1)[0]
        yield local
        if "+" in local:
            base, _, plus_hash = local.partition("+")
            yield base
            yield plus_hash


def _fallback_resolve_user(email: InboundEmail) -> UUID | None:
    """FALLBACK for routing.resolve_user.

    MailboxHash first, then To local-part, then the `+hash` piece of Postmark
    default inbound addresses. `aamir` and `demo` map to the demo user;
    UUID-shaped hashes map to that user directly.
    """
    for candidate in _routing_candidates(email):
        key = candidate.strip().lower()
        if not key:
            continue
        if key in _HASH_TO_USER:
            return _HASH_TO_USER[key]
        try:
            return UUID(key)
        except ValueError:
            continue
    return None


def _fallback_inbox_address_for(user_id: UUID) -> str:
    """FALLBACK for routing.inbox_address_for."""
    if user_id == DEMO_USER_ID:
        return "aamir@lapse.app"
    return f"{user_id}@lapse.app"


try:
    from backend.intake.routing import resolve_user
except ImportError:
    resolve_user = _fallback_resolve_user
    INTAKE_FALLBACKS.append("routing")

try:
    from backend.intake.routing import inbox_address_for
except ImportError:
    inbox_address_for = _fallback_inbox_address_for
    if "routing" not in INTAKE_FALLBACKS:
        INTAKE_FALLBACKS.append("routing")


# =============================================================================
# FALLBACK: dedupe.py  (seen_before + mark_processed)
# =============================================================================

_dedupe_lock = threading.Lock()
_seen_messages: set[tuple[str, str]] = set()


def _fallback_seen_before(email: InboundEmail, user_id: UUID) -> bool:
    """FALLBACK for dedupe.seen_before (MessageID-only, in-memory)."""
    with _dedupe_lock:
        return (str(user_id), email.MessageID) in _seen_messages


def _fallback_mark_processed(email: InboundEmail, user_id: UUID) -> None:
    """FALLBACK for dedupe.mark_processed (MessageID-only, in-memory)."""
    with _dedupe_lock:
        _seen_messages.add((str(user_id), email.MessageID))


try:
    from backend.intake.dedupe import mark_processed, seen_before
except ImportError:
    seen_before = _fallback_seen_before
    mark_processed = _fallback_mark_processed
    INTAKE_FALLBACKS.append("dedupe")


# =============================================================================
# FALLBACK: redact.py  (redact_email)
# =============================================================================

# Card numbers: 4 groups of digits (13-19 total) with optional space/dash.
_CARD_RE = re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{1,7}\b")
# US-style phone numbers; requires separators so dates/amounts never match.
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[\s.\-])?\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}(?!\d)"
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_SCRIPT_SPLIT_RE = re.compile(r"(?is)(<script[^>]*>.*?</script>)")
_TAG_SPLIT_RE = re.compile(r"(<[^>]*>)")


def _fallback_redact_text(
    text: str | None, keep: frozenset[str] | set[str] = frozenset()
) -> tuple[str | None, dict[str, int]]:
    """FALLBACK for redact.redact_text (simple regex; no Presidio).

    Redacts card numbers, phone numbers and email addresses (except those in
    `keep`). Never touches names, dates, amounts, promo codes, store names.
    """
    counts: Counter[str] = Counter()
    if not text:
        return text, dict(counts)

    def _card(match: re.Match) -> str:
        counts["CREDIT_CARD"] += 1
        return "[REDACTED_CARD]"

    def _phone(match: re.Match) -> str:
        counts["PHONE_NUMBER"] += 1
        return "[REDACTED_PHONE]"

    def _email(match: re.Match) -> str:
        if match.group(0).lower() in keep:
            return match.group(0)
        counts["EMAIL_ADDRESS"] += 1
        return "[REDACTED_EMAIL]"

    text = _CARD_RE.sub(_card, text)
    text = _PHONE_RE.sub(_phone, text)
    text = _EMAIL_RE.sub(_email, text)
    return text, dict(counts)


def _fallback_redact_html(
    html: str | None, keep: frozenset[str] | set[str]
) -> tuple[str | None, dict[str, int]]:
    """Redact text nodes only; never touch tags or <script> (JSON-LD) blocks."""
    counts: Counter[str] = Counter()
    if not html:
        return html, dict(counts)
    chunks: list[str] = []
    for part in _SCRIPT_SPLIT_RE.split(html):
        if part.lower().startswith("<script"):
            chunks.append(part)
            continue
        tokens = _TAG_SPLIT_RE.split(part)
        for i, token in enumerate(tokens):
            if token.startswith("<"):
                continue
            tokens[i], token_counts = _fallback_redact_text(token, keep)
            counts.update(token_counts)
        chunks.append("".join(tokens))
    return "".join(chunks), dict(counts)


def _keep_addresses(email: InboundEmail) -> frozenset[str]:
    """Sender/recipient addresses are preserved (never redacted)."""
    keep = set()
    sender = str((email.FromFull or {}).get("Email") or "").lower()
    if sender:
        keep.add(sender)
    for recipient in email.ToFull or []:
        if isinstance(recipient, dict):
            address = str(recipient.get("Email") or "").lower()
            if address:
                keep.add(address)
    return frozenset(keep)


def _fallback_redact_email(
    email: InboundEmail,
) -> tuple[InboundEmail, dict[str, int]]:
    """FALLBACK for redact.redact_email."""
    keep = _keep_addresses(email)
    counts: Counter[str] = Counter()
    text_body, text_counts = _fallback_redact_text(email.TextBody, keep)
    counts.update(text_counts)
    html_body, html_counts = _fallback_redact_html(email.HtmlBody, keep)
    counts.update(html_counts)
    redacted = email.model_copy(update={"TextBody": text_body, "HtmlBody": html_body})
    return redacted, dict(counts)


try:
    from backend.intake.redact import redact_email
except ImportError:
    redact_email = _fallback_redact_email
    INTAKE_FALLBACKS.append("redact")


def _safe_redact(email: InboundEmail) -> tuple[InboundEmail, dict[str, int]]:
    """Call the real redactor; degrade to the fallback if it blows up at
    call time (e.g. Presidio/spacy model not installed on this box)."""
    try:
        return redact_email(email)
    except Exception:  # noqa: BLE001 - heavy dep failure must not drop email
        if redact_email is not _fallback_redact_email:
            logger.exception("redact_email failed; using fallback redaction")
            return _fallback_redact_email(email)
        raise


# =============================================================================
# GLiNER guard: pipeline falls back on ImportError only, but gliner_extract
# raises ExtractionUnavailable at CALL time when the gliner2 package/model is
# missing, which would 500 every plaintext email. Wrap it so the pipeline's
# regex extractor carries the load instead. Real GLiNER is used untouched
# whenever it actually works.
# =============================================================================


def _install_gliner_guard() -> None:
    try:
        from backend.extraction import pipeline as _pipeline
        from backend.extraction.gliner_extract import ExtractionUnavailable
        from backend.extraction.types import FieldCandidates
    except ImportError:
        return
    original = _pipeline.extract_fields
    if getattr(original, "_intake_guarded", False):
        return

    def _guarded_extract_fields(text: str) -> FieldCandidates:
        try:
            return original(text)
        except ExtractionUnavailable:
            return FieldCandidates()

    _guarded_extract_fields._intake_guarded = True  # type: ignore[attr-defined]
    _pipeline.extract_fields = _guarded_extract_fields


_install_gliner_guard()


# =============================================================================
# Events: in-process reward_added queue drained by main.py's /events SSE loop
# =============================================================================

_events_lock = threading.Lock()
_event_queues: dict[UUID, Deque[Event]] = defaultdict(lambda: deque(maxlen=256))


def emit_event(event: Event) -> None:
    """Queue an event for delivery on the /events SSE stream."""
    with _events_lock:
        _event_queues[event.user_id].append(event)


def drain_events(user_id: UUID) -> list[Event]:
    """Pop all pending events for a user (called by the /events generator)."""
    with _events_lock:
        queue = _event_queues.get(user_id)
        if not queue:
            return []
        events = list(queue)
        queue.clear()
        return events


# =============================================================================
# Payload coercion: Postmark sends extra fields and demos send partial ones.
# Build a valid InboundEmail from whatever parseable JSON object we received
# so Postmark always gets a 200 instead of a 422 retry loop.
# =============================================================================


def coerce_inbound_email(payload: dict) -> InboundEmail:
    """Tolerantly convert a raw (Postmark-shaped) JSON object to InboundEmail."""
    from_full = payload.get("FromFull")
    if not isinstance(from_full, dict):
        from_full = {"Email": str(payload.get("From") or ""), "Name": ""}

    to_full = payload.get("ToFull")
    if not isinstance(to_full, list):
        to_address = str(payload.get("To") or "")
        to_full = [{"Email": addr.strip(), "Name": ""} for addr in to_address.split(",") if addr.strip()]
    to_full = [entry for entry in to_full if isinstance(entry, dict)]

    def _opt_str(key: str) -> str | None:
        value = payload.get(key)
        return value if isinstance(value, str) else None

    attachments = payload.get("Attachments")
    headers = payload.get("Headers")
    data = {
        "MessageID": str(payload.get("MessageID") or "") or f"unknown-{uuid4()}",
        "FromFull": from_full,
        "ToFull": to_full,
        "Subject": str(payload.get("Subject") or ""),
        "TextBody": _opt_str("TextBody"),
        "HtmlBody": _opt_str("HtmlBody"),
        "Date": str(payload.get("Date") or ""),
        "MailboxHash": str(payload.get("MailboxHash") or ""),
        "Attachments": attachments if isinstance(attachments, list) else [],
        "Headers": headers if isinstance(headers, list) else [],
    }
    try:
        return InboundEmail.model_validate(data)
    except Exception:  # noqa: BLE001 - e.g. malformed attachment entries
        data["Attachments"] = []
        data["Headers"] = []
        return InboundEmail.model_validate(data)


# =============================================================================
# Persistence: the in-memory rewards store main.py already uses
# =============================================================================

# Standalone fallback store, used only if backend.app.main is unavailable.
_fallback_reward_store: list[Reward] = []


def _persist_rewards(rewards: list[Reward]) -> None:
    try:
        from backend.app.main import get_rewards
    except ImportError:
        _fallback_reward_store.extend(rewards)
        return
    get_rewards().extend(rewards)


# =============================================================================
# process_inbound: the shared-interface entry point
# =============================================================================


def process_inbound(
    email: InboundEmail,
    user_id: UUID | None = None,
    *,
    source: str = "postmark",
    force: bool = False,
) -> IntakeInboundResult:
    """Full intake flow for one inbound email. Always returns a 200-style
    result (see module docstring for the unknown-recipient/duplicate policy).
    `force=True` bypasses the dedupe check so demos can replay emails."""
    started = time.perf_counter()

    def _elapsed_ms() -> int:
        return int((time.perf_counter() - started) * 1000)

    resolved = user_id or resolve_user(email)
    if resolved is None:
        logger.warning(
            "inbound email %s (%s): no user for recipient; dropping",
            email.MessageID,
            source,
        )
        return IntakeInboundResult(
            message_id=email.MessageID,
            classification=EmailClassification.other,
            rewards_extracted=0,
            note="unknown_recipient",
            processing_time_ms=_elapsed_ms(),
        )

    if not force and seen_before(email, resolved):
        logger.info("inbound email %s (%s): duplicate; skipping", email.MessageID, source)
        return IntakeInboundResult(
            message_id=email.MessageID,
            classification=EmailClassification.other,
            rewards_extracted=0,
            duplicate=True,
            note="duplicate",
            processing_time_ms=_elapsed_ms(),
        )

    redacted, redaction_counts = _safe_redact(email)

    try:
        from backend.extraction.pipeline import run_pipeline

        result = run_pipeline(redacted, resolved)
    except Exception:  # noqa: BLE001 - Postmark must still receive a 200
        logger.exception("extraction failed for email %s", email.MessageID)
        return IntakeInboundResult(
            message_id=email.MessageID,
            classification=EmailClassification.other,
            rewards_extracted=0,
            note="extraction_error",
            processing_time_ms=_elapsed_ms(),
        )

    _persist_rewards(result.rewards)
    mark_processed(email, resolved)

    for reward in result.rewards:
        emit_event(
            Event(
                event_type=EventType.reward_added,
                user_id=resolved,
                reward_id=reward.id,
                data={
                    "merchant_name": reward.merchant_name,
                    "kind": reward.kind.value,
                    "value": str(reward.value),
                    "code": reward.code,
                    "source": source,
                },
            )
        )

    logger.info(
        "inbound email %s (%s) -> user %s: %d reward(s), redacted=%s",
        email.MessageID,
        source,
        resolved,
        len(result.rewards),
        redaction_counts or "{}",
    )
    return IntakeInboundResult(
        message_id=email.MessageID,
        classification=EmailClassification(result.classification),
        rewards_extracted=len(result.rewards),
        reward_ids=[r.id for r in result.rewards],
        needs_review=any(r.status == RewardStatus.needs_review for r in result.rewards),
        processing_time_ms=_elapsed_ms(),
    )


# =============================================================================
# Introspection / test helpers
# =============================================================================


def intake_status() -> dict[str, str]:
    """Which intake stages run real modules vs built-in fallbacks."""
    return {
        stage: ("fallback" if stage in INTAKE_FALLBACKS else "real")
        for stage in ("routing", "dedupe", "redact")
    }


def reset_intake_state() -> None:
    """Clear in-memory dedupe/event/reward state (used by tests and demos)."""
    with _dedupe_lock:
        _seen_messages.clear()
    with _events_lock:
        _event_queues.clear()
    _fallback_reward_store.clear()
    if "dedupe" not in INTAKE_FALLBACKS:
        # Best effort: let a real dedupe module reset its in-memory state too.
        try:
            from backend.intake import dedupe as _dedupe_module

            for name in ("reset", "clear", "_reset"):
                hook = getattr(_dedupe_module, name, None)
                if callable(hook):
                    hook()
                    break
        except Exception:  # noqa: BLE001 - purely best-effort test hygiene
            pass
