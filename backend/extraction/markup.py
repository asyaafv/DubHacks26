"""Schema.org JSON-LD and microdata extraction for Gmail promotions annotations."""
from __future__ import annotations

import re
from typing import Any

from backend.extraction.types import FieldCandidates, FieldValue

JSONLD_CONFIDENCE = 0.98
SOURCE = "email_jsonld"

OFFER_TYPES = frozenset({
    "DiscountOffer",
    "Offer",
    "PromotionCard",
    "http://schema.org/DiscountOffer",
    "http://schema.org/Offer",
    "http://schema.org/PromotionCard",
    "https://schema.org/DiscountOffer",
    "https://schema.org/Offer",
    "https://schema.org/PromotionCard",
})

ORDER_TYPES = frozenset({
    "Order",
    "http://schema.org/Order",
    "https://schema.org/Order",
})

PROMO_OFFER_TYPES = frozenset({
    "DiscountOffer",
    "PromotionCard",
    "http://schema.org/DiscountOffer",
    "http://schema.org/PromotionCard",
    "https://schema.org/DiscountOffer",
    "https://schema.org/PromotionCard",
})


def extract_markup(html: str | None) -> FieldCandidates | None:
    """Extract schema.org JSON-LD and microdata from HTML.
    
    Looks for Gmail promotions annotations:
    - schema.org DiscountOffer (description, discountCode, availabilityStarts, availabilityEnds, merchant/seller)
    - schema.org PromotionCard (discountValue, price, priceCurrency)
    - schema.org Offer (with discount info)
    
    Returns FieldCandidates with source='email_jsonld' and confidence 0.98.
    Returns None if no relevant markup found.
    """
    if not html:
        return None
    
    try:
        import extruct
        from w3lib.html import get_base_url
    except ImportError:
        return None
    
    try:
        base_url = get_base_url(html, "")
        data = extruct.extract(
            html,
            base_url=base_url,
            syntaxes=["json-ld", "microdata"],
            uniform=True,
        )
    except Exception:
        return None
    
    items = data.get("json-ld", []) + data.get("microdata", [])
    
    offers = []
    for item in items:
        if _is_order_type(item):
            continue
        if _is_offer_type(item) and _is_promotional_offer(item):
            offers.append(item)
        elif isinstance(item, dict):
            for nested in _find_nested_offers(item):
                if _is_promotional_offer(nested):
                    offers.append(nested)
    
    if not offers:
        return None
    
    candidates = FieldCandidates()
    
    for offer in offers:
        _extract_offer_fields(offer, candidates)
    
    if not _has_any_field(candidates):
        return None
    
    return candidates


def _is_offer_type(item: Any) -> bool:
    """Check if item is a relevant offer type."""
    if not isinstance(item, dict):
        return False
    item_type = item.get("@type") or item.get("type")
    if isinstance(item_type, list):
        return any(t in OFFER_TYPES for t in item_type)
    return item_type in OFFER_TYPES


def _is_order_type(item: Any) -> bool:
    """Check if item is an Order type (receipt, not promotion)."""
    if not isinstance(item, dict):
        return False
    item_type = item.get("@type") or item.get("type")
    if isinstance(item_type, list):
        return any(t in ORDER_TYPES for t in item_type)
    return item_type in ORDER_TYPES


def _is_promotional_offer(offer: dict) -> bool:
    """Check if an offer is a promotional offer (not just a product listing).
    
    Returns True if the offer has discount-related fields like:
    - discountCode, discount, discountValue
    - validThrough (expiry date for promotion)
    - eligibleTransactionVolume (min spend)
    - DiscountOffer or PromotionCard type
    """
    item_type = offer.get("@type") or offer.get("type")
    if isinstance(item_type, list):
        if any(t in PROMO_OFFER_TYPES for t in item_type):
            return True
    elif item_type in PROMO_OFFER_TYPES:
        return True
    
    promo_fields = [
        "discountCode", "discount_code", "promoCode",
        "discount", "discountValue", "discountType",
        "validThrough", "validFrom",
        "eligibleTransactionVolume",
    ]
    
    for field in promo_fields:
        if field in offer and offer[field]:
            return True
    
    return False


def _find_nested_offers(item: dict) -> list[dict]:
    """Find nested offer objects within a larger schema.
    
    Skips offers inside Order types (those are product listings, not promos).
    """
    if _is_order_type(item):
        return []
    
    offers = []
    for key, value in item.items():
        if isinstance(value, dict):
            if _is_order_type(value):
                continue
            if _is_offer_type(value):
                offers.append(value)
        elif isinstance(value, list):
            for sub_item in value:
                if isinstance(sub_item, dict):
                    if _is_order_type(sub_item):
                        continue
                    if _is_offer_type(sub_item):
                        offers.append(sub_item)
    return offers


def _extract_offer_fields(offer: dict, candidates: FieldCandidates) -> None:
    """Extract fields from an offer object into FieldCandidates."""
    code = _get_discount_code(offer)
    if code and candidates.code is None:
        candidates.code = FieldValue(value=code, confidence=JSONLD_CONFIDENCE, source=SOURCE)
    
    discount_value = _get_discount_value(offer)
    if discount_value and candidates.discount_value is None:
        candidates.discount_value = FieldValue(
            value=discount_value, confidence=JSONLD_CONFIDENCE, source=SOURCE
        )
    
    expiry = _get_expiry(offer)
    if expiry and candidates.expiry is None:
        candidates.expiry = FieldValue(value=expiry, confidence=JSONLD_CONFIDENCE, source=SOURCE)
    
    starts = _get_starts(offer)
    if starts and candidates.starts is None:
        candidates.starts = FieldValue(value=starts, confidence=JSONLD_CONFIDENCE, source=SOURCE)
    
    merchant = _get_merchant(offer)
    if merchant and candidates.merchant is None:
        candidates.merchant = FieldValue(
            value=merchant, confidence=JSONLD_CONFIDENCE, source=SOURCE
        )
    
    min_spend = _get_min_spend(offer)
    if min_spend and candidates.min_spend is None:
        candidates.min_spend = FieldValue(
            value=min_spend, confidence=JSONLD_CONFIDENCE, source=SOURCE
        )
    
    max_discount = _get_max_discount(offer)
    if max_discount and candidates.max_discount is None:
        candidates.max_discount = FieldValue(
            value=max_discount, confidence=JSONLD_CONFIDENCE, source=SOURCE
        )


def _get_discount_code(offer: dict) -> str | None:
    """Extract discount/promo code from offer."""
    for key in ["discountCode", "discount_code", "code", "promoCode", "promo_code"]:
        if key in offer and offer[key]:
            return str(offer[key])
    return None


def _get_discount_value(offer: dict) -> str | None:
    """Extract discount value (percentage or amount) from offer."""
    discount = offer.get("discount")
    discount_type = offer.get("discountType", "")
    
    if discount:
        if discount_type.lower() == "percent":
            return f"{discount}% off"
        elif discount_type.lower() == "amount":
            currency = offer.get("discountCurrency", "USD")
            return f"${discount} off" if currency == "USD" else f"{discount} {currency} off"
        return str(discount)
    
    for key in ["discountValue", "discount_value"]:
        if key in offer and offer[key]:
            return str(offer[key])
    
    price_spec = offer.get("priceSpecification")
    if isinstance(price_spec, dict):
        price = price_spec.get("price")
        currency = price_spec.get("priceCurrency", "USD")
        if price:
            return f"${price} off" if currency == "USD" else f"{price} {currency} off"
    
    for key in ["price"]:
        if key in offer and offer[key]:
            currency = offer.get("priceCurrency", "USD")
            val = offer[key]
            return f"${val}" if currency == "USD" else f"{val} {currency}"
    
    return None


def _get_expiry(offer: dict) -> str | None:
    """Extract expiration date from offer."""
    for key in [
        "validThrough",
        "availabilityEnds",
        "expires",
        "expirationDate",
        "valid_through",
    ]:
        if key in offer and offer[key]:
            return str(offer[key])
    return None


def _get_starts(offer: dict) -> str | None:
    """Extract start date from offer."""
    for key in ["validFrom", "availabilityStarts", "valid_from", "starts"]:
        if key in offer and offer[key]:
            return str(offer[key])
    return None


def _get_merchant(offer: dict) -> str | None:
    """Extract merchant/seller name from offer."""
    for key in ["seller", "offeredBy", "merchant", "provider"]:
        val = offer.get(key)
        if isinstance(val, dict):
            name = val.get("name")
            if name:
                return str(name)
        elif isinstance(val, str) and val:
            return val
    return None


def _get_min_spend(offer: dict) -> str | None:
    """Extract minimum spend from offer."""
    min_price = offer.get("minPrice")
    if min_price:
        return str(min_price)
    
    etv = offer.get("eligibleTransactionVolume")
    if isinstance(etv, dict):
        min_price = etv.get("minPrice")
        currency = etv.get("priceCurrency", "USD")
        if min_price:
            return f"${min_price}" if currency == "USD" else f"{min_price} {currency}"
    
    return None


def _get_max_discount(offer: dict) -> str | None:
    """Extract maximum discount cap from offer."""
    price_spec = offer.get("priceSpecification")
    if isinstance(price_spec, dict):
        max_price = price_spec.get("maxPrice")
        if max_price:
            currency = price_spec.get("priceCurrency", "USD")
            return f"${max_price}" if currency == "USD" else f"{max_price} {currency}"
    
    return None


def _has_any_field(candidates: FieldCandidates) -> bool:
    """Check if any field was extracted."""
    return any([
        candidates.merchant,
        candidates.discount_value,
        candidates.min_spend,
        candidates.max_discount,
        candidates.expiry,
        candidates.starts,
        candidates.code,
        candidates.stackable,
        candidates.exclusions,
    ])
