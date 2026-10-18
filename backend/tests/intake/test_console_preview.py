"""Tests for the merchant-console email preview (Agent D).

The core guarantee under test: everything the console shows is derived from
the exact .eml bytes that get sent or injected (sha256-verifiable), and the
extraction panel surfaces only real pipeline/intake output (per-field
confidence, dedupe, PII redaction, processing time).
"""
from __future__ import annotations

import hashlib
import importlib.util
from decimal import Decimal

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.extraction import pipeline
from backend.intake.console import emails as console_emails
from backend.intake.console.router import router as console_router


@pytest.fixture(autouse=True)
def _tolerate_missing_gliner(monkeypatch):
    if importlib.util.find_spec("gliner2") is None:
        from backend.extraction.types import FieldCandidates

        monkeypatch.setattr(pipeline, "extract_fields", lambda text: FieldCandidates())


@pytest.fixture(autouse=True)
def _fresh_intake_state():
    """Dedupe state is process-global; isolate it per test (and from the
    other console tests, which also inject these templates)."""
    try:
        from backend.intake import dedupe

        dedupe.reset()
    except Exception:  # noqa: BLE001 - module may be absent on some branches
        pass
    try:
        from backend.intake.service import reset_intake_state

        reset_intake_state()
    except Exception:  # noqa: BLE001
        pass
    yield


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(console_router, prefix="/demo/console")
    return TestClient(app)


# ---------------------------------------------------------------------------
# /preview: derived from the exact rendered bytes
# ---------------------------------------------------------------------------

def test_preview_payload_matches_eml_bytes(client):
    resp = client.post(
        "/demo/console/preview", json={"template_id": "hollister_10", "overrides": {}}
    )
    assert resp.status_code == 200, resp.text
    email = resp.json()["email"]

    # The sha256 is of the raw source shown; the raw source must itself be a
    # valid .eml that parse_eml accepts, with identical headers and bodies.
    raw_bytes = email["raw"].encode("utf-8")
    assert hashlib.sha256(raw_bytes).hexdigest() == email["sha256"]
    assert email["size_bytes"] == len(raw_bytes)

    parsed = pipeline.parse_eml(raw_bytes)
    assert parsed.Subject == email["subject"]
    assert parsed.MessageID == email["message_id"]
    assert parsed.FromFull["Email"] == "rewards@hollisterco.com"
    assert "rewards@hollisterco.com" in email["from"]
    assert email["to"] == console_emails.DEFAULT_RECIPIENT

    assert "HCOFALL10" in email["text"]
    assert email["html"] and "application/ld+json" in email["html"]
    assert "application/ld+json" in email["raw"]
    assert "multipart" in email["content_type"]


def test_preview_plain_text_template(client):
    resp = client.post(
        "/demo/console/preview", json={"template_id": "tacobell_crunchwrap"}
    )
    assert resp.status_code == 200
    email = resp.json()["email"]
    assert email["html"] is None
    assert email["content_type"] == "text/plain"
    assert "CRUNCHTIME" in email["text"]


def test_preview_reflects_overrides(client):
    resp = client.post(
        "/demo/console/preview",
        json={
            "template_id": "hollister_10",
            "overrides": {"value": 25, "code": "CUSTOM25", "recipient": "x@lapse.app"},
        },
    )
    assert resp.status_code == 200
    email = resp.json()["email"]
    assert "CUSTOM25" in email["text"]
    assert "CUSTOM25" in email["html"]
    assert "25%" in email["subject"]
    assert email["to"] == "x@lapse.app"


def test_preview_unknown_template_404(client):
    resp = client.post("/demo/console/preview", json={"template_id": "nope"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# /send: the response carries the exact bytes that were injected
# ---------------------------------------------------------------------------

def test_instant_send_email_payload_is_what_the_pipeline_saw(client):
    resp = client.post(
        "/demo/console/send", json={"template_id": "hollister_10", "mode": "instant"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    email = data["email"]

    # Byte identity: the pipeline result references the Message-ID parsed out
    # of the same bytes the preview shows, and the sha256 checks out.
    assert data["result"]["message_id"] == email["message_id"]
    assert hashlib.sha256(email["raw"].encode()).hexdigest() == email["sha256"]

    # Real extraction output, including per-field confidence.
    assert len(data["rewards"]) == 1
    card = data["rewards"][0]
    assert card["code"] == "HCOFALL10"
    assert Decimal(card["value"]) == Decimal("10")
    fc = card["field_confidence"]
    assert set(fc) == {"value", "expires_at", "code", "min_spend", "merchant"}
    assert all(0.0 <= v <= 1.0 for v in fc.values())
    assert data["result"]["processing_time_ms"] >= 0


def test_instant_send_dedupe_indicator_and_force(client):
    body = {"template_id": "target_5off", "mode": "instant"}
    first = client.post("/demo/console/send", json=body).json()
    assert first["duplicate"] is False
    assert len(first["rewards"]) == 1

    second = client.post("/demo/console/send", json=body).json()
    assert second["duplicate"] is True
    assert second["rewards"] == []
    # Same content -> same dedupe hash (that is what triggered the skip).
    assert second["content_hash"] == first["content_hash"]

    forced = client.post("/demo/console/send", json={**body, "force": True}).json()
    assert forced["duplicate"] is False
    assert len(forced["rewards"]) == 1


def test_pii_footer_is_in_bytes_and_gets_redacted(client):
    resp = client.post(
        "/demo/console/send",
        json={
            "template_id": "hollister_10",
            "mode": "instant",
            "overrides": {"pii_footer": True},
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # The PII is really in the sent bytes...
    assert "(800) 555-0199" in data["email"]["text"]
    assert "(800) 555-0199" in data["email"]["raw"]

    # ...intake's redaction reports scrubbing it...
    redaction = data["redaction"]
    assert redaction is not None
    assert redaction["counts"].get("PHONE_NUMBER", 0) >= 1
    assert redaction["total"] >= 1
    assert "(800) 555-0199" not in (redaction["redacted_text"] or "")

    # ...and extraction still produces the right reward.
    assert len(data["rewards"]) == 1
    assert data["rewards"][0]["code"] == "HCOFALL10"


def test_pii_footer_off_by_default():
    rendered = console_emails.render_email("hollister_10")
    assert "555-0199" not in rendered.text
    assert "555-0199" not in rendered.eml_bytes.decode("utf-8", errors="replace")


def test_email_mode_sends_same_bodies_as_preview(client, monkeypatch):
    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "test-token-123")
    monkeypatch.setenv("DEMO_FROM_EMAIL", "studio@lapse.app")

    from backend.intake.console import router as console_router_module

    calls: list[dict] = []

    def fake_post(payload, token):
        calls.append(payload)
        return {"MessageID": "pm-msg-1", "SubmittedAt": "2026-10-18T00:00:00Z", "To": payload["To"]}

    monkeypatch.setattr(console_router_module, "_post_postmark", fake_post)

    resp = client.post(
        "/demo/console/send", json={"template_id": "hollister_10", "mode": "email"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    email = data["email"]

    # What Postmark was given is exactly what the preview displays (the MIME
    # round-trip adds a single trailing newline to body parts, nothing else).
    assert len(calls) == 1
    assert calls[0]["TextBody"].rstrip("\n") == email["text"].rstrip("\n")
    assert calls[0]["HtmlBody"].rstrip("\n") == email["html"].rstrip("\n")
    assert calls[0]["Subject"] == email["subject"]
    assert hashlib.sha256(email["raw"].encode()).hexdigest() == email["sha256"]
