"""
Regex-based field extraction for reward emails.

Extracts discount offers, codes, dates, and constraints using optimized patterns.
Designed to run in under 5ms on typical email text.
"""
from __future__ import annotations

import re
from typing import Callable

from backend.extraction.types import FieldCandidates, FieldValue

_SOURCE = "regex"


_PERCENT_OFF_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"(\d{1,2})%\s*off", re.IGNORECASE), 0.8),
    (re.compile(r"save\s+(\d{1,2})%", re.IGNORECASE), 0.75),
    (re.compile(r"(\d{1,2})\s*percent\s*off", re.IGNORECASE), 0.75),
    (re.compile(r"get\s+(\d{1,2})%", re.IGNORECASE), 0.7),
]

_DOLLAR_OFF_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"\$(\d+(?:\.\d{1,2})?)\s+off", re.IGNORECASE), 0.8),
    (re.compile(r"save\s+\$(\d+(?:\.\d{1,2})?)", re.IGNORECASE), 0.75),
    (re.compile(r"\$(\d+(?:\.\d{1,2})?)\s+reward", re.IGNORECASE), 0.7),
    (re.compile(r"get\s+\$(\d+(?:\.\d{1,2})?)\s+off", re.IGNORECASE), 0.75),
]

_POINTS_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"(\d+)x\s+points", re.IGNORECASE), 0.75),
    (re.compile(r"(\d+)\s*bonus\s*points", re.IGNORECASE), 0.75),
    (re.compile(r"earn\s+(\d+)\s*points", re.IGNORECASE), 0.7),
    (re.compile(r"(\d+)\s*extra\s*points", re.IGNORECASE), 0.7),
]

_FREE_ITEM_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"free\s+(\w+(?:\s+\w+)?)", re.IGNORECASE), 0.7),
    (re.compile(r"buy\s+one\s+get\s+one(?:\s+free)?", re.IGNORECASE), 0.8),
    (re.compile(r"bogo", re.IGNORECASE), 0.8),
    (re.compile(r"get\s+(?:a\s+)?free\s+(\w+)", re.IGNORECASE), 0.7),
]

_MIN_SPEND_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"(?:on\s+)?orders?\s+(?:of\s+)?\$(\d+(?:\.\d{1,2})?)\s*(?:\+|or\s+more)", re.IGNORECASE), 0.8),
    (re.compile(r"spend\s+\$(\d+(?:\.\d{1,2})?)\s*(?:\+|or\s+more)?", re.IGNORECASE), 0.8),
    (re.compile(r"min(?:imum)?\s+(?:purchase(?:\s+of)?[:\s]+)?\$(\d+(?:\.\d{1,2})?)", re.IGNORECASE), 0.8),
    (re.compile(r"when\s+you\s+spend\s+\$(\d+(?:\.\d{1,2})?)", re.IGNORECASE), 0.75),
    (re.compile(r"\$(\d+(?:\.\d{1,2})?)\s*\+", re.IGNORECASE), 0.65),
    (re.compile(r"minimum\s+purchase[:\s]+\$(\d+(?:\.\d{1,2})?)", re.IGNORECASE), 0.8),
]

_MAX_DISCOUNT_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"up\s+to\s+\$(\d+(?:\.\d{1,2})?)", re.IGNORECASE), 0.8),
    (re.compile(r"max(?:imum)?\s+(?:discount|savings)[:\s]+\$(\d+(?:\.\d{1,2})?)", re.IGNORECASE), 0.8),
    (re.compile(r"max\s+discount[:\s]+\$(\d+(?:\.\d{1,2})?)", re.IGNORECASE), 0.8),
]

_EXPIRY_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(
        r"(?:expires?|expiring|valid\s+(?:through|until|thru)|ends?|by|through|until|offer\s+ends?)[:\s]+?"
        r"(\d{1,2}/\d{1,2}(?:/\d{2,4})?|\w+\s+\d{1,2}(?:,?\s*\d{4})?|"
        r"(?:sun|mon|tue|wed|thu|fri|sat)(?:day)?|tonight|today|tomorrow|"
        r"\d{1,2}:\d{2}\s*(?:am|pm)?\s*(?:[A-Z]{2,4})?\s*\d{1,2}/\d{1,2})",
        re.IGNORECASE
    ), 0.8),
    (re.compile(r"ends?\s+(tonight|today)", re.IGNORECASE), 0.75),
    (re.compile(r"valid\s+(through|until|thru)\s+(\w+\s+\d{1,2}(?:,?\s*\d{4})?)", re.IGNORECASE), 0.8),
    (re.compile(
        r"offer\s+ends?\s+(\d{1,2}:\d{2}\s*(?:am|pm)?\s*(?:[A-Z]{2,4})?\s*\d{1,2}/\d{1,2})",
        re.IGNORECASE
    ), 0.75),
]

_CODE_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"promo\s+code[:\s]+([A-Z0-9]{3,20})", re.IGNORECASE), 0.8),
    (re.compile(r"(?:use\s+)?(?:code|coupon)[:\s]+([A-Z0-9]{3,20})", re.IGNORECASE), 0.8),
    (re.compile(r"code[:\s]+([A-Z0-9]{3,20})", re.IGNORECASE), 0.8),
    (re.compile(r"coupon[:\s]+([A-Z0-9]{3,20})", re.IGNORECASE), 0.75),
    (re.compile(r"use\s+([A-Z0-9]{4,20})\s+at\s+checkout", re.IGNORECASE), 0.75),
]

_STACKABLE_TRUE_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"can\s+be\s+combined", re.IGNORECASE), 0.8),
    (re.compile(r"stackable\s+with", re.IGNORECASE), 0.8),
    (re.compile(r"combine\s+with\s+other\s+(?:offers?|coupons?|discounts?)", re.IGNORECASE), 0.75),
    (re.compile(r"is\s+stackable", re.IGNORECASE), 0.8),
]

_STACKABLE_FALSE_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"cannot\s+be\s+combined", re.IGNORECASE), 0.8),
    (re.compile(r"can(?:'t|not)\s+(?:be\s+)?combine", re.IGNORECASE), 0.8),
    (re.compile(r"not\s+(?:valid|combinable)\s+with\s+(?:other\s+)?(?:offers?|coupons?|discounts?)", re.IGNORECASE), 0.8),
    (re.compile(r"one\s+(?:coupon|offer|discount)\s+per\s+(?:order|purchase|transaction)", re.IGNORECASE), 0.75),
]

_EXCLUSION_PATTERNS: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"excludes?[:\s]+([^.;\n]+)", re.IGNORECASE), 0.75),
    (re.compile(r"not\s+valid\s+(?:on|for)[:\s]+([^.;\n]+)", re.IGNORECASE), 0.75),
    (re.compile(r"exclusions?[:\s]+([^.;\n]+)", re.IGNORECASE), 0.75),
    (re.compile(r"does\s+not\s+(?:apply|include)[:\s]+([^.;\n]+)", re.IGNORECASE), 0.7),
]


def _find_first_match(
    text: str,
    patterns: list[tuple[re.Pattern[str], float]],
    extract_fn: Callable[[re.Match[str]], str] | None = None,
) -> FieldValue | None:
    """Find the first matching pattern and return a FieldValue."""
    for pattern, confidence in patterns:
        match = pattern.search(text)
        if match:
            if extract_fn:
                value = extract_fn(match)
            else:
                value = match.group(1) if match.lastindex else match.group(0)
            return FieldValue(value=value, confidence=confidence, source=_SOURCE)
    return None


def _find_all_matches(
    text: str,
    patterns: list[tuple[re.Pattern[str], float]],
) -> list[FieldValue]:
    """Find all matching patterns and return a list of FieldValues."""
    results: list[FieldValue] = []
    seen: set[str] = set()
    for pattern, confidence in patterns:
        for match in pattern.finditer(text):
            value = match.group(1) if match.lastindex else match.group(0)
            value_lower = value.lower().strip()
            if value_lower not in seen:
                seen.add(value_lower)
                results.append(FieldValue(value=value.strip(), confidence=confidence, source=_SOURCE))
    return results


def extract_fields_regex(text: str) -> FieldCandidates:
    """
    Extract reward fields from text using regex patterns.

    Designed to complete in under 5ms for typical email text lengths.

    Args:
        text: Plain text content of the email

    Returns:
        FieldCandidates with extracted fields and confidence scores
    """
    candidates = FieldCandidates()

    percent_match = _find_first_match(text, _PERCENT_OFF_PATTERNS)
    if percent_match:
        candidates.discount_value = FieldValue(
            value=f"{percent_match.value}% off",
            confidence=percent_match.confidence,
            source=_SOURCE,
        )
    else:
        dollar_match = _find_first_match(text, _DOLLAR_OFF_PATTERNS)
        if dollar_match:
            candidates.discount_value = FieldValue(
                value=f"${dollar_match.value} off",
                confidence=dollar_match.confidence,
                source=_SOURCE,
            )
        else:
            points_match = _find_first_match(text, _POINTS_PATTERNS)
            if points_match:
                raw_value = points_match.value
                if "x" in raw_value.lower() or text.lower().find(f"{raw_value}x") != -1:
                    candidates.discount_value = FieldValue(
                        value=f"{raw_value}x points",
                        confidence=points_match.confidence,
                        source=_SOURCE,
                    )
                else:
                    candidates.discount_value = FieldValue(
                        value=f"{raw_value} points",
                        confidence=points_match.confidence,
                        source=_SOURCE,
                    )
            else:
                free_match = _find_first_match(
                    text,
                    _FREE_ITEM_PATTERNS,
                    lambda m: m.group(0),
                )
                if free_match:
                    candidates.discount_value = free_match

    min_spend_match = _find_first_match(text, _MIN_SPEND_PATTERNS)
    if min_spend_match:
        candidates.min_spend = FieldValue(
            value=f"${min_spend_match.value}",
            confidence=min_spend_match.confidence,
            source=_SOURCE,
        )

    max_discount_match = _find_first_match(text, _MAX_DISCOUNT_PATTERNS)
    if max_discount_match:
        candidates.max_discount = FieldValue(
            value=f"${max_discount_match.value}",
            confidence=max_discount_match.confidence,
            source=_SOURCE,
        )

    expiry_match = _find_first_match(
        text,
        _EXPIRY_PATTERNS,
        lambda m: m.group(2) if m.lastindex and m.lastindex >= 2 else (m.group(1) if m.lastindex else m.group(0)),
    )
    if expiry_match:
        candidates.expiry = expiry_match

    code_match = _find_first_match(text, _CODE_PATTERNS)
    if code_match:
        candidates.code = FieldValue(
            value=code_match.value.upper(),
            confidence=code_match.confidence,
            source=_SOURCE,
        )

    stackable_true = _find_first_match(text, _STACKABLE_TRUE_PATTERNS, lambda m: "true")
    stackable_false = _find_first_match(text, _STACKABLE_FALSE_PATTERNS, lambda m: "false")

    if stackable_false:
        candidates.stackable = stackable_false
    elif stackable_true:
        candidates.stackable = stackable_true

    exclusions = _find_all_matches(text, _EXCLUSION_PATTERNS)
    if exclusions:
        candidates.exclusions = exclusions

    return candidates
