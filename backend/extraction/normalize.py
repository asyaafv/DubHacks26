"""
Normalize extracted field candidates into structured Reward fields.

Uses dateparser for date parsing and price-parser for currency amounts.
All dates are interpreted relative to the email date.
"""
from __future__ import annotations

import re
from datetime import datetime, time, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import dateparser
from price_parser import Price

from backend.extraction.types import FieldCandidates, FieldValue


_PERCENT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
_DOLLAR_PATTERN = re.compile(r"\$\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_POINTS_PATTERN = re.compile(r"(\d+)\s*(?:x\s*)?points?", re.IGNORECASE)
_POINTS_MULTIPLIER_PATTERN = re.compile(r"(\d+)x\s*points?", re.IGNORECASE)
_FREE_ITEM_PATTERN = re.compile(r"free\s+\w+", re.IGNORECASE)
_BOGO_PATTERN = re.compile(r"(?:buy\s+one\s+get\s+one|bogo)", re.IGNORECASE)

_TONIGHT_PATTERN = re.compile(r"tonight", re.IGNORECASE)
_TODAY_PATTERN = re.compile(r"today", re.IGNORECASE)

# Source priority for merging candidates: structured markup beats NER beats regex.
_SOURCE_PRIORITY = {"email_jsonld": 3, "gliner": 2, "regex": 1}
_MERGE_FIELDS = (
    "merchant",
    "discount_value",
    "min_spend",
    "max_discount",
    "expiry",
    "starts",
    "code",
    "stackable",
)


def merge_candidates(*candidates: FieldCandidates | None) -> FieldCandidates:
    """
    Merge FieldCandidates from multiple extractors into one.

    Per field, the candidate from the highest-priority source wins
    (email_jsonld > gliner > regex); ties are broken by confidence.
    Exclusions are taken from the first candidate that has any.
    """
    merged = FieldCandidates()
    present = [c for c in candidates if c is not None]
    for name in _MERGE_FIELDS:
        best: FieldValue | None = None
        for cand in present:
            fv: FieldValue | None = getattr(cand, name)
            if fv is None or not str(fv.value).strip():
                continue
            if best is None or (
                _SOURCE_PRIORITY.get(fv.source, 0),
                fv.confidence,
            ) > (_SOURCE_PRIORITY.get(best.source, 0), best.confidence):
                best = fv
        setattr(merged, name, best)
    for cand in present:
        if cand.exclusions:
            merged.exclusions = list(cand.exclusions)
            break
    return merged


def _parse_discount_value(
    field: FieldValue | None,
) -> tuple[str | None, Decimal | None, str, float]:
    """
    Parse discount value into kind, value, and currency.

    Returns:
        (kind, value, currency, parse_factor)
        parse_factor is 1.0 for successful parse, lower for partial success
    """
    if not field:
        return None, None, "USD", 1.0

    text = field.value.lower()

    percent_match = _PERCENT_PATTERN.search(text)
    if percent_match:
        try:
            val = Decimal(percent_match.group(1))
            return "percent_off", val, "USD", 1.0
        except InvalidOperation:
            return "percent_off", None, "USD", 0.5

    dollar_match = _DOLLAR_PATTERN.search(field.value)
    if dollar_match:
        try:
            val = Decimal(dollar_match.group(1))
            return "amount_off", val, "USD", 1.0
        except InvalidOperation:
            return "amount_off", None, "USD", 0.5

    # Only try price-parser when there is an actual number; otherwise texts
    # like "FREE Guacamole reward" get misparsed as amount_off 0.
    if "reward" in text and any(ch.isdigit() for ch in text):
        price = Price.fromstring(field.value)
        if price.amount is not None:
            return "amount_off", Decimal(str(price.amount)), price.currency or "USD", 1.0

    points_mult_match = _POINTS_MULTIPLIER_PATTERN.search(text)
    if points_mult_match:
        try:
            val = Decimal(points_mult_match.group(1))
            return "points", val, "USD", 1.0
        except InvalidOperation:
            return "points", None, "USD", 0.5

    points_match = _POINTS_PATTERN.search(text)
    if points_match:
        try:
            val = Decimal(points_match.group(1))
            return "points", val, "USD", 1.0
        except InvalidOperation:
            return "points", None, "USD", 0.5

    if _BOGO_PATTERN.search(text):
        return "bogo", Decimal("1"), "USD", 1.0

    if _FREE_ITEM_PATTERN.search(text):
        return "free_item", Decimal("1"), "USD", 1.0

    return None, None, "USD", 0.3


def _parse_price(field: FieldValue | None) -> tuple[Decimal | None, float]:
    """
    Parse price/spend amount.

    Returns:
        (amount, parse_factor)
    """
    if not field:
        return None, 1.0

    dollar_match = _DOLLAR_PATTERN.search(field.value)
    if dollar_match:
        try:
            return Decimal(dollar_match.group(1)), 1.0
        except InvalidOperation:
            pass

    price = Price.fromstring(field.value)
    if price.amount is not None:
        return Decimal(str(price.amount)), 1.0

    return None, 0.5


def _parse_date(
    field: FieldValue | None,
    email_date: datetime,
) -> tuple[datetime | None, float]:
    """
    Parse date string relative to email date.

    Handles special cases like 'tonight', 'today', and weekday names.

    Returns:
        (parsed_datetime, parse_factor)
    """
    if not field:
        return None, 1.0

    text = field.value.strip()

    if _TONIGHT_PATTERN.search(text):
        end_of_day = datetime.combine(
            email_date.date(),
            time(23, 59, 59),
            tzinfo=email_date.tzinfo or timezone.utc,
        )
        return end_of_day, 1.0

    if _TODAY_PATTERN.fullmatch(text):
        end_of_day = datetime.combine(
            email_date.date(),
            time(23, 59, 59),
            tzinfo=email_date.tzinfo or timezone.utc,
        )
        return end_of_day, 1.0

    settings: dict[str, Any] = {
        "RELATIVE_BASE": email_date.replace(tzinfo=None) if email_date.tzinfo else email_date,
        "PREFER_DATES_FROM": "future",
        "RETURN_AS_TIMEZONE_AWARE": True,
    }

    parsed = dateparser.parse(text, settings=settings)

    if parsed:
        if parsed.hour == 0 and parsed.minute == 0 and parsed.second == 0:
            parsed = parsed.replace(hour=23, minute=59, second=59)
        return parsed, 1.0

    return None, 0.3


def _parse_stackable(field: FieldValue | None) -> tuple[bool, float]:
    """
    Parse stackability field.

    Returns:
        (stackable_bool, parse_factor)
    """
    if not field:
        return False, 1.0

    text = field.value.lower().strip()
    if text == "true":
        return True, 1.0
    if text == "false":
        return False, 1.0

    return False, 0.5


def normalize(c: FieldCandidates, email_date: datetime) -> dict[str, Any]:
    """
    Normalize extracted field candidates into Reward-compatible fields.

    Args:
        c: FieldCandidates from extraction
        email_date: The datetime the email was received (used as RELATIVE_BASE)

    Returns:
        dict with keys matching Reward fields:
        - kind (RewardKind string value)
        - value (Decimal)
        - currency (str, default "USD")
        - min_spend (Decimal or None)
        - max_discount (Decimal or None)
        - code (str or None)
        - expires_at (datetime or None)
        - starts_at (datetime or None)
        - stackable (bool, default False)
        - exclusions (list[str])
        - field_confidence (dict[str, float])

        Missing or unparseable fields are omitted rather than guessed.
    """
    result: dict[str, Any] = {}
    field_confidence: dict[str, float] = {}

    kind, value, currency, value_factor = _parse_discount_value(c.discount_value)
    if kind and value is not None:
        result["kind"] = kind
        result["value"] = value
        result["currency"] = currency
        base_conf = c.discount_value.confidence if c.discount_value else 0.6
        field_confidence["value"] = base_conf * value_factor

    min_spend, min_spend_factor = _parse_price(c.min_spend)
    if min_spend is not None:
        result["min_spend"] = min_spend
        base_conf = c.min_spend.confidence if c.min_spend else 0.6
        field_confidence["min_spend"] = base_conf * min_spend_factor

    max_discount, max_discount_factor = _parse_price(c.max_discount)
    if max_discount is not None:
        result["max_discount"] = max_discount
        base_conf = c.max_discount.confidence if c.max_discount else 0.6
        field_confidence["max_discount"] = base_conf * max_discount_factor

    if c.code:
        result["code"] = c.code.value.upper()
        field_confidence["code"] = c.code.confidence

    expires_at, expires_factor = _parse_date(c.expiry, email_date)
    if expires_at is not None:
        result["expires_at"] = expires_at
        base_conf = c.expiry.confidence if c.expiry else 0.6
        field_confidence["expires_at"] = base_conf * expires_factor

    starts_at, starts_factor = _parse_date(c.starts, email_date)
    if starts_at is not None:
        result["starts_at"] = starts_at
        base_conf = c.starts.confidence if c.starts else 0.6
        field_confidence["starts_at"] = base_conf * starts_factor

    stackable, stackable_factor = _parse_stackable(c.stackable)
    result["stackable"] = stackable
    if c.stackable:
        field_confidence["stackable"] = c.stackable.confidence * stackable_factor

    if c.exclusions:
        result["exclusions"] = [excl.value.strip() for excl in c.exclusions]
        avg_conf = sum(e.confidence for e in c.exclusions) / len(c.exclusions)
        field_confidence["exclusions"] = avg_conf

    result["field_confidence"] = field_confidence

    return result
