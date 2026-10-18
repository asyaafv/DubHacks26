"""Tests for backend.extraction.markup against every seed .eml."""
from pathlib import Path

import pytest

from backend.extraction.clean import parse_eml
from backend.extraction.markup import extract_markup
from backend.extraction.types import FieldCandidates, FieldValue

EMAILS_DIR = Path(__file__).resolve().parents[3] / "shared" / "seed" / "emails"

# Which seed emails must yield markup fields vs None.
EXPECT_MARKUP = {
    "hollister_10_percent.eml": True,  # DiscountOffer
    "target_jsonld_offer.eml": True,  # Offer
    "nike_promo.eml": True,  # DiscountOffer
    "chipotle_plaintext.eml": False,  # plain text, no HTML
    "amazon_receipt.eml": False,  # Order markup only, not an offer
}


def _candidates_for(filename: str) -> FieldCandidates | None:
    email = parse_eml((EMAILS_DIR / filename).read_bytes())
    return extract_markup(email.HtmlBody)


@pytest.mark.parametrize("filename,expected", sorted(EXPECT_MARKUP.items()))
def test_every_seed_eml(filename, expected):
    result = _candidates_for(filename)
    if expected:
        assert isinstance(result, FieldCandidates)
    else:
        assert result is None


def test_all_fields_tagged_email_jsonld():
    for filename, expected in EXPECT_MARKUP.items():
        if not expected:
            continue
        c = _candidates_for(filename)
        for attr in ("merchant", "discount_value", "min_spend", "max_discount",
                     "expiry", "starts", "code", "stackable"):
            fv = getattr(c, attr)
            if fv is not None:
                assert isinstance(fv, FieldValue)
                assert fv.source == "email_jsonld"
                assert fv.confidence == 0.98


def test_hollister_discount_offer():
    c = _candidates_for("hollister_10_percent.eml")
    assert c.code.value == "HCOFALL10"
    assert c.discount_value.value == "10% off"
    assert c.min_spend.value == "50.00"
    assert c.merchant.value == "Hollister Co."
    assert c.starts.value == "2026-10-15T00:00:00-07:00"
    assert c.expiry.value == "2026-10-20T23:59:59-07:00"


def test_target_plain_offer():
    c = _candidates_for("target_jsonld_offer.eml")
    assert c.discount_value.value == "$5.00 off"
    assert c.min_spend.value == "25.00"
    assert c.merchant.value == "Target"
    assert c.expiry.value == "2026-10-19T23:59:59-07:00"
    assert c.code is None  # no discountCode in the Target markup


def test_nike_discount_offer_with_max_discount():
    c = _candidates_for("nike_promo.eml")
    assert c.code.value == "NIKE20FALL"
    assert c.discount_value.value == "20% off"
    assert c.min_spend.value == "100.00"
    assert c.max_discount.value == "50.00"
    assert c.merchant.value == "Nike"


def test_no_html_returns_none():
    assert extract_markup(None) is None
    assert extract_markup("") is None


def test_html_without_markup_returns_none():
    assert extract_markup("<html><body><p>20% off with code SAVE20</p></body></html>") is None


def test_gmail_promotion_card():
    html = """
    <html><head><script type="application/ld+json">
    {
      "@context": "http://schema.org/",
      "@type": "PromotionCard",
      "image": "https://www.example.com/hero.jpg",
      "price": "25.50",
      "discountValue": "25%",
      "url": "https://www.example.com/sale"
    }
    </script></head><body></body></html>
    """
    c = extract_markup(html)
    assert c is not None
    assert c.discount_value.value == "25% off"
    assert c.discount_value.source == "email_jsonld"
    assert c.discount_value.confidence == 0.98


def test_gmail_discount_offer_availability_fields():
    html = """
    <html><head><script type="application/ld+json">
    {
      "@context": "http://schema.org/",
      "@type": "DiscountOffer",
      "description": "20% off in store or online",
      "discountCode": "SUMMER20",
      "availabilityStarts": "2026-10-01T00:00:00-07:00",
      "availabilityEnds": "2026-10-30T23:59:59-07:00"
    }
    </script></head><body></body></html>
    """
    c = extract_markup(html)
    assert c.code.value == "SUMMER20"
    assert c.starts.value == "2026-10-01T00:00:00-07:00"
    assert c.expiry.value == "2026-10-30T23:59:59-07:00"


def test_microdata_offer():
    html = """
    <html><body>
    <div itemscope itemtype="https://schema.org/DiscountOffer">
      <span itemprop="discountCode">MICRO15</span>
      <meta itemprop="discount" content="15">
      <meta itemprop="discountType" content="Percent">
    </div>
    </body></html>
    """
    c = extract_markup(html)
    assert c is not None
    assert c.code.value == "MICRO15"
    assert c.discount_value.value == "15% off"
