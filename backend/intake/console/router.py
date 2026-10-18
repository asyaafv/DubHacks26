"""Demo merchant console router (Agent D).

Mounted by the integrator at /demo/console. Serves a fake "merchant
marketing" tool that sends realistic reward emails either through real
Postmark outbound (so they travel through inbound back to /inbound) or
instantly in-process through the intake/extraction pipeline.
"""
from __future__ import annotations

import importlib.util
import inspect
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from backend.app.schemas import EmailClassification, InboundEmail, InboundResult, Reward, RewardStatus
from backend.intake.console import emails as console_emails

logger = logging.getLogger("lapse.intake.console")

router = APIRouter()

DEMO_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
POSTMARK_API_URL = "https://api.postmarkapp.com/email"
_PAGE_PATH = Path(__file__).parent / "console.html"


class SendRequest(BaseModel):
    """POST /send payload."""

    template_id: str
    overrides: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["email", "instant"] = "instant"
    user_id: UUID | None = None


# ---------------------------------------------------------------------------
# Config helpers (never hardcode secrets)
# ---------------------------------------------------------------------------

def _postmark_token() -> str | None:
    return os.getenv("POSTMARK_SERVER_TOKEN") or None


def _from_email() -> str | None:
    return os.getenv("DEMO_FROM_EMAIL") or None


def _email_disabled_reason() -> str | None:
    if not _postmark_token():
        return "POSTMARK_SERVER_TOKEN is not set"
    if not _from_email():
        return "DEMO_FROM_EMAIL is not set"
    return None


def _default_recipient(user_id: UUID) -> str:
    """User's inbound address: env override, then routing module, then default."""
    env_addr = os.getenv("POSTMARK_INBOUND_ADDRESS")
    if env_addr:
        return env_addr
    try:  # Agent B's module; may not exist on every branch.
        from backend.intake.routing import inbox_address_for

        addr = inbox_address_for(user_id)
        if addr:
            return str(addr)
    except Exception:  # noqa: BLE001 - defensive cross-agent import
        pass
    return console_emails.DEFAULT_RECIPIENT


# ---------------------------------------------------------------------------
# Instant processing (in-process intake), defensive across parallel agents
# ---------------------------------------------------------------------------

def _ensure_pipeline_tolerates_missing_gliner() -> None:
    """The real gliner_extract raises at call time when gliner2 isn't
    installed and run_pipeline doesn't guard that call. Wrap it once so the
    demo keeps working on machines without the heavy ML deps."""
    if importlib.util.find_spec("gliner2") is not None:
        return
    try:
        from backend.extraction import pipeline
        from backend.extraction.types import FieldCandidates

        real = pipeline.extract_fields
        if getattr(real, "__console_shim__", False):
            return

        def _shim(text: str) -> FieldCandidates:
            try:
                return real(text)
            except Exception:  # noqa: BLE001 - model unavailable
                return FieldCandidates()

        _shim.__console_shim__ = True  # type: ignore[attr-defined]
        pipeline.extract_fields = _shim
    except Exception:  # noqa: BLE001 - never break the console over this
        pass


def _reward_card(reward: Reward) -> dict[str, Any]:
    return {
        "id": str(reward.id),
        "merchant_name": reward.merchant_name,
        "kind": reward.kind.value,
        "value": str(reward.value),
        "code": reward.code,
        "min_spend": str(reward.min_spend) if reward.min_spend is not None else None,
        "expires_at": reward.expires_at.isoformat() if reward.expires_at else None,
        "overall_confidence": reward.overall_confidence,
        "status": reward.status.value,
        "source": reward.source.value,
        "source_email_id": reward.source_email_id,
        "created_at": reward.created_at.isoformat() if reward.created_at else None,
    }


def _app_rewards_store() -> list[Reward] | None:
    try:
        from backend.app.main import get_rewards

        return get_rewards()
    except Exception:  # noqa: BLE001 - app may not be importable standalone
        return None


def _cards_for_ids(reward_ids: list[UUID]) -> list[dict[str, Any]]:
    store = _app_rewards_store()
    if store is None:
        return []
    wanted = set(reward_ids)
    return [_reward_card(r) for r in store if r.id in wanted]


def _process_instant(email: InboundEmail, user_id: UUID) -> tuple[InboundResult, list[dict[str, Any]]]:
    """Run intake in-process: intake service -> app inject path -> raw pipeline."""
    _ensure_pipeline_tolerates_missing_gliner()

    # 1. Agent C's intake service, if present.
    process_inbound = None
    try:
        from backend.intake.service import process_inbound  # type: ignore[no-redef]
    except Exception:  # noqa: BLE001 - not on this branch yet
        process_inbound = None
    if process_inbound is not None:
        try:
            result = process_inbound(email, user_id=user_id, source="console")
            if inspect.isawaitable(result):
                import asyncio

                result = asyncio.run(result)
            return result, _cards_for_ids(result.reward_ids)
        except Exception as exc:  # noqa: BLE001 - fall through to inject path
            logger.warning("intake service failed, falling back: %s", exc)

    # 2. The app's own /demo/inject-style path (stores rewards for /sync).
    try:
        from backend.app.main import _run_extraction

        result = _run_extraction(email, user_id)
        return result, _cards_for_ids(result.reward_ids)
    except Exception as exc:  # noqa: BLE001 - app module may be unavailable
        logger.warning("app inject path failed, using raw pipeline: %s", exc)

    # 3. Raw extraction pipeline as the last resort.
    from backend.extraction.pipeline import run_pipeline

    pr = run_pipeline(email, user_id)
    store = _app_rewards_store()
    if store is not None:
        store.extend(pr.rewards)
    result = InboundResult(
        message_id=email.MessageID,
        classification=EmailClassification(pr.classification),
        rewards_extracted=len(pr.rewards),
        reward_ids=[r.id for r in pr.rewards],
        needs_review=any(r.status == RewardStatus.needs_review for r in pr.rewards),
        processing_time_ms=int(pr.timings_ms.get("total_ms", 0)),
    )
    return result, [_reward_card(r) for r in pr.rewards]


# ---------------------------------------------------------------------------
# Real email via Postmark outbound
# ---------------------------------------------------------------------------

def _post_postmark(payload: dict[str, Any], token: str) -> dict[str, Any]:
    """POST to Postmark's outbound API. Split out so tests can mock it."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": token,
    }
    try:
        resp = httpx.post(POSTMARK_API_URL, json=payload, headers=headers, timeout=15.0)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Postmark request failed: {exc}") from exc
    if resp.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"Postmark error {resp.status_code}: {resp.text[:300]}",
        )
    data = resp.json()
    if data.get("ErrorCode"):
        raise HTTPException(status_code=502, detail=f"Postmark error: {data.get('Message')}")
    return data


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def console_page() -> HTMLResponse:
    """The merchant console page (inline CSS/JS, no build step)."""
    return HTMLResponse(_PAGE_PATH.read_text(encoding="utf-8"))


@router.get("/templates")
def list_templates() -> dict[str, Any]:
    """Store templates plus console config for the UI."""
    return {
        "templates": console_emails.template_payload(),
        "config": {
            "email_enabled": _email_disabled_reason() is None,
            "email_disabled_reason": _email_disabled_reason(),
            "from_email": _from_email(),
            "default_recipient": _default_recipient(DEMO_USER_ID),
            "demo_user_id": str(DEMO_USER_ID),
        },
    }


@router.get("/rewards")
def recent_rewards(user_id: UUID | None = None) -> dict[str, Any]:
    """Recent reward cards for the result panel (fallback when /sync is
    unavailable, e.g. no database configured)."""
    uid = user_id or DEMO_USER_ID
    store = _app_rewards_store()
    if store is None:
        return {"rewards": [], "available": False}
    cards = [_reward_card(r) for r in store if r.user_id == uid]
    cards.sort(key=lambda c: c["created_at"] or "", reverse=True)
    return {"rewards": cards[:25], "available": True}


@router.post("/send")
def send(req: SendRequest) -> dict[str, Any]:
    """Render the chosen template and send it (real email or instant inject)."""
    if req.template_id not in console_emails.TEMPLATES_BY_ID:
        raise HTTPException(status_code=404, detail=f"Unknown template: {req.template_id}")

    user_id = req.user_id or DEMO_USER_ID
    recipient = (req.overrides.get("recipient") or "").strip() or _default_recipient(user_id)
    try:
        rendered = console_emails.render_email(req.template_id, req.overrides, recipient)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Bad overrides: {exc}") from exc

    started = time.perf_counter()
    base: dict[str, Any] = {
        "mode": req.mode,
        "template_id": req.template_id,
        "merchant": rendered.merchant,
        "subject": rendered.subject,
        "to": recipient,
        "message_id": rendered.message_id,
        "user_id": str(user_id),
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }

    if req.mode == "email":
        reason = _email_disabled_reason()
        if reason:
            raise HTTPException(status_code=503, detail=f"Email mode disabled: {reason}")
        payload: dict[str, Any] = {
            "From": _from_email(),
            "To": recipient,
            "Subject": rendered.subject,
            "TextBody": rendered.text,
            "MessageStream": "outbound",
        }
        if rendered.html:
            payload["HtmlBody"] = rendered.html
        data = _post_postmark(payload, _postmark_token() or "")
        base["postmark"] = {
            "message_id": data.get("MessageID"),
            "submitted_at": data.get("SubmittedAt"),
            "to": data.get("To"),
        }
        base["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
        return base

    # Instant mode: parse our own .eml and run intake in-process.
    from backend.extraction.pipeline import parse_eml

    email = parse_eml(rendered.eml_bytes)
    result, cards = _process_instant(email, user_id)
    base["result"] = result.model_dump(mode="json")
    base["rewards"] = cards
    base["elapsed_ms"] = int((time.perf_counter() - started) * 1000)
    return base
