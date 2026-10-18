"""Tests for the demo merchant console (Agent D).

Covers: every template renders a valid .eml that parse_eml accepts and the
extraction pipeline turns into the right reward; instant mode end-to-end via
a TestClient app mounting the console router; email mode fully mocked.
"""
from __future__ import annotations

import importlib.util
from decimal import Decimal
from uuid import UUID

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.extraction import pipeline
from backend.intake.console import emails as console_emails
from backend.intake.console import router as console_router_module
from backend.intake.console.router import router as console_router

DEMO_USER = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture(autouse=True)
def _tolerate_missing_gliner(monkeypatch):
    """The real gliner_extract raises at call time when gliner2 isn't
    installed; shim it to empty candidates so the regex path is exercised."""
    if importlib.util.find_spec("gliner2") is None:
        from backend.extraction.types import FieldCandidates

        monkeypatch.setattr(pipeline, "extract_fields", lambda text: FieldCandidates())


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(console_router, prefix="/demo/console")
    return TestClient(app)


# ---------------------------------------------------------------------------
# Template rendering -> parse_eml -> extraction pipeline
# ---------------------------------------------------------------------------

# template_id -> (kind, value, code, merchant_name or None if not in seed)
EXPECTED = {
    "hollister_10": ("percent_off", Decimal("10"), "HCOFALL10", "Hollister"),
    "tacobell_crunchwrap": ("free_item", Decimal("1"), "CRUNCHTIME", "Taco Bell"),
    "ulta_points": ("points", Decimal("500"), None, "Ulta Beauty"),
    "pacsun_bogo": ("bogo", Decimal("1"), "PACBOGO", None),
    "aero_50": ("percent_off", Decimal("50"), "AERO50", None),
    "target_5off": ("amount_off", Decimal("5"), "CIRCLE5", "Target"),
}


def test_all_templates_covered():
    assert set(EXPECTED) == {t.id for t in console_emails.TEMPLATES}
    assert len(console_emails.TEMPLATES) == 6


@pytest.mark.parametrize("template_id", sorted(EXPECTED))
def test_eml_parses(template_id):
    raw = console_emails.render_eml(template_id)
    email = pipeline.parse_eml(raw)
    assert email.MessageID
    assert email.Subject
    assert email.ToFull[0]["Email"] == console_emails.DEFAULT_RECIPIENT
    spec = console_emails.TEMPLATES_BY_ID[template_id]
    assert email.FromFull["Email"] == spec.from_email
    assert email.TextBody
    if spec.jsonld:
        assert email.HtmlBody and "application/ld+json" in email.HtmlBody


@pytest.mark.parametrize("template_id", sorted(EXPECTED))
def test_pipeline_extracts_expected_reward(template_id):
    kind, value, code, merchant = EXPECTED[template_id]
    raw = console_emails.render_eml(template_id)
    email = pipeline.parse_eml(raw)
    result = pipeline.run_pipeline(email, DEMO_USER)

    assert result.classification == "reward", (
        f"{template_id} classified as {result.classification}"
    )
    assert len(result.rewards) == 1
    reward = result.rewards[0]
    assert reward.kind.value == kind
    assert reward.value == value
    assert reward.code == code
    if merchant is not None:
        assert reward.merchant_name == merchant
    # Every template carries an expiry.
    assert reward.expires_at is not None


def test_jsonld_templates_use_markup_source():
    raw = console_emails.render_eml("hollister_10")
    result = pipeline.run_pipeline(pipeline.parse_eml(raw), DEMO_USER)
    assert result.rewards[0].source.value == "email_jsonld"


def test_overrides_flow_through_to_reward():
    raw = console_emails.render_eml(
        "hollister_10",
        overrides={"value": 25, "code": "CUSTOM25", "expiry_days": 1, "min_spend": 75},
    )
    result = pipeline.run_pipeline(pipeline.parse_eml(raw), DEMO_USER)
    reward = result.rewards[0]
    assert reward.value == Decimal("25")
    assert reward.code == "CUSTOM25"
    assert reward.min_spend == Decimal("75")


def test_custom_recipient():
    raw = console_emails.render_eml("target_5off", recipient="abc123@lapse.app")
    email = pipeline.parse_eml(raw)
    assert email.ToFull[0]["Email"] == "abc123@lapse.app"


def test_unknown_template_raises():
    with pytest.raises(KeyError):
        console_emails.render_eml("nope")


# ---------------------------------------------------------------------------
# Router: page + templates + instant mode end-to-end
# ---------------------------------------------------------------------------

def test_console_page(client):
    resp = client.get("/demo/console/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Lapse" in resp.text


def test_templates_endpoint(client, monkeypatch):
    monkeypatch.delenv("POSTMARK_SERVER_TOKEN", raising=False)
    resp = client.get("/demo/console/templates")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["templates"]) == 6
    ids = {t["id"] for t in data["templates"]}
    assert ids == set(EXPECTED)
    assert data["config"]["email_enabled"] is False
    assert data["config"]["email_disabled_reason"]
    assert data["config"]["default_recipient"]


@pytest.mark.parametrize("template_id", ["hollister_10", "tacobell_crunchwrap"])
def test_instant_mode_end_to_end(client, template_id):
    resp = client.post(
        "/demo/console/send",
        json={"template_id": template_id, "overrides": {}, "mode": "instant"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mode"] == "instant"
    assert data["result"]["classification"] == "reward"
    assert data["result"]["rewards_extracted"] == 1
    assert len(data["rewards"]) == 1
    kind, value, code, _merchant = EXPECTED[template_id]
    card = data["rewards"][0]
    assert card["kind"] == kind
    assert Decimal(card["value"]) == value
    assert card["code"] == code
    assert "elapsed_ms" in data


def test_instant_mode_with_overrides(client):
    resp = client.post(
        "/demo/console/send",
        json={
            "template_id": "target_5off",
            "overrides": {"value": 10, "code": "BULLSEYE10"},
            "mode": "instant",
        },
    )
    assert resp.status_code == 200, resp.text
    card = resp.json()["rewards"][0]
    assert Decimal(card["value"]) == Decimal("10")
    assert card["code"] == "BULLSEYE10"


def test_send_unknown_template_404(client):
    resp = client.post(
        "/demo/console/send", json={"template_id": "nope", "mode": "instant"}
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Email mode (mocked: no real network)
# ---------------------------------------------------------------------------

def test_email_mode_disabled_without_token(client, monkeypatch):
    monkeypatch.delenv("POSTMARK_SERVER_TOKEN", raising=False)
    resp = client.post(
        "/demo/console/send", json={"template_id": "hollister_10", "mode": "email"}
    )
    assert resp.status_code == 503


def test_email_mode_mocked(client, monkeypatch):
    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "test-token-123")
    monkeypatch.setenv("DEMO_FROM_EMAIL", "studio@lapse.app")
    monkeypatch.setenv("POSTMARK_INBOUND_ADDRESS", "inbound+demo@lapse.app")

    calls: list[tuple[dict, str]] = []

    def fake_post(payload, token):
        calls.append((payload, token))
        return {"MessageID": "pm-msg-1", "SubmittedAt": "2026-10-18T00:00:00Z", "To": payload["To"]}

    monkeypatch.setattr(console_router_module, "_post_postmark", fake_post)

    resp = client.post(
        "/demo/console/send", json={"template_id": "hollister_10", "mode": "email"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["mode"] == "email"
    assert data["postmark"]["message_id"] == "pm-msg-1"

    assert len(calls) == 1
    payload, token = calls[0]
    assert token == "test-token-123"
    assert payload["From"] == "studio@lapse.app"
    assert payload["To"] == "inbound+demo@lapse.app"
    assert "HCOFALL10" in payload["TextBody"]
    assert "application/ld+json" in payload["HtmlBody"]
    assert payload["MessageStream"] == "outbound"


def test_email_mode_transport_never_hits_network(client, monkeypatch):
    """Even at the httpx layer, email mode must not reach the real API."""
    monkeypatch.setenv("POSTMARK_SERVER_TOKEN", "test-token-123")
    monkeypatch.setenv("DEMO_FROM_EMAIL", "studio@lapse.app")

    import httpx

    captured: dict = {}

    def fake_httpx_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return httpx.Response(
            200,
            json={"MessageID": "pm-2", "ErrorCode": 0, "To": json["To"]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(console_router_module.httpx, "post", fake_httpx_post)

    resp = client.post(
        "/demo/console/send",
        json={
            "template_id": "ulta_points",
            "mode": "email",
            "overrides": {"recipient": "someone@lapse.app"},
        },
    )
    assert resp.status_code == 200, resp.text
    assert captured["url"] == "https://api.postmarkapp.com/email"
    assert captured["headers"]["X-Postmark-Server-Token"] == "test-token-123"
    assert captured["json"]["To"] == "someone@lapse.app"
