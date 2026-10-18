"""Tests for markup extraction functions."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from backend.extraction.clean import parse_eml
from backend.extraction.markup import extract_markup
from backend.extraction.types import FieldCandidates, FieldValue


SEED_EMAILS_DIR = Path(__file__).parent.parent.parent.parent / "shared" / "seed" / "emails"


class TestExtractMarkup:
    """Tests for extract_markup function."""

    def test_extract_target_jsonld_offer(self):
        """Target email with Offer JSON-LD should yield markup."""
        eml_path = SEED_EMAILS_DIR / "target_jsonld_offer.eml"
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = extract_markup(email_obj.HtmlBody)
        
        assert result is not None
        assert isinstance(result, FieldCandidates)
        assert result.discount_value is not None
        assert result.discount_value.source == "email_jsonld"
        assert result.discount_value.confidence >= 0.95
        assert result.min_spend is not None
        assert result.min_spend.value == "$25.00"
        assert result.merchant is not None
        assert result.merchant.value == "Target"
        assert result.expiry is not None
        assert result.starts is not None

    def test_extract_hollister_discount_offer(self):
        """Hollister email with DiscountOffer JSON-LD should yield markup."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = extract_markup(email_obj.HtmlBody)
        
        assert result is not None
        assert isinstance(result, FieldCandidates)
        assert result.code is not None
        assert result.code.value == "HCOFALL10"
        assert result.code.source == "email_jsonld"
        assert result.code.confidence >= 0.95
        assert result.discount_value is not None
        assert "10" in result.discount_value.value
        assert result.merchant is not None
        assert result.merchant.value == "Hollister Co."
        assert result.min_spend is not None
        assert result.min_spend.value == "$50.00"

    def test_extract_nike_discount_offer(self):
        """Nike email with DiscountOffer JSON-LD should yield markup."""
        eml_path = SEED_EMAILS_DIR / "nike_promo.eml"
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = extract_markup(email_obj.HtmlBody)
        
        assert result is not None
        assert result.code is not None
        assert result.code.value == "NIKE20FALL"
        assert result.discount_value is not None
        assert "20" in result.discount_value.value
        assert result.merchant is not None
        assert result.merchant.value == "Nike"
        assert result.min_spend is not None
        assert result.min_spend.value == "$100.00"
        assert result.max_discount is not None
        assert result.max_discount.value == "$50.00"

    def test_amazon_receipt_returns_none(self):
        """Amazon receipt email (Order type) should return None."""
        eml_path = SEED_EMAILS_DIR / "amazon_receipt.eml"
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = extract_markup(email_obj.HtmlBody)
        
        assert result is None

    def test_chipotle_plaintext_returns_none(self):
        """Chipotle plaintext email (no HTML) should return None."""
        eml_path = SEED_EMAILS_DIR / "chipotle_plaintext.eml"
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = extract_markup(email_obj.HtmlBody)
        
        assert result is None

    def test_none_html_returns_none(self):
        """None HTML input should return None."""
        result = extract_markup(None)
        assert result is None

    def test_empty_html_returns_none(self):
        """Empty HTML input should return None."""
        result = extract_markup("")
        assert result is None

    def test_html_without_markup_returns_none(self):
        """HTML without schema.org markup should return None."""
        html = "<html><body><p>Hello world</p></body></html>"
        result = extract_markup(html)
        assert result is None

    def test_field_candidates_have_correct_source(self):
        """All extracted fields should have source='email_jsonld'."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = extract_markup(email_obj.HtmlBody)
        
        assert result is not None
        for field_name in ["merchant", "discount_value", "min_spend", "expiry", "starts", "code"]:
            field = getattr(result, field_name, None)
            if field is not None:
                assert isinstance(field, FieldValue)
                assert field.source == "email_jsonld"

    def test_confidence_in_valid_range(self):
        """All confidence scores should be between 0.95 and 0.99."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        
        result = extract_markup(email_obj.HtmlBody)
        
        assert result is not None
        for field_name in ["merchant", "discount_value", "min_spend", "expiry", "starts", "code"]:
            field = getattr(result, field_name, None)
            if field is not None:
                assert 0.95 <= field.confidence <= 0.99, f"{field_name} confidence out of range"

    def test_extract_markup_fast(self):
        """Verify extract_markup completes in under 20ms."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        raw = eml_path.read_bytes()
        email_obj = parse_eml(raw)
        html = email_obj.HtmlBody
        
        start = time.perf_counter()
        extract_markup(html)
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        assert elapsed_ms < 20, f"extract_markup took {elapsed_ms:.2f}ms, expected <20ms"

    def test_no_ml_dependency(self):
        """Verify importing markup extraction doesn't pull in ML models.

        Runs in a subprocess: checking sys.modules in-process is order-dependent
        once other test files legitimately import torch/setfit/gliner.
        """
        import subprocess
        import sys

        code = (
            "import sys; import backend.extraction.markup; "
            "ml = [m for m in ('torch', 'tensorflow', 'transformers', 'setfit', 'gliner', 'gliner2') "
            "if m in sys.modules]; "
            "assert not ml, f'ML modules loaded: {ml}'"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).resolve().parents[3]),
        )
        assert result.returncode == 0, result.stderr
