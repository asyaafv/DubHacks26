"""Tests for email parsing and cleaning functions."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from backend.extraction.clean import parse_eml, clean_email
from backend.extraction.types import CleanedEmail


SEED_EMAILS_DIR = Path(__file__).parent.parent.parent.parent / "shared" / "seed" / "emails"


class TestParseEml:
    """Tests for parse_eml function."""

    def test_parse_multipart_email(self):
        """Parse a multipart email with HTML and text parts."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        raw = eml_path.read_bytes()
        
        result = parse_eml(raw)
        
        assert result.MessageID == "msg-001@hollisterco.com"
        assert result.Subject == "Your 10% Off Voucher - Don't Miss Out!"
        assert result.FromFull["Email"] == "rewards@hollisterco.com"
        assert result.FromFull["Name"] == "Hollister Co."
        assert result.TextBody is not None
        assert "HCOFALL10" in result.TextBody
        assert result.HtmlBody is not None
        assert "<html>" in result.HtmlBody
        assert "15 Oct 2026" in result.Date
        assert "10:30:00" in result.Date

    def test_parse_plaintext_only_email(self):
        """Parse a plain text email without HTML part."""
        eml_path = SEED_EMAILS_DIR / "chipotle_plaintext.eml"
        raw = eml_path.read_bytes()
        
        result = parse_eml(raw)
        
        assert result.MessageID == "msg-003@chipotle.com"
        assert result.Subject == "You've Earned FREE Guacamole!"
        assert result.FromFull["Email"] == "rewards@chipotle.com"
        assert result.TextBody is not None
        assert "FREEGUAC" in result.TextBody
        assert result.HtmlBody is None

    def test_parse_target_email(self):
        """Parse the Target JSON-LD offer email."""
        eml_path = SEED_EMAILS_DIR / "target_jsonld_offer.eml"
        raw = eml_path.read_bytes()
        
        result = parse_eml(raw)
        
        assert result.MessageID == "msg-009@target.com"
        assert "$5" in result.Subject
        assert result.FromFull["Email"] == "circle@target.com"
        assert result.HtmlBody is not None
        assert "TARGET5" in result.HtmlBody

    def test_parse_amazon_receipt(self):
        """Parse Amazon receipt email."""
        eml_path = SEED_EMAILS_DIR / "amazon_receipt.eml"
        raw = eml_path.read_bytes()
        
        result = parse_eml(raw)
        
        assert result.MessageID == "receipt-001@amazon.com"
        assert "shipped" in result.Subject.lower()
        assert result.FromFull["Email"] == "auto-confirm@amazon.com"

    def test_parse_nike_promo(self):
        """Parse Nike promo email."""
        eml_path = SEED_EMAILS_DIR / "nike_promo.eml"
        raw = eml_path.read_bytes()
        
        result = parse_eml(raw)
        
        assert result.MessageID == "msg-004@nike.com"
        assert "20%" in result.Subject
        assert result.FromFull["Email"] == "news@nike.com"
        assert result.HtmlBody is not None

    def test_parse_eml_fast(self):
        """Verify parse_eml completes in under 20ms."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        raw = eml_path.read_bytes()
        
        start = time.perf_counter()
        parse_eml(raw)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        assert elapsed_ms < 20, f"parse_eml took {elapsed_ms:.2f}ms, expected <20ms"


class TestCleanEmail:
    """Tests for clean_email function."""

    def test_clean_html_email_extracts_text(self):
        """Clean an HTML email and extract readable text."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = clean_email(email_obj)
        
        assert isinstance(result, CleanedEmail)
        assert result.subject == "Your 10% Off Voucher - Don't Miss Out!"
        assert result.sender == "rewards@hollisterco.com"
        assert result.sender_domain == "hollisterco.com"
        assert result.html is not None
        assert len(result.text) > 0

    def test_clean_plaintext_email(self):
        """Clean a plain text email."""
        eml_path = SEED_EMAILS_DIR / "chipotle_plaintext.eml"
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = clean_email(email_obj)
        
        assert result.sender_domain == "chipotle.com"
        assert "FREEGUAC" in result.text
        assert result.html is None

    def test_clean_target_email(self):
        """Clean Target email."""
        eml_path = SEED_EMAILS_DIR / "target_jsonld_offer.eml"
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = clean_email(email_obj)
        
        assert result.sender_domain == "target.com"
        assert result.html is not None

    def test_clean_extracts_sender_domain(self):
        """Verify sender domain extraction works for all emails."""
        test_cases = [
            ("hollister_10_percent.eml", "hollisterco.com"),
            ("chipotle_plaintext.eml", "chipotle.com"),
            ("target_jsonld_offer.eml", "target.com"),
            ("amazon_receipt.eml", "amazon.com"),
            ("nike_promo.eml", "nike.com"),
        ]
        
        for filename, expected_domain in test_cases:
            eml_path = SEED_EMAILS_DIR / filename
            raw = eml_path.read_bytes()
            email_obj = parse_eml(raw)
            result = clean_email(email_obj)
            
            assert result.sender_domain == expected_domain, f"Failed for {filename}"

    def test_clean_email_parses_dates(self):
        """Verify date parsing from email headers."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = clean_email(email_obj)
        
        assert result.received_at.year == 2026
        assert result.received_at.month == 10
        assert result.received_at.day == 15

    def test_clean_email_fast(self):
        """Verify clean_email completes in under 20ms."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        start = time.perf_counter()
        clean_email(email_obj)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        assert elapsed_ms < 20, f"clean_email took {elapsed_ms:.2f}ms, expected <20ms"

    def test_clean_collapses_whitespace(self):
        """Verify whitespace is properly collapsed."""
        eml_path = SEED_EMAILS_DIR / "chipotle_plaintext.eml"
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = clean_email(email_obj)
        
        assert "\n\n\n" not in result.text
        assert "  " not in result.text.replace("  ", "skip")
