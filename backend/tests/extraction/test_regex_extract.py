"""
Tests for regex_extract.py - regex-based field extraction.

Tests cover all pattern types:
- percent off, dollar off, points
- free item / BOGO
- minimum spend, max discount
- expiry dates
- promo codes
- stackability
- exclusions
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from backend.extraction.regex_extract import extract_fields_regex


SEED_EMAILS_DIR = Path(__file__).parent.parent.parent.parent / "shared" / "seed" / "emails"


class TestPercentOff:
    """Test percent off discount patterns."""

    @pytest.mark.parametrize(
        "text,expected_value",
        [
            ("Get 10% off your purchase", "10% off"),
            ("Save 20% on all items", "20% off"),
            ("15 percent off everything", "15% off"),
            ("get 25% today only", "25% off"),
            ("Enjoy 10% OFF your order", "10% off"),
            ("save 5% on your next order", "5% off"),
        ],
    )
    def test_percent_off_extraction(self, text: str, expected_value: str) -> None:
        result = extract_fields_regex(text)
        assert result.discount_value is not None
        assert result.discount_value.value == expected_value
        assert result.discount_value.source == "regex"
        assert 0.6 <= result.discount_value.confidence <= 0.85


class TestDollarOff:
    """Test dollar off discount patterns."""

    @pytest.mark.parametrize(
        "text,expected_value",
        [
            ("$10 off your order", "$10 off"),
            ("Save $25 on purchases over $100", "$25 off"),
            ("Get $5 off today", "$5 off"),
            ("$15.00 off your purchase", "$15.00 off"),
            ("$5 reward for members", "$5 off"),
        ],
    )
    def test_dollar_off_extraction(self, text: str, expected_value: str) -> None:
        result = extract_fields_regex(text)
        assert result.discount_value is not None
        assert result.discount_value.value == expected_value
        assert result.discount_value.source == "regex"
        assert 0.6 <= result.discount_value.confidence <= 0.85


class TestPoints:
    """Test points reward patterns."""

    @pytest.mark.parametrize(
        "text,expected_contains",
        [
            ("Earn 2x points on dining", "2x points"),
            ("500 bonus points for you", "500 points"),
            ("Earn 100 points with purchase", "100 points"),
            ("Get 3x points this week", "3x points"),
        ],
    )
    def test_points_extraction(self, text: str, expected_contains: str) -> None:
        result = extract_fields_regex(text)
        assert result.discount_value is not None
        assert expected_contains in result.discount_value.value
        assert result.discount_value.source == "regex"


class TestFreeItemBogo:
    """Test free item and BOGO patterns."""

    @pytest.mark.parametrize(
        "text",
        [
            "Free drink with purchase",
            "Get a free entree",
            "Buy one get one free",
            "BOGO on all items",
            "Free guacamole with any order",
        ],
    )
    def test_free_item_extraction(self, text: str) -> None:
        result = extract_fields_regex(text)
        assert result.discount_value is not None
        assert result.discount_value.source == "regex"


class TestMinimumSpend:
    """Test minimum spend patterns."""

    @pytest.mark.parametrize(
        "text,expected_value",
        [
            ("on orders of $50 or more", "$50"),
            ("spend $100 or more", "$100"),
            ("$50+ purchase required", "$50"),
            ("Minimum purchase: $25", "$25"),
            ("when you spend $75", "$75"),
            ("minimum purchase of $30", "$30"),
        ],
    )
    def test_min_spend_extraction(self, text: str, expected_value: str) -> None:
        result = extract_fields_regex(text)
        assert result.min_spend is not None
        assert result.min_spend.value == expected_value
        assert result.min_spend.source == "regex"
        assert 0.6 <= result.min_spend.confidence <= 0.85


class TestMaxDiscount:
    """Test maximum discount patterns."""

    @pytest.mark.parametrize(
        "text,expected_value",
        [
            ("up to $25 off", "$25"),
            ("Maximum discount: $50", "$50"),
            ("max discount: $100", "$100"),
            ("up to $15.00 savings", "$15.00"),
        ],
    )
    def test_max_discount_extraction(self, text: str, expected_value: str) -> None:
        result = extract_fields_regex(text)
        assert result.max_discount is not None
        assert result.max_discount.value == expected_value
        assert result.max_discount.source == "regex"


class TestExpiry:
    """Test expiry date patterns."""

    @pytest.mark.parametrize(
        "text,expected_contains",
        [
            ("expires Sunday", "Sunday"),
            ("Valid through 10/31", "10/31"),
            ("ends tonight", "tonight"),
            ("by Oct 31, 2026", "Oct 31, 2026"),
            ("Expires: October 20, 2026", "October 20, 2026"),
            ("valid until Friday", "Friday"),
            ("offer ends 11:59pm PT 10/20", "11:59pm PT 10/20"),
        ],
    )
    def test_expiry_extraction(self, text: str, expected_contains: str) -> None:
        result = extract_fields_regex(text)
        assert result.expiry is not None
        assert expected_contains.lower() in result.expiry.value.lower()
        assert result.expiry.source == "regex"


class TestPromoCode:
    """Test promo code patterns."""

    @pytest.mark.parametrize(
        "text,expected_code",
        [
            ("use code SAVE10 at checkout", "SAVE10"),
            ("Code: FALL25", "FALL25"),
            ("Promo code: SUMMER20", "SUMMER20"),
            ("coupon: DEAL50", "DEAL50"),
            ("use FREESHIP at checkout", "FREESHIP"),
            ("code HCOFALL10", "HCOFALL10"),
        ],
    )
    def test_code_extraction(self, text: str, expected_code: str) -> None:
        result = extract_fields_regex(text)
        assert result.code is not None
        assert result.code.value == expected_code
        assert result.code.source == "regex"


class TestStackability:
    """Test stackability patterns."""

    @pytest.mark.parametrize(
        "text,expected_stackable",
        [
            ("cannot be combined with other offers", "false"),
            ("can be combined with other discounts", "true"),
            ("Not valid with other coupons", "false"),
            ("This reward is stackable with other offers", "true"),
            ("One coupon per order", "false"),
            ("combine with other offers", "true"),
        ],
    )
    def test_stackability_extraction(self, text: str, expected_stackable: str) -> None:
        result = extract_fields_regex(text)
        assert result.stackable is not None
        assert result.stackable.value == expected_stackable
        assert result.stackable.source == "regex"


class TestExclusions:
    """Test exclusion patterns."""

    @pytest.mark.parametrize(
        "text,expected_exclusion_contains",
        [
            ("Excludes: Gift Cards, Clearance items", "Gift Cards"),
            ("Not valid on sale items", "sale items"),
            ("Exclusions: Electronics, Apple products", "Electronics"),
            ("does not include alcohol", "alcohol"),
        ],
    )
    def test_exclusions_extraction(self, text: str, expected_exclusion_contains: str) -> None:
        result = extract_fields_regex(text)
        assert len(result.exclusions) > 0
        assert any(expected_exclusion_contains.lower() in e.value.lower() for e in result.exclusions)


class TestHollisterEmail:
    """Test extraction from Hollister 10% off voucher email."""

    @pytest.fixture
    def hollister_text(self) -> str:
        """Load Hollister email text."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        content = eml_path.read_text()
        return content

    def test_hollister_discount_value(self, hollister_text: str) -> None:
        result = extract_fields_regex(hollister_text)
        assert result.discount_value is not None
        assert "10" in result.discount_value.value
        assert "%" in result.discount_value.value

    def test_hollister_code(self, hollister_text: str) -> None:
        result = extract_fields_regex(hollister_text)
        assert result.code is not None
        assert result.code.value == "HCOFALL10"

    def test_hollister_min_spend(self, hollister_text: str) -> None:
        result = extract_fields_regex(hollister_text)
        assert result.min_spend is not None
        assert "50" in result.min_spend.value

    def test_hollister_expiry(self, hollister_text: str) -> None:
        result = extract_fields_regex(hollister_text)
        assert result.expiry is not None

    def test_hollister_exclusions(self, hollister_text: str) -> None:
        result = extract_fields_regex(hollister_text)
        assert len(result.exclusions) > 0
        exclusion_text = " ".join(e.value.lower() for e in result.exclusions)
        assert "gift cards" in exclusion_text or "clearance" in exclusion_text


class TestChipotleEmail:
    """Test extraction from Chipotle plaintext email."""

    @pytest.fixture
    def chipotle_text(self) -> str:
        """Load Chipotle email text."""
        eml_path = SEED_EMAILS_DIR / "chipotle_plaintext.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        return eml_path.read_text()

    def test_chipotle_free_item(self, chipotle_text: str) -> None:
        result = extract_fields_regex(chipotle_text)
        assert result.discount_value is not None
        assert "free" in result.discount_value.value.lower()

    def test_chipotle_code(self, chipotle_text: str) -> None:
        result = extract_fields_regex(chipotle_text)
        assert result.code is not None
        assert result.code.value == "FREEGUAC"

    def test_chipotle_min_spend(self, chipotle_text: str) -> None:
        result = extract_fields_regex(chipotle_text)
        assert result.min_spend is not None
        assert "10" in result.min_spend.value

    def test_chipotle_stackable(self, chipotle_text: str) -> None:
        result = extract_fields_regex(chipotle_text)
        assert result.stackable is not None
        assert result.stackable.value == "true"


class TestNikeEmail:
    """Test extraction from Nike promo email."""

    @pytest.fixture
    def nike_text(self) -> str:
        """Load Nike email text."""
        eml_path = SEED_EMAILS_DIR / "nike_promo.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        return eml_path.read_text()

    def test_nike_discount_value(self, nike_text: str) -> None:
        result = extract_fields_regex(nike_text)
        assert result.discount_value is not None
        assert "20" in result.discount_value.value

    def test_nike_code(self, nike_text: str) -> None:
        result = extract_fields_regex(nike_text)
        assert result.code is not None
        assert result.code.value == "NIKE20FALL"

    def test_nike_min_spend(self, nike_text: str) -> None:
        result = extract_fields_regex(nike_text)
        assert result.min_spend is not None
        assert "100" in result.min_spend.value

    def test_nike_max_discount(self, nike_text: str) -> None:
        result = extract_fields_regex(nike_text)
        assert result.max_discount is not None
        assert "50" in result.max_discount.value

    def test_nike_exclusions(self, nike_text: str) -> None:
        result = extract_fields_regex(nike_text)
        assert len(result.exclusions) > 0


class TestTargetEmail:
    """Test extraction from Target JSON-LD email."""

    @pytest.fixture
    def target_text(self) -> str:
        """Load Target email text."""
        eml_path = SEED_EMAILS_DIR / "target_jsonld_offer.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        return eml_path.read_text()

    def test_target_discount_value(self, target_text: str) -> None:
        result = extract_fields_regex(target_text)
        assert result.discount_value is not None
        assert "5" in result.discount_value.value

    def test_target_code(self, target_text: str) -> None:
        result = extract_fields_regex(target_text)
        assert result.code is not None
        assert result.code.value == "TARGET5"

    def test_target_min_spend(self, target_text: str) -> None:
        result = extract_fields_regex(target_text)
        assert result.min_spend is not None
        assert "25" in result.min_spend.value

    def test_target_stackable(self, target_text: str) -> None:
        result = extract_fields_regex(target_text)
        assert result.stackable is not None
        assert result.stackable.value == "true"


class TestPerformance:
    """Test that extraction completes quickly."""

    def test_extraction_under_5ms(self) -> None:
        """Extraction should complete in under 5ms for typical email text."""
        text = """
        Hi there!

        Thanks for being a loyal customer. Here's a special reward just for you:

        20% OFF YOUR NEXT PURCHASE
        Code: SAVE20NOW
        Minimum Purchase: $50
        Valid through: October 31, 2026

        Excludes: Gift Cards, Clearance items

        Cannot be combined with other offers.

        Shop now at example.com
        """

        iterations = 100
        start = time.perf_counter()
        for _ in range(iterations):
            extract_fields_regex(text)
        elapsed = time.perf_counter() - start

        avg_ms = (elapsed / iterations) * 1000
        assert avg_ms < 5, f"Extraction took {avg_ms:.2f}ms on average, expected < 5ms"


class TestCombinedPatterns:
    """Test extraction of multiple fields from combined text."""

    def test_full_offer_extraction(self) -> None:
        """Test extracting all fields from a complete offer."""
        text = """
        $10 off $50+ purchase
        Use code: FALL10
        Expires Sunday
        Cannot be combined with other offers
        Excludes: sale items
        """

        result = extract_fields_regex(text)

        assert result.discount_value is not None
        assert "$10" in result.discount_value.value
        assert result.min_spend is not None
        assert "50" in result.min_spend.value
        assert result.code is not None
        assert result.code.value == "FALL10"
        assert result.expiry is not None
        assert result.stackable is not None
        assert result.stackable.value == "false"
        assert len(result.exclusions) > 0


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_text(self) -> None:
        """Empty text should return empty candidates."""
        result = extract_fields_regex("")
        assert result.discount_value is None
        assert result.code is None
        assert result.min_spend is None

    def test_no_offers(self) -> None:
        """Text with no offers should return empty candidates."""
        result = extract_fields_regex("Hello, thank you for shopping with us!")
        assert result.discount_value is None
        assert result.code is None

    def test_multiple_codes_takes_first(self) -> None:
        """Multiple codes should return the first one found."""
        result = extract_fields_regex("Use code FIRST123 or code SECOND456")
        assert result.code is not None
        assert result.code.value == "FIRST123"

    def test_case_insensitivity(self) -> None:
        """Patterns should be case-insensitive."""
        result = extract_fields_regex("CODE: lowercase123")
        assert result.code is not None
        assert result.code.value == "LOWERCASE123"
