"""Tests for JSON-LD and microdata markup extraction."""
from __future__ import annotations

import pytest
from pathlib import Path

from backend.extraction.markup import extract_markup
from backend.extraction.types import FieldCandidates, FieldValue
from backend.extraction.clean import parse_eml


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


try:
    import extruct
    EXTRUCT_AVAILABLE = True
except ImportError:
    EXTRUCT_AVAILABLE = False


class TestExtractMarkup:
    """Tests for extract_markup function."""
    
    @pytest.mark.skipif(not EXTRUCT_AVAILABLE, reason="extruct not installed")
    def test_target_jsonld_has_code_and_expiry(self):
        """Test that target_jsonld_offer.eml yields markup with code and expiry.
        
        This is a critical test case specified in the task requirements.
        """
        eml_path = SEED_EMAILS_DIR / "target_jsonld_offer.eml"
        if not eml_path.exists():
            pytest.skip("target_jsonld_offer.eml not found")
        
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = extract_markup(email_obj.HtmlBody)
        
        assert result is not None, "target_jsonld_offer.eml must yield markup"
        assert isinstance(result, FieldCandidates)
        
        assert result.expiry is not None, "Must extract expiry from target_jsonld_offer.eml"
        assert result.expiry.source == "email_jsonld"
        assert result.expiry.confidence == 0.98
        assert "2026-10-19" in result.expiry.value or "19" in result.expiry.value
        
        assert result.discount_value is not None, "Must extract discount value"
        assert "5" in result.discount_value.value
        
        assert result.min_spend is not None, "Must extract min spend"
        assert "25" in result.min_spend.value
    
    @pytest.mark.skipif(not EXTRUCT_AVAILABLE, reason="extruct not installed")
    def test_hollister_jsonld_discount_offer(self):
        """Test extraction from Hollister DiscountOffer JSON-LD."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        if not eml_path.exists():
            pytest.skip("hollister_10_percent.eml not found")
        
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = extract_markup(email_obj.HtmlBody)
        
        assert result is not None
        assert isinstance(result, FieldCandidates)
        
        assert result.code is not None
        assert result.code.value == "HCOFALL10"
        assert result.code.source == "email_jsonld"
        assert result.code.confidence == 0.98
        
        assert result.discount_value is not None
        assert "10" in result.discount_value.value
        
        assert result.expiry is not None
        assert "2026-10-20" in result.expiry.value
        
        assert result.min_spend is not None
        assert "50" in result.min_spend.value
        
        assert result.merchant is not None
        assert "Hollister" in result.merchant.value
    
    @pytest.mark.skipif(not EXTRUCT_AVAILABLE, reason="extruct not installed")
    def test_nike_jsonld_discount_offer(self):
        """Test extraction from Nike DiscountOffer JSON-LD."""
        eml_path = SEED_EMAILS_DIR / "nike_promo.eml"
        if not eml_path.exists():
            pytest.skip("nike_promo.eml not found")
        
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = extract_markup(email_obj.HtmlBody)
        
        assert result is not None
        assert isinstance(result, FieldCandidates)
        
        assert result.code is not None
        assert result.code.value == "NIKE20FALL"
        
        assert result.discount_value is not None
        assert "20" in result.discount_value.value
        
        assert result.expiry is not None
        
        assert result.min_spend is not None
        assert "100" in result.min_spend.value
        
        assert result.max_discount is not None
        assert "50" in result.max_discount.value
        
        assert result.merchant is not None
        assert "Nike" in result.merchant.value
    
    @pytest.mark.skipif(not EXTRUCT_AVAILABLE, reason="extruct not installed")
    def test_chipotle_no_jsonld(self):
        """Test that plain text email with no JSON-LD returns None."""
        eml_path = SEED_EMAILS_DIR / "chipotle_plaintext.eml"
        if not eml_path.exists():
            pytest.skip("chipotle_plaintext.eml not found")
        
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = extract_markup(email_obj.HtmlBody)
        
        assert result is None
    
    @pytest.mark.skipif(not EXTRUCT_AVAILABLE, reason="extruct not installed")
    def test_amazon_receipt_not_discount(self):
        """Test that Amazon receipt (Order type) is not extracted as discount."""
        eml_path = SEED_EMAILS_DIR / "amazon_receipt.eml"
        if not eml_path.exists():
            pytest.skip("amazon_receipt.eml not found")
        
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = extract_markup(email_obj.HtmlBody)
        
        assert result is None
    
    def test_extract_none_html(self):
        """Test that None HTML returns None."""
        result = extract_markup(None)
        assert result is None
    
    def test_extract_empty_html(self):
        """Test that empty HTML returns None."""
        result = extract_markup("")
        assert result is None
    
    @pytest.mark.skipif(not EXTRUCT_AVAILABLE, reason="extruct not installed")
    def test_extract_html_no_jsonld(self):
        """Test that HTML without JSON-LD returns None."""
        html = "<html><body><p>Hello World</p></body></html>"
        result = extract_markup(html)
        assert result is None
    
    @pytest.mark.skipif(not EXTRUCT_AVAILABLE, reason="extruct not installed")
    @pytest.mark.parametrize("eml_file", get_all_eml_files(), ids=lambda p: p.name)
    def test_extract_all_seed_emails(self, eml_file: Path):
        """Test extract_markup on all seed emails without crashing."""
        raw = eml_file.read_bytes()
        email_obj = parse_eml(raw)
        
        result = extract_markup(email_obj.HtmlBody)
        
        assert result is None or isinstance(result, FieldCandidates)
        
        if result is not None:
            if result.code:
                assert isinstance(result.code, FieldValue)
                assert result.code.source == "email_jsonld"
                assert result.code.confidence == 0.98
            if result.expiry:
                assert isinstance(result.expiry, FieldValue)
                assert result.expiry.source == "email_jsonld"


class TestFieldValue:
    """Tests for FieldValue structure."""
    
    @pytest.mark.skipif(not EXTRUCT_AVAILABLE, reason="extruct not installed")
    def test_field_value_structure(self):
        """Test that FieldValue has correct structure."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        if not eml_path.exists():
            pytest.skip("hollister_10_percent.eml not found")
        
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = extract_markup(email_obj.HtmlBody)
        
        assert result is not None
        assert result.code is not None
        
        assert hasattr(result.code, "value")
        assert hasattr(result.code, "confidence")
        assert hasattr(result.code, "source")
        
        assert isinstance(result.code.value, str)
        assert isinstance(result.code.confidence, float)
        assert isinstance(result.code.source, str)
        
        assert 0.0 <= result.code.confidence <= 1.0
        assert result.code.source == "email_jsonld"


class TestJsonLdTypes:
    """Test different JSON-LD schema types."""
    
    @pytest.mark.skipif(not EXTRUCT_AVAILABLE, reason="extruct not installed")
    def test_discount_offer_type(self):
        """Test DiscountOffer type extraction."""
        html = """
        <html>
        <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "DiscountOffer",
          "name": "Test Offer",
          "discountCode": "TEST123",
          "discount": "20",
          "discountType": "Percent",
          "validThrough": "2026-12-31"
        }
        </script>
        </head>
        <body></body>
        </html>
        """
        
        result = extract_markup(html)
        
        assert result is not None
        assert result.code is not None
        assert result.code.value == "TEST123"
        assert result.discount_value is not None
        assert "20" in result.discount_value.value
        assert result.expiry is not None
    
    @pytest.mark.skipif(not EXTRUCT_AVAILABLE, reason="extruct not installed")
    def test_offer_type_with_price_spec(self):
        """Test Offer type with priceSpecification."""
        html = """
        <html>
        <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "Offer",
          "name": "Test Offer",
          "priceSpecification": {
            "@type": "PriceSpecification",
            "price": "10.00",
            "priceCurrency": "USD"
          },
          "validThrough": "2026-12-31",
          "offeredBy": {
            "@type": "Organization",
            "name": "Test Store"
          }
        }
        </script>
        </head>
        <body></body>
        </html>
        """
        
        result = extract_markup(html)
        
        assert result is not None
        assert result.discount_value is not None
        assert "10" in result.discount_value.value
        assert result.merchant is not None
        assert "Test Store" in result.merchant.value
    
    @pytest.mark.skipif(not EXTRUCT_AVAILABLE, reason="extruct not installed")
    def test_eligible_transaction_volume(self):
        """Test extraction of eligibleTransactionVolume (min spend)."""
        html = """
        <html>
        <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "Offer",
          "name": "Test Offer",
          "eligibleTransactionVolume": {
            "@type": "PriceSpecification",
            "minPrice": "50.00",
            "priceCurrency": "USD"
          },
          "validThrough": "2026-12-31"
        }
        </script>
        </head>
        <body></body>
        </html>
        """
        
        result = extract_markup(html)
        
        assert result is not None
        assert result.min_spend is not None
        assert "50" in result.min_spend.value
