"""Tests for backend/intake/redact.py (Agent A).

Runs the same assertions twice:
* mode="auto"     - Presidio + spaCy if installed, otherwise the regex fallback
* mode="fallback" - regex fallback forced (Presidio disabled via monkeypatch)

Plus: markup/JSON-LD safety, and an extraction-equivalence check proving that
redacting any of the 5 seed emails does not change what
backend.extraction.pipeline extracts. Warm per-email redaction latency is
printed by test_warm_latency_report (run pytest with -s to see it).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

pytest.importorskip("pydantic", reason="core backend deps not installed")

from backend.app.schemas import InboundEmail
from backend.intake import redact
from backend.intake.redact import redact_email, redact_html, redact_text

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_DIR = REPO_ROOT / "shared" / "seed" / "emails"
SEED_EMAILS = [
    "hollister_10_percent.eml",
    "target_jsonld_offer.eml",
    "chipotle_plaintext.eml",
    "nike_promo.eml",
    "amazon_receipt.eml",
]
DEMO_USER = "00000000-0000-0000-0000-000000000001"


def _presidio_available() -> bool:
    try:
        import presidio_analyzer  # noqa: F401
        import spacy

        spacy.load("en_core_web_sm")
        return True
    except Exception:  # noqa: BLE001
        return False


HAS_PRESIDIO = _presidio_available()


@pytest.fixture(params=["auto", "fallback"])
def mode(request, monkeypatch):
    """Run each test against the live engine AND the forced regex fallback."""
    if request.param == "fallback":
        monkeypatch.setattr(redact, "_get_analyzer", lambda: None)
    return request.param


# ---------------------------------------------------------------------------
# PII IS redacted
# ---------------------------------------------------------------------------

def test_credit_card_redacted(mode):
    out, counts = redact_text("Your card 4111 1111 1111 1111 was charged.")
    assert "4111" not in out
    assert "<CARD>" in out
    assert counts["CREDIT_CARD"] == 1


def test_credit_card_contiguous_and_amex(mode):
    out, counts = redact_text(
        "Visa 4111111111111111 and Amex 3782 822463 10005 on file."
    )
    assert "4111111111111111" not in out
    assert "822463" not in out
    assert out.count("<CARD>") == 2
    assert counts["CREDIT_CARD"] == 2


@pytest.mark.parametrize(
    "phone",
    ["(206) 555-0143", "206-555-0143", "+1 206 555 0143", "1-800-806-6453"],
)
def test_phone_redacted(mode, phone):
    out, counts = redact_text(f"Questions? Call {phone} any time.")
    assert phone not in out
    assert "<PHONE>" in out
    assert counts["PHONE_NUMBER"] >= 1


def test_email_redacted_but_keep_preserved(mode):
    text = "Contact support@randomstore.com or reply to rewards@chipotle.com."
    out, counts = redact_text(text, keep={"rewards@chipotle.com"})
    assert "support@randomstore.com" not in out
    assert "<EMAIL>" in out
    assert "rewards@chipotle.com" in out  # sender address preserved
    assert counts["EMAIL_ADDRESS"] == 1


@pytest.mark.parametrize(
    "address",
    ["123 Main St, Apt 4", "456 Evergreen Terrace", "9801 N. Lamar Blvd Suite 200"],
)
def test_street_address_redacted(mode, address):
    out, counts = redact_text(f"Ship to {address} by Friday.")
    assert address not in out
    assert "<ADDRESS>" in out
    assert counts["STREET_ADDRESS"] == 1


# ---------------------------------------------------------------------------
# Non-PII is NOT redacted
# ---------------------------------------------------------------------------

NEGATIVE_TEXTS = [
    "Use code HCOFALL10 at checkout for 10% off.",
    "Code: TARGET5 saves you $5 when you spend $25 or more.",
    "Your FREEGUAC reward: minimum purchase $10.",
    "Order Total: $357.52 (Tax: $29.52).",
    "Get 20% OFF select styles, maximum discount $50.",
    "Valid through: October 31, 2026. Expires 10/31/2026.",
    "Shop Hollister, Target and Chipotle in Seattle.",
    "Order #112-3456789-0123456 arriving Friday, October 18.",
    "You're only 50 points away from your next free entree!",
]


@pytest.mark.parametrize("text", NEGATIVE_TEXTS)
def test_non_pii_untouched(mode, text):
    out, counts = redact_text(text)
    assert out == text, f"falsely redacted: {counts}"
    assert counts == {}


def test_none_and_empty_inputs(mode):
    assert redact_text(None) == (None, {})
    assert redact_text("") == ("", {})


# ---------------------------------------------------------------------------
# HTML handling
# ---------------------------------------------------------------------------

HTML_SAMPLE = """<!DOCTYPE html>
<html><head>
<script type="application/ld+json">
{
  "@type": "DiscountOffer",
  "discountCode": "HCOFALL10",
  "discount": "10",
  "validThrough": "2026-10-20T23:59:59-07:00",
  "seller": {"name": "Hollister Co.", "email": "pii-leak@example.com", "telephone": "(206) 555-0143"}
}
</script>
<script>var tracking = "support@randomstore.com";</script>
<style>.card4111 { color: red; }</style>
</head>
<body>
<div style="max-width: 600px;">
  <p>Use code HCOFALL10 before October 20, 2026 at Hollister.</p>
  <p>Card on file: 4111 1111 1111 1111. Call (425) 555-0100.</p>
  <p>Ship to 123 Main St, Apt 4. Contact buyer@example.com.</p>
  <a href="mailto:unsub@example.com">Unsubscribe</a>
</div>
</body></html>"""


def test_html_text_nodes_redacted_markup_intact(mode):
    out, counts = redact_html(HTML_SAMPLE)
    # PII inside text nodes is gone
    assert "4111 1111 1111 1111" not in out
    assert "(425) 555-0100" not in out
    assert "123 Main St" not in out
    assert "buyer@example.com" not in out
    # markup untouched
    assert '<div style="max-width: 600px;">' in out
    assert '<a href="mailto:unsub@example.com">' in out
    assert counts["CREDIT_CARD"] == 1
    assert counts["STREET_ADDRESS"] == 1


def test_html_jsonld_promo_fields_survive_but_email_phone_redacted(mode):
    out, _ = redact_html(HTML_SAMPLE)
    start = out.index('<script type="application/ld+json">') + len(
        '<script type="application/ld+json">'
    )
    end = out.index("</script>", start)
    block = json.loads(out[start:end])
    # promo fields untouched
    assert block["discountCode"] == "HCOFALL10"
    assert block["discount"] == "10"
    assert block["validThrough"] == "2026-10-20T23:59:59-07:00"
    assert block["seller"]["name"] == "Hollister Co."
    # email/phone values inside JSON-LD are redacted
    assert block["seller"]["email"] == "<EMAIL>"
    assert block["seller"]["telephone"] == "<PHONE>"


def test_html_plain_scripts_and_styles_untouched(mode):
    out, _ = redact_html(HTML_SAMPLE)
    assert 'var tracking = "support@randomstore.com";' in out
    assert ".card4111 { color: red; }" in out


def test_html_none(mode):
    assert redact_html(None) == (None, {})


# ---------------------------------------------------------------------------
# redact_email
# ---------------------------------------------------------------------------

def _make_email(text=None, html=None) -> InboundEmail:
    return InboundEmail(
        MessageID="test-001",
        FromFull={"Email": "rewards@store.com", "Name": "Store"},
        ToFull=[{"Email": "demo@lapse.app", "Name": "Demo"}],
        Subject="Test",
        TextBody=text,
        HtmlBody=html,
        Date="Sat, 12 Oct 2026 09:15:00 -0700",
    )


def test_redact_email_keeps_sender_recipient(mode):
    email = _make_email(
        text=(
            "From rewards@store.com to demo@lapse.app: forward to "
            "friend@gmail.com. Card 4111 1111 1111 1111."
        )
    )
    redacted, counts = redact_email(email)
    assert "rewards@store.com" in redacted.TextBody
    assert "demo@lapse.app" in redacted.TextBody
    assert "friend@gmail.com" not in redacted.TextBody
    assert "<CARD>" in redacted.TextBody
    assert counts["EMAIL_ADDRESS"] == 1
    assert counts["CREDIT_CARD"] == 1
    # original is not mutated
    assert "friend@gmail.com" in email.TextBody


def test_redact_email_handles_both_bodies(mode):
    email = _make_email(
        text="Call (206) 555-0143.",
        html="<p>Call (206) 555-0143.</p>",
    )
    redacted, counts = redact_email(email)
    assert "<PHONE>" in redacted.TextBody
    assert "<p>" in redacted.HtmlBody and "<PHONE>" in redacted.HtmlBody
    assert counts["PHONE_NUMBER"] == 2


# ---------------------------------------------------------------------------
# Seed-email extraction equivalence + latency
# ---------------------------------------------------------------------------

def _reward_key_fields(reward):
    return (
        reward.merchant_name,
        reward.kind,
        reward.value,
        reward.code,
        reward.min_spend,
        reward.max_discount,
        reward.expires_at,
        reward.stackable,
        tuple(reward.exclusions),
    )


def _load_seed(filename: str) -> InboundEmail:
    from backend.extraction.pipeline import parse_eml

    return parse_eml((SEED_DIR / filename).read_bytes())


@pytest.fixture
def pipeline_mod(monkeypatch):
    """Extraction pipeline; GLiNER is stubbed out when gliner2 isn't installed.

    gliner_extract raises ExtractionUnavailable without the (heavy, optional)
    gliner2/torch stack, which would crash run_pipeline for original AND
    redacted emails alike. Stubbing it with an empty FieldCandidates matches
    the pipeline's own fallback; markup + regex extraction stay fully real.
    """
    pipeline = pytest.importorskip("backend.extraction.pipeline")
    try:
        import gliner2  # noqa: F401
    except ImportError:
        from backend.extraction.types import FieldCandidates

        monkeypatch.setattr(
            pipeline, "extract_fields", lambda text: FieldCandidates()
        )
    return pipeline


@pytest.mark.parametrize("filename", SEED_EMAILS)
def test_seed_email_extraction_unchanged_by_redaction(filename, pipeline_mod):
    pipeline = pipeline_mod

    email = _load_seed(filename)
    redacted, _counts = redact_email(email)

    original = pipeline.run_pipeline(email, DEMO_USER)
    after = pipeline.run_pipeline(redacted, DEMO_USER)

    assert after.classification == original.classification
    assert len(after.rewards) == len(original.rewards)
    for before_reward, after_reward in zip(original.rewards, after.rewards):
        assert _reward_key_fields(after_reward) == _reward_key_fields(
            before_reward
        ), f"{filename}: reward fields changed by redaction"


def test_warm_latency_report():
    emails = [_load_seed(name) for name in SEED_EMAILS]
    redact_email(emails[0])  # warm the lazy singleton engine

    engine = "presidio" if HAS_PRESIDIO else "regex-fallback"
    print(f"\nWarm redaction latency per seed email ({engine}):")
    total = 0.0
    for name, email in zip(SEED_EMAILS, emails):
        start = time.perf_counter()
        redact_email(email)
        elapsed_ms = (time.perf_counter() - start) * 1000
        total += elapsed_ms
        print(f"  {name:32s} {elapsed_ms:8.1f} ms")
        assert elapsed_ms < 5000, f"{name} warm redaction too slow"
    print(f"  {'TOTAL':32s} {total:8.1f} ms")
