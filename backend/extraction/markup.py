"""Structured-markup extraction (schema.org JSON-LD + microdata) via extruct.

Targets the Google Gmail promotions-tab annotations
(https://developers.google.com/workspace/gmail/promotab/reference):
DiscountOffer (description, discountCode, availabilityStarts,
availabilityEnds), PromotionCard (discountValue, price, url) and plain
schema.org Offer, plus the Organization/seller name for the merchant.

Fields read directly from markup get source="email_jsonld" and
confidence 0.98.
"""
from __future__ import annotations

import extruct

from backend.extraction.types import FieldCandidates, FieldValue

_SOURCE = "email_jsonld"
_CONFIDENCE = 0.98

_OFFER_TYPES = {"DiscountOffer", "Offer", "PromotionCard"}
_MERCHANT_KEYS = ("seller", "offeredBy", "merchant", "provider", "brand")


def extract_markup(html: str | None) -> FieldCandidates | None:
    """Extract reward field candidates from schema.org markup in email HTML.

    Returns None when there is no HTML, no parseable markup, or no
    DiscountOffer/Offer/PromotionCard item with usable fields.
    """
    if not html:
        return None

    try:
        data = extruct.extract(
            html,
            base_url="http://email.local/",
            syntaxes=["json-ld", "microdata"],
            uniform=True,
        )
    except Exception:
        return None

    items: list[dict] = []
    for syntax in ("json-ld", "microdata"):
        for item in data.get(syntax, []):
            if isinstance(item, dict):
                items.extend(_flatten_graph(item))

    candidates = FieldCandidates()
    found = False
    for item in items:
        if _item_types(item) & _OFFER_TYPES:
            if _map_offer(item, candidates):
                found = True

    return candidates if found else None


def _flatten_graph(item: dict) -> list[dict]:
    graph = item.get("@graph")
    if isinstance(graph, list):
        return [node for node in graph if isinstance(node, dict)]
    return [item]


def _item_types(item: dict) -> set[str]:
    raw = item.get("@type", [])
    if isinstance(raw, str):
        raw = [raw]
    # Uniform microdata types may be full URLs like https://schema.org/Offer.
    return {str(t).rstrip("/").rsplit("/", 1)[-1] for t in raw}


def _map_offer(item: dict, c: FieldCandidates) -> bool:
    """Map one DiscountOffer/Offer/PromotionCard item onto FieldCandidates.

    Returns True if at least one field was set.
    """
    found = False

    def _set(attr: str, value: str | None) -> None:
        nonlocal found
        if value and getattr(c, attr) is None:
            setattr(c, attr, FieldValue(value=value, confidence=_CONFIDENCE, source=_SOURCE))
            found = True

    price_spec = item.get("priceSpecification") or {}
    eligible = item.get("eligibleTransactionVolume") or {}
    currency = _as_str(item.get("discountCurrency")) or _as_str(price_spec.get("priceCurrency")) or "USD"

    _set("code", _as_str(item.get("discountCode")))
    _set("discount_value", _discount_value(item, price_spec, currency))
    _set("min_spend", _as_str(eligible.get("minPrice")) or _as_str(item.get("minPrice")))
    _set("max_discount", _as_str(price_spec.get("maxPrice")))
    _set("starts", _as_str(item.get("availabilityStarts")) or _as_str(item.get("validFrom")))
    _set("expiry", _as_str(item.get("availabilityEnds")) or _as_str(item.get("validThrough")))
    _set("merchant", _merchant_name(item))

    return found


def _discount_value(item: dict, price_spec: dict, currency: str) -> str | None:
    # Gmail PromotionCard: discountValue is pre-formatted, e.g. "25%" or "$10".
    discount_value = _as_str(item.get("discountValue"))
    if discount_value:
        return f"{discount_value} off" if not discount_value.lower().endswith("off") else discount_value

    # Gmail DiscountOffer: discount + discountType ("Percent" / "Amount").
    discount = _as_str(item.get("discount"))
    if discount:
        discount_type = (_as_str(item.get("discountType")) or "").lower()
        if "percent" in discount_type or discount.endswith("%"):
            return f"{discount.rstrip('%')}% off"
        return f"{_money(discount, currency)} off"

    # Plain Offer in a promo email: priceSpecification.price is the amount off.
    # PromotionCard also carries a price field.
    price = _as_str(price_spec.get("price")) or _as_str(item.get("price"))
    if price:
        return f"{_money(price, currency)} off"
    return None


def _money(amount: str, currency: str) -> str:
    return f"${amount}" if currency in ("", "USD") else f"{amount} {currency}"


def _merchant_name(item: dict) -> str | None:
    for key in _MERCHANT_KEYS:
        org = item.get(key)
        if isinstance(org, dict):
            name = _as_str(org.get("name"))
            if name:
                return name
        elif isinstance(org, str) and org.strip():
            return org.strip()
    return None


def _as_str(value) -> str | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (str, int, float)):
        text = str(value).strip()
        return text or None
    return None
