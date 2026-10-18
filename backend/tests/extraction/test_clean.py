"""Tests for email parsing and cleaning."""
from __future__ import annotations

import pytest
from pathlib import Path
from datetime import datetime, timezone

from backend.extraction.clean import parse_eml, clean_email
from backend.extraction.types import CleanedEmail
from backend.app.schemas import InboundEmail


SEED_EMAILS_DIR = Path(__file__).parent.parent.parent.parent / "shared" / "seed" / "emails"


def get_all_eml_files() -> list[Path]:
    """Get all .eml files from seed directory."""
    if not SEED_EMAILS_DIR.exists():
        return []
    return list(SEED_EMAILS_DIR.glob("*.eml"))


@pytest.fixture
def eml_files() -> list[Path]:
    """Fixture providing all seed email files."""
    files = get_all_eml_files()
    if not files:
        pytest.skip("No .eml files found in shared/seed/emails/")
    return files


class TestParseEml:
    """Tests for parse_eml function."""
    
    def test_parse_hollister_multipart(self):
        """Test parsing multipart Hollister email."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        if not eml_path.exists():
            pytest.skip("hollister_10_percent.eml not found")
        
        raw = eml_path.read_bytes()
        result = parse_eml(raw)
        
        assert isinstance(result, InboundEmail)
        assert result.MessageID == "msg-001@hollisterco.com"
        assert result.Subject == "Your 10% Off Voucher - Don't Miss Out!"
        assert result.FromFull["Email"] == "rewards@hollisterco.com"
        assert result.FromFull["Name"] == "Hollister Co."
        assert result.TextBody is not None
        assert result.HtmlBody is not None
        assert "HCOFALL10" in result.TextBody
        assert "HCOFALL10" in result.HtmlBody
    
    def test_parse_chipotle_plaintext(self):
        """Test parsing plain text Chipotle email."""
        eml_path = SEED_EMAILS_DIR / "chipotle_plaintext.eml"
        if not eml_path.exists():
            pytest.skip("chipotle_plaintext.eml not found")
        
        raw = eml_path.read_bytes()
        result = parse_eml(raw)
        
        assert isinstance(result, InboundEmail)
        assert result.MessageID == "msg-003@chipotle.com"
        assert "FREE Guacamole" in result.Subject
        assert result.TextBody is not None
        assert result.HtmlBody is None
        assert "FREEGUAC" in result.TextBody
    
    def test_parse_target_jsonld(self):
        """Test parsing Target email with JSON-LD."""
        eml_path = SEED_EMAILS_DIR / "target_jsonld_offer.eml"
        if not eml_path.exists():
            pytest.skip("target_jsonld_offer.eml not found")
        
        raw = eml_path.read_bytes()
        result = parse_eml(raw)
        
        assert isinstance(result, InboundEmail)
        assert result.FromFull["Email"] == "circle@target.com"
        assert "$5 off" in result.Subject or "5 off" in result.Subject
        assert result.HtmlBody is not None
        assert "application/ld+json" in result.HtmlBody
    
    def test_parse_nike_promo(self):
        """Test parsing Nike promo email."""
        eml_path = SEED_EMAILS_DIR / "nike_promo.eml"
        if not eml_path.exists():
            pytest.skip("nike_promo.eml not found")
        
        raw = eml_path.read_bytes()
        result = parse_eml(raw)
        
        assert isinstance(result, InboundEmail)
        assert result.FromFull["Email"] == "news@nike.com"
        assert "20%" in result.Subject
        assert result.HtmlBody is not None
    
    def test_parse_amazon_receipt(self):
        """Test parsing Amazon receipt email."""
        eml_path = SEED_EMAILS_DIR / "amazon_receipt.eml"
        if not eml_path.exists():
            pytest.skip("amazon_receipt.eml not found")
        
        raw = eml_path.read_bytes()
        result = parse_eml(raw)
        
        assert isinstance(result, InboundEmail)
        assert result.FromFull["Email"] == "auto-confirm@amazon.com"
        assert "shipped" in result.Subject.lower()
    
    @pytest.mark.parametrize("eml_file", get_all_eml_files(), ids=lambda p: p.name)
    def test_parse_all_seed_emails(self, eml_file: Path):
        """Test that all seed emails can be parsed."""
        raw = eml_file.read_bytes()
        result = parse_eml(raw)
        
        assert isinstance(result, InboundEmail)
        assert result.MessageID
        assert result.Subject
        assert result.FromFull["Email"]
        assert result.TextBody or result.HtmlBody
    
    def test_parse_extracts_date(self):
        """Test that email date is extracted."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        if not eml_path.exists():
            pytest.skip("hollister_10_percent.eml not found")
        
        raw = eml_path.read_bytes()
        result = parse_eml(raw)
        
        assert result.Date
        assert "Oct" in result.Date or "15" in result.Date


class TestCleanEmail:
    """Tests for clean_email function."""
    
    def test_clean_hollister_html(self):
        """Test cleaning Hollister HTML email."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        if not eml_path.exists():
            pytest.skip("hollister_10_percent.eml not found")
        
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        result = clean_email(email_obj)
        
        assert isinstance(result, CleanedEmail)
        assert result.subject == "Your 10% Off Voucher - Don't Miss Out!"
        assert result.sender_domain == "hollisterco.com"
        assert "HCOFALL10" in result.text
        assert result.html is not None
        assert isinstance(result.received_at, datetime)
    
    def test_clean_chipotle_plaintext(self):
        """Test cleaning plain text email."""
        eml_path = SEED_EMAILS_DIR / "chipotle_plaintext.eml"
        if not eml_path.exists():
            pytest.skip("chipotle_plaintext.eml not found")
        
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        result = clean_email(email_obj)
        
        assert isinstance(result, CleanedEmail)
        assert result.sender_domain == "chipotle.com"
        assert "FREEGUAC" in result.text
        assert result.html is None
    
    def test_clean_extracts_sender_domain(self):
        """Test that sender domain is correctly extracted."""
        eml_path = SEED_EMAILS_DIR / "target_jsonld_offer.eml"
        if not eml_path.exists():
            pytest.skip("target_jsonld_offer.eml not found")
        
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        result = clean_email(email_obj)
        
        assert result.sender_domain == "target.com"
    
    def test_clean_parses_date(self):
        """Test that email date is parsed to datetime."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        if not eml_path.exists():
            pytest.skip("hollister_10_percent.eml not found")
        
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        result = clean_email(email_obj)
        
        assert isinstance(result.received_at, datetime)
        assert result.received_at.year == 2026
        assert result.received_at.month == 10
    
    def test_clean_removes_footer_boilerplate(self):
        """Test that footer boilerplate is removed from plain text."""
        eml_path = SEED_EMAILS_DIR / "chipotle_plaintext.eml"
        if not eml_path.exists():
            pytest.skip("chipotle_plaintext.eml not found")
        
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        result = clean_email(email_obj)
        
        assert "unsubscribe" not in result.text.lower()
    
    @pytest.mark.parametrize("eml_file", get_all_eml_files(), ids=lambda p: p.name)
    def test_clean_all_seed_emails(self, eml_file: Path):
        """Test that all seed emails can be cleaned."""
        raw = eml_file.read_bytes()
        email_obj = parse_eml(raw)
        result = clean_email(email_obj)
        
        assert isinstance(result, CleanedEmail)
        assert result.subject
        assert result.text or result.html
        assert result.sender_domain
        assert isinstance(result.received_at, datetime)
    
    def test_clean_collapses_whitespace(self):
        """Test that whitespace is properly collapsed."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        if not eml_path.exists():
            pytest.skip("hollister_10_percent.eml not found")
        
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        result = clean_email(email_obj)
        
        assert "    " not in result.text
        assert "\n\n\n\n" not in result.text


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_parse_empty_bytes(self):
        """Test parsing empty bytes returns an InboundEmail with empty fields."""
        result = parse_eml(b"")
        
        assert isinstance(result, InboundEmail)
        assert result.MessageID == ""
        assert result.Subject == ""
    
    def test_clean_email_fallback_date(self):
        """Test that missing date falls back to now."""
        email_obj = InboundEmail(
            MessageID="test-123",
            FromFull={"Email": "test@example.com", "Name": "Test"},
            ToFull=[{"Email": "demo@lapse.app", "Name": ""}],
            Subject="Test Subject",
            TextBody="Test body",
            Date="",
        )
        
        result = clean_email(email_obj)
        
        assert isinstance(result.received_at, datetime)
        now = datetime.now(timezone.utc)
        assert abs((result.received_at - now).total_seconds()) < 60
