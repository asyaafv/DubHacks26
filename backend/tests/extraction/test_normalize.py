"""
Tests for normalize.py - field normalization using dateparser and price-parser.

Tests cover:
- Discount value parsing (percent off, dollar off, points, free item, BOGO)
- Price/spend amount parsing
- Date parsing relative to email date
- Stackability parsing
- Exclusions handling
- Field confidence calculation
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from backend.extraction.normalize import normalize
from backend.extraction.regex_extract import extract_fields_regex
from backend.extraction.types import FieldCandidates, FieldValue


SEED_EMAILS_DIR = Path(__file__).parent.parent.parent.parent / "shared" / "seed" / "emails"


class TestDiscountValueParsing:
    """Test parsing of discount values into kind and value."""

    @pytest.fixture
    def email_date(self) -> datetime:
        return datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_percent_off_parsing(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            discount_value=FieldValue(value="10% off", confidence=0.8, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["kind"] == "percent_off"
        assert result["value"] == Decimal("10")
        assert result["currency"] == "USD"
        assert "value" in result["field_confidence"]

    def test_dollar_off_parsing(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            discount_value=FieldValue(value="$25 off", confidence=0.8, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["kind"] == "amount_off"
        assert result["value"] == Decimal("25")
        assert result["currency"] == "USD"

    def test_decimal_dollar_off(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            discount_value=FieldValue(value="$15.50 off", confidence=0.8, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["kind"] == "amount_off"
        assert result["value"] == Decimal("15.50")

    def test_points_parsing(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            discount_value=FieldValue(value="500 points", confidence=0.75, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["kind"] == "points"
        assert result["value"] == Decimal("500")

    def test_points_multiplier_parsing(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            discount_value=FieldValue(value="2x points", confidence=0.75, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["kind"] == "points"
        assert result["value"] == Decimal("2")

    def test_free_item_parsing(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            discount_value=FieldValue(value="Free drink", confidence=0.7, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["kind"] == "free_item"
        assert result["value"] == Decimal("1")

    def test_bogo_parsing(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            discount_value=FieldValue(value="Buy one get one free", confidence=0.8, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["kind"] == "bogo"
        assert result["value"] == Decimal("1")


class TestPriceParsing:
    """Test parsing of price/spend amounts."""

    @pytest.fixture
    def email_date(self) -> datetime:
        return datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_min_spend_parsing(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            min_spend=FieldValue(value="$50", confidence=0.8, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["min_spend"] == Decimal("50")
        assert "min_spend" in result["field_confidence"]

    def test_max_discount_parsing(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            max_discount=FieldValue(value="$25", confidence=0.8, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["max_discount"] == Decimal("25")

    def test_decimal_price_parsing(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            min_spend=FieldValue(value="$99.99", confidence=0.8, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["min_spend"] == Decimal("99.99")


class TestDateParsing:
    """Test date parsing relative to email date."""

    @pytest.fixture
    def email_date(self) -> datetime:
        return datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_specific_date_parsing(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            expiry=FieldValue(value="October 20, 2026", confidence=0.8, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["expires_at"] is not None
        assert result["expires_at"].year == 2026
        assert result["expires_at"].month == 10
        assert result["expires_at"].day == 20
        assert result["expires_at"].hour == 23
        assert result["expires_at"].minute == 59

    def test_weekday_parsing_prefers_future(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            expiry=FieldValue(value="Sunday", confidence=0.8, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["expires_at"] is not None
        assert result["expires_at"] >= email_date
        assert result["expires_at"].weekday() == 6

    def test_tonight_parsing(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            expiry=FieldValue(value="tonight", confidence=0.75, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["expires_at"] is not None
        assert result["expires_at"].date() == email_date.date()
        assert result["expires_at"].hour == 23
        assert result["expires_at"].minute == 59
        assert result["expires_at"].second == 59

    def test_today_parsing(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            expiry=FieldValue(value="today", confidence=0.75, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["expires_at"] is not None
        assert result["expires_at"].date() == email_date.date()
        assert result["expires_at"].hour == 23

    def test_short_date_parsing(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            expiry=FieldValue(value="10/31", confidence=0.8, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["expires_at"] is not None
        assert result["expires_at"].month == 10
        assert result["expires_at"].day == 31


class TestStackability:
    """Test stackability field parsing."""

    @pytest.fixture
    def email_date(self) -> datetime:
        return datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_stackable_true(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            stackable=FieldValue(value="true", confidence=0.8, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["stackable"] is True

    def test_stackable_false(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            stackable=FieldValue(value="false", confidence=0.8, source="regex")
        )
        result = normalize(candidates, email_date)

        assert result["stackable"] is False

    def test_stackable_default_false(self, email_date: datetime) -> None:
        candidates = FieldCandidates()
        result = normalize(candidates, email_date)

        assert result["stackable"] is False


class TestExclusions:
    """Test exclusions handling."""

    @pytest.fixture
    def email_date(self) -> datetime:
        return datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_exclusions_parsing(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            exclusions=[
                FieldValue(value="Gift Cards", confidence=0.75, source="regex"),
                FieldValue(value="Clearance items", confidence=0.75, source="regex"),
            ]
        )
        result = normalize(candidates, email_date)

        assert "exclusions" in result
        assert len(result["exclusions"]) == 2
        assert "Gift Cards" in result["exclusions"]
        assert "Clearance items" in result["exclusions"]
        assert "exclusions" in result["field_confidence"]


class TestFieldConfidence:
    """Test field confidence calculation."""

    @pytest.fixture
    def email_date(self) -> datetime:
        return datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_confidence_included(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            discount_value=FieldValue(value="10% off", confidence=0.8, source="regex"),
            code=FieldValue(value="SAVE10", confidence=0.8, source="regex"),
            min_spend=FieldValue(value="$50", confidence=0.75, source="regex"),
        )
        result = normalize(candidates, email_date)

        assert "field_confidence" in result
        assert "value" in result["field_confidence"]
        assert "code" in result["field_confidence"]
        assert "min_spend" in result["field_confidence"]

    def test_confidence_reflects_input(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            discount_value=FieldValue(value="10% off", confidence=0.8, source="regex"),
        )
        result = normalize(candidates, email_date)

        assert result["field_confidence"]["value"] == pytest.approx(0.8, rel=0.01)


class TestHollisterEmailNormalization:
    """Test full normalization of Hollister email."""

    @pytest.fixture
    def email_date(self) -> datetime:
        return datetime(2026, 10, 15, 10, 30, 0, tzinfo=timezone.utc)

    @pytest.fixture
    def hollister_candidates(self) -> FieldCandidates:
        """Load and extract from Hollister email."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        text = eml_path.read_text()
        return extract_fields_regex(text)

    def test_hollister_kind(self, hollister_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(hollister_candidates, email_date)
        assert result["kind"] == "percent_off"

    def test_hollister_value(self, hollister_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(hollister_candidates, email_date)
        assert result["value"] == Decimal("10")

    def test_hollister_code(self, hollister_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(hollister_candidates, email_date)
        assert result["code"] == "HCOFALL10"

    def test_hollister_min_spend(self, hollister_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(hollister_candidates, email_date)
        assert result["min_spend"] == Decimal("50")

    def test_hollister_expiry(self, hollister_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(hollister_candidates, email_date)
        assert "expires_at" in result
        assert result["expires_at"].month == 10
        assert result["expires_at"].day == 20


class TestDollarOffWithExpiryAndMinSpend:
    """Test '$10 off $50+ expires Sunday' scenario with fixed email date."""

    @pytest.fixture
    def email_date(self) -> datetime:
        return datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_combined_extraction_and_normalization(self, email_date: datetime) -> None:
        text = "$10 off $50+ expires Sunday"
        candidates = extract_fields_regex(text)
        result = normalize(candidates, email_date)

        assert result["kind"] == "amount_off"
        assert result["value"] == Decimal("10")
        assert result["min_spend"] == Decimal("50")

        assert "expires_at" in result
        expires_at = result["expires_at"]
        assert expires_at.weekday() == 6
        assert expires_at >= email_date


class TestChipotleEmailNormalization:
    """Test full normalization of Chipotle email."""

    @pytest.fixture
    def email_date(self) -> datetime:
        return datetime(2026, 10, 12, 9, 15, 0, tzinfo=timezone.utc)

    @pytest.fixture
    def chipotle_candidates(self) -> FieldCandidates:
        """Load and extract from Chipotle email."""
        eml_path = SEED_EMAILS_DIR / "chipotle_plaintext.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        text = eml_path.read_text()
        return extract_fields_regex(text)

    def test_chipotle_kind(self, chipotle_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(chipotle_candidates, email_date)
        assert result["kind"] == "free_item"

    def test_chipotle_stackable(self, chipotle_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(chipotle_candidates, email_date)
        assert result["stackable"] is True

    def test_chipotle_code(self, chipotle_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(chipotle_candidates, email_date)
        assert result["code"] == "FREEGUAC"


class TestNikeEmailNormalization:
    """Test full normalization of Nike email."""

    @pytest.fixture
    def email_date(self) -> datetime:
        return datetime(2026, 10, 8, 16, 45, 0, tzinfo=timezone.utc)

    @pytest.fixture
    def nike_candidates(self) -> FieldCandidates:
        """Load and extract from Nike email."""
        eml_path = SEED_EMAILS_DIR / "nike_promo.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        text = eml_path.read_text()
        return extract_fields_regex(text)

    def test_nike_kind(self, nike_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(nike_candidates, email_date)
        assert result["kind"] == "percent_off"

    def test_nike_value(self, nike_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(nike_candidates, email_date)
        assert result["value"] == Decimal("20")

    def test_nike_min_spend(self, nike_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(nike_candidates, email_date)
        assert result["min_spend"] == Decimal("100")

    def test_nike_max_discount(self, nike_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(nike_candidates, email_date)
        assert result["max_discount"] == Decimal("50")

    def test_nike_code(self, nike_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(nike_candidates, email_date)
        assert result["code"] == "NIKE20FALL"


class TestTargetEmailNormalization:
    """Test full normalization of Target email."""

    @pytest.fixture
    def email_date(self) -> datetime:
        return datetime(2026, 10, 17, 11, 30, 0, tzinfo=timezone.utc)

    @pytest.fixture
    def target_candidates(self) -> FieldCandidates:
        """Load and extract from Target email."""
        eml_path = SEED_EMAILS_DIR / "target_jsonld_offer.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        text = eml_path.read_text()
        return extract_fields_regex(text)

    def test_target_kind(self, target_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(target_candidates, email_date)
        assert result["kind"] == "amount_off"

    def test_target_value(self, target_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(target_candidates, email_date)
        assert result["value"] == Decimal("5")

    def test_target_min_spend(self, target_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(target_candidates, email_date)
        assert result["min_spend"] == Decimal("25")

    def test_target_stackable(self, target_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(target_candidates, email_date)
        assert result["stackable"] is True

    def test_target_code(self, target_candidates: FieldCandidates, email_date: datetime) -> None:
        result = normalize(target_candidates, email_date)
        assert result["code"] == "TARGET5"


class TestMissingFields:
    """Test that missing fields are omitted rather than guessed."""

    @pytest.fixture
    def email_date(self) -> datetime:
        return datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_empty_candidates(self, email_date: datetime) -> None:
        candidates = FieldCandidates()
        result = normalize(candidates, email_date)

        assert "kind" not in result
        assert "value" not in result
        assert "min_spend" not in result
        assert "max_discount" not in result
        assert "code" not in result
        assert "expires_at" not in result
        assert "starts_at" not in result
        assert result["stackable"] is False

    def test_partial_candidates(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            code=FieldValue(value="SAVE10", confidence=0.8, source="regex")
        )
        result = normalize(candidates, email_date)

        assert "kind" not in result
        assert "value" not in result
        assert result["code"] == "SAVE10"
        assert "code" in result["field_confidence"]


class TestAuditRegressions:
    """Regressions found by the extraction audit (Ulta/Sephora points emails)."""

    @pytest.fixture
    def email_date(self) -> datetime:
        return datetime(2026, 10, 18, 12, 0, 0, tzinfo=timezone.utc)

    def test_bonus_points_phrase_parses(self, email_date: datetime) -> None:
        # GLiNER returns the full phrase "500 bonus points"; it must still
        # normalize to a points reward.
        candidates = FieldCandidates(
            discount_value=FieldValue(value="500 bonus points", confidence=0.51, source="gliner")
        )
        result = normalize(candidates, email_date)
        assert result["kind"] == "points"
        assert result["value"] == Decimal("500")

    def test_extra_points_phrase_parses(self, email_date: datetime) -> None:
        candidates = FieldCandidates(
            discount_value=FieldValue(value="250 extra points", confidence=0.6, source="gliner")
        )
        result = normalize(candidates, email_date)
        assert result["kind"] == "points"
        assert result["value"] == Decimal("250")

    def test_merge_skips_bare_year_expiry(self) -> None:
        # A bare year from GLiNER must not out-prioritize a real regex date.
        from backend.extraction.normalize import merge_candidates

        gliner = FieldCandidates(
            expiry=FieldValue(value="2026", confidence=0.75, source="gliner")
        )
        regex = FieldCandidates(
            expiry=FieldValue(value="November 1", confidence=0.8, source="regex")
        )
        merged = merge_candidates(gliner, regex)
        assert merged.expiry is not None
        assert merged.expiry.value == "November 1"
        assert merged.expiry.source == "regex"
