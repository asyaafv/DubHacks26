"""Tests for backend.extraction.clean against every seed .eml."""
from datetime import datetime
from pathlib import Path

import pytest

from backend.app.schemas import InboundEmail
from backend.extraction.clean import clean_email, parse_eml
from backend.extraction.types import CleanedEmail

EMAILS_DIR = Path(__file__).resolve().parents[3] / "shared" / "seed" / "emails"
EML_FILES = sorted(EMAILS_DIR.glob("*.eml"))


@pytest.fixture(params=EML_FILES, ids=lambda p: p.name)
def eml_path(request):
    return request.param


def test_seed_emails_present():
    assert len(EML_FILES) >= 5


def test_parse_eml_returns_valid_inbound_email(eml_path):
    email = parse_eml(eml_path.read_bytes())
    assert isinstance(email, InboundEmail)
    assert email.MessageID
    assert email.Subject
    assert "@" in email.FromFull["Email"]
    assert email.TextBody or email.HtmlBody
    assert email.Date


def test_clean_email_every_seed_eml(eml_path):
    cleaned = clean_email(parse_eml(eml_path.read_bytes()))
    assert isinstance(cleaned, CleanedEmail)
    assert cleaned.text.strip()
    assert cleaned.subject
    assert "@" in cleaned.sender
    assert cleaned.sender_domain and "." in cleaned.sender_domain
    assert isinstance(cleaned.received_at, datetime)
    assert cleaned.received_at.year == 2026
    # No raw HTML or JSON-LD leaked into the cleaned text.
    assert "<div" not in cleaned.text
    assert "<script" not in cleaned.text
    assert "@context" not in cleaned.text
    assert "font-family" not in cleaned.text


def test_clean_target_email():
    cleaned = clean_email(parse_eml((EMAILS_DIR / "target_jsonld_offer.eml").read_bytes()))
    assert cleaned.sender == "circle@target.com"
    assert cleaned.sender_domain == "target.com"
    assert cleaned.received_at.month == 10 and cleaned.received_at.day == 17
    assert "TARGET5" in cleaned.text
    assert "$5 OFF" in cleaned.text
    # Image alt text is kept (promo copy often lives there).
    assert "Target" in cleaned.text
    assert cleaned.html is not None


def test_clean_plaintext_email_and_boilerplate_removal():
    cleaned = clean_email(parse_eml((EMAILS_DIR / "chipotle_plaintext.eml").read_bytes()))
    assert cleaned.html is None
    assert "FREEGUAC" in cleaned.text
    assert "unsubscribe" not in cleaned.text.lower()


def test_clean_drops_hidden_elements_and_tracking_pixels():
    email = parse_eml((EMAILS_DIR / "nike_promo.eml").read_bytes())
    email.HtmlBody = (
        "<html><body>"
        "<div style='display:none'>HIDDEN_PREHEADER</div>"
        "<p hidden>ALSO_HIDDEN</p>"
        "<img src='t.gif' width='1' height='1' alt='TRACKER'>"
        "<img src='logo.png' alt='KEPT ALT TEXT'>"
        "<p>Visible   promo    text</p>"
        "</body></html>"
    )
    cleaned = clean_email(email)
    assert "HIDDEN_PREHEADER" not in cleaned.text
    assert "ALSO_HIDDEN" not in cleaned.text
    assert "TRACKER" not in cleaned.text
    assert "KEPT ALT TEXT" in cleaned.text
    # Whitespace collapsed.
    assert "Visible promo text" in cleaned.text


def test_clean_email_handles_iso_date():
    email = parse_eml((EMAILS_DIR / "nike_promo.eml").read_bytes())
    email.Date = "2026-10-18T10:00:00Z"
    cleaned = clean_email(email)
    assert cleaned.received_at.year == 2026
    assert cleaned.received_at.hour == 10
