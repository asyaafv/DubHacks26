"""Extract structured markup from HTML emails.

Uses extruct to find Google Gmail Promotions annotations:
- schema.org DiscountOffer
- schema.org PromotionCard (GmailPromotionCard)
- schema.org Offer with discount properties
"""
from __future__ import annotations

from typing import Any

import extruct
from w3lib.html import get_base_url

from backend.extraction.types import FieldCandidates, FieldValue


DISCOUNT_TYPES = {"DiscountOffer", "GmailPromotionCard", "PromotionCard"}
OFFER_TYPES = {"Offer"}

SOURCE = "email_jsonld"
HIGH_CONFIDENCE = 0.99
MEDIUM_CONFIDENCE = 0.97
BASE_CONFIDENCE = 0.95


def extract_markup(html: str | None) -> FieldCandidates | None:
    """Extract Gmail Promotions markup from HTML.
    
    Looks for schema.org DiscountOffer, PromotionCard, and Offer types
    containing discount/promotion information.
    
    Returns FieldCandidates with source='email_jsonld' and confidence 0.95-0.99,
    or None if no relevant markup is found.
    """
    if not html:
        return None
    
    try:
        data = extruct.extract(
            html,
            base_url=get_base_url(html, ""),
            syntaxes=["json-ld", "microdata"],
            uniform=True,
        )
    except Exception:
        return None
    
    items = data.get("json-ld", []) + data.get("microdata", [])
    
    if not items:
        return None
    
    for item in items:
        item_type = _get_type(item)
        
        if item_type in DISCOUNT_TYPES:
            return _parse_discount_offer(item)
        
        if item_type in OFFER_TYPES:
            if _is_discount_offer(item):
                return _parse_offer(item)
    
    return None


def _get_type(item: dict[str, Any]) -> str:
    """Extract the @type from a schema.org item."""
    item_type = item.get("@type", "")
    if isinstance(item_type, list):
        item_type = item_type[0] if item_type else ""
    return item_type


def _is_discount_offer(item: dict[str, Any]) -> bool:
    """Check if an Offer represents a discount/promotion."""
    if item.get("discountCode"):
        return True
    if item.get("discount"):
        return True
    
    price_spec = item.get("priceSpecification", {})
    if isinstance(price_spec, dict) and price_spec.get("price"):
        return True
    
    eligible_vol = item.get("eligibleTransactionVolume", {})
    if isinstance(eligible_vol, dict) and eligible_vol.get("minPrice"):
        return True
    
    return False


def _parse_discount_offer(item: dict[str, Any]) -> FieldCandidates:
    """Parse a DiscountOffer or PromotionCard into FieldCandidates."""
    candidates = FieldCandidates()
    
    code = item.get("discountCode")
    if code:
        candidates.code = FieldValue(value=str(code), confidence=HIGH_CONFIDENCE, source=SOURCE)
    
    discount_value = _extract_discount_value(item)
    if discount_value:
        candidates.discount_value = FieldValue(
            value=discount_value, confidence=HIGH_CONFIDENCE, source=SOURCE
        )
    
    min_spend = _extract_min_spend(item)
    if min_spend:
        candidates.min_spend = FieldValue(
            value=min_spend, confidence=MEDIUM_CONFIDENCE, source=SOURCE
        )
    
    max_discount = _extract_max_discount(item)
    if max_discount:
        candidates.max_discount = FieldValue(
            value=max_discount, confidence=MEDIUM_CONFIDENCE, source=SOURCE
        )
    
    starts = item.get("validFrom") or item.get("availabilityStarts")
    if starts:
        candidates.starts = FieldValue(value=str(starts), confidence=HIGH_CONFIDENCE, source=SOURCE)
    
    expiry = item.get("validThrough") or item.get("availabilityEnds")
    if expiry:
        candidates.expiry = FieldValue(value=str(expiry), confidence=HIGH_CONFIDENCE, source=SOURCE)
    
    merchant = _extract_merchant(item)
    if merchant:
        candidates.merchant = FieldValue(
            value=merchant, confidence=HIGH_CONFIDENCE, source=SOURCE
        )
    
    return candidates


def _parse_offer(item: dict[str, Any]) -> FieldCandidates:
    """Parse a standard Offer with discount properties into FieldCandidates."""
    candidates = FieldCandidates()
    
    discount_value = _extract_offer_discount_value(item)
    if discount_value:
        candidates.discount_value = FieldValue(
            value=discount_value, confidence=BASE_CONFIDENCE, source=SOURCE
        )
    
    min_spend = _extract_min_spend(item)
    if min_spend:
        candidates.min_spend = FieldValue(
            value=min_spend, confidence=BASE_CONFIDENCE, source=SOURCE
        )
    
    starts = item.get("validFrom")
    if starts:
        candidates.starts = FieldValue(value=str(starts), confidence=MEDIUM_CONFIDENCE, source=SOURCE)
    
    expiry = item.get("validThrough")
    if expiry:
        candidates.expiry = FieldValue(value=str(expiry), confidence=MEDIUM_CONFIDENCE, source=SOURCE)
    
    merchant = _extract_merchant(item)
    if merchant:
        candidates.merchant = FieldValue(
            value=merchant, confidence=BASE_CONFIDENCE, source=SOURCE
        )
    
    return candidates


def _extract_discount_value(item: dict[str, Any]) -> str | None:
    """Extract discount value from DiscountOffer."""
    discount = item.get("discount")
    discount_type = item.get("discountType", "").lower()
    currency = item.get("discountCurrency", "USD")
    
    if discount:
        if discount_type == "percent":
            return f"{discount}% off"
        else:
            return f"${discount} off" if currency == "USD" else f"{discount} {currency} off"
    
    price = item.get("price")
    price_currency = item.get("priceCurrency", "USD")
    if price:
        return f"${price}" if price_currency == "USD" else f"{price} {price_currency}"
    
    return None


def _extract_offer_discount_value(item: dict[str, Any]) -> str | None:
    """Extract discount value from standard Offer."""
    price_spec = item.get("priceSpecification", {})
    if isinstance(price_spec, dict):
        price = price_spec.get("price")
        currency = price_spec.get("priceCurrency", "USD")
        if price:
            return f"${price} off" if currency == "USD" else f"{price} {currency} off"
    
    desc = item.get("description")
    if desc:
        return str(desc)
    
    name = item.get("name")
    if name:
        return str(name)
    
    return None


def _extract_min_spend(item: dict[str, Any]) -> str | None:
    """Extract minimum spend from item."""
    min_price = item.get("minPrice")
    if min_price:
        return f"${min_price}"
    
    eligible = item.get("eligibleTransactionVolume", {})
    if isinstance(eligible, dict):
        min_val = eligible.get("minPrice")
        currency = eligible.get("priceCurrency", "USD")
        if min_val:
            return f"${min_val}" if currency == "USD" else f"{min_val} {currency}"
    
    return None


def _extract_max_discount(item: dict[str, Any]) -> str | None:
    """Extract maximum discount cap."""
    price_spec = item.get("priceSpecification", {})
    if isinstance(price_spec, dict):
        max_price = price_spec.get("maxPrice")
        if max_price:
            currency = price_spec.get("priceCurrency", "USD")
            return f"${max_price}" if currency == "USD" else f"{max_price} {currency}"
    return None


def _extract_merchant(item: dict[str, Any]) -> str | None:
    """Extract merchant/seller name."""
    for key in ("seller", "offeredBy", "merchant"):
        entity = item.get(key)
        if entity:
            if isinstance(entity, dict):
                name = entity.get("name")
                if name:
                    return str(name)
            elif isinstance(entity, str):
                return entity
    return None
