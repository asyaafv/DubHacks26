"""PII redaction for inbound emails (intake, Agent A).

Redacts ONLY: credit card numbers, phone numbers, email addresses (except the
sender/recipient addresses passed via ``keep``), and US street addresses.
Never redacts names, dates, dollar amounts, percentages, promo codes, or
store/city names.

Engine strategy
---------------
* Primary: Microsoft Presidio (``presidio-analyzer``) with the small spaCy
  model ``en_core_web_sm``. Both are LAZY-loaded as a singleton on first use.
  Install::

      pip install -r backend/intake/requirements/redact.txt
      python -m spacy download en_core_web_sm

* Presidio's built-in LOCATION entity is intentionally NOT used: it is far too
  broad and eats store names and city names (Hollister, Target, Seattle...).
  Instead a custom ``PatternRecognizer`` for US street addresses
  ("123 Main St, Apt 4") is registered under the STREET_ADDRESS entity.

* Fallback: if presidio/spacy (or the model) are unavailable, pure-regex
  recognizers for the exact same entity types take over, so redaction never
  crashes the intake pipeline.

Replacements are stable tags: ``<CARD>``, ``<PHONE>``, ``<EMAIL>``,
``<ADDRESS>``. Counts are reported per Presidio entity-type name.

HTML handling: only text nodes are redacted; markup (tags/attributes) is never
touched. ``<script type="application/ld+json">`` blocks are left intact so
promo fields (discountCode etc.) survive, except email/phone VALUES inside
them, which are still redacted.
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any, Iterable, Optional

from backend.app.schemas import InboundEmail

logger = logging.getLogger("lapse.intake.redact")

# Entity type -> replacement tag. Counts returned by redact_text/redact_email
# are keyed by the entity-type names on the left.
TAGS: dict[str, str] = {
    "CREDIT_CARD": "<CARD>",
    "PHONE_NUMBER": "<PHONE>",
    "EMAIL_ADDRESS": "<EMAIL>",
    "STREET_ADDRESS": "<ADDRESS>",
}
_ALL_ENTITIES: tuple[str, ...] = tuple(TAGS)
# Inside JSON-LD blocks only email/phone values are fair game.
_JSONLD_ENTITIES: tuple[str, ...] = ("EMAIL_ADDRESS", "PHONE_NUMBER")
_SCORE_THRESHOLD = 0.4

# ---------------------------------------------------------------------------
# Shared street-address pattern (used by BOTH the Presidio PatternRecognizer
# and the regex fallback). Requires a leading house number so bare city/store
# names ("Seattle", "Hollister") can never match.
# ---------------------------------------------------------------------------
_STREET_SUFFIX = (
    r"(?:St(?:reet)?|Ave(?:nue)?|Blvd|Boulevard|Rd|Road|Dr(?:ive)?|Ln|Lane|"
    r"Ct|Court|Pl(?:ace)?|Ter(?:race)?|Way|Pkwy|Parkway|Cir(?:cle)?|"
    r"Hwy|Highway)"
)
_UNIT = r"(?:Apt|Apartment|Suite|Ste|Unit|Bldg|Fl(?:oor)?|Rm|Room|#)"
STREET_ADDRESS_REGEX = (
    r"\b\d{1,6}\s+(?:[NSEW]\.?\s+)?(?:[A-Z][A-Za-z'.-]*\s+){1,4}"
    + _STREET_SUFFIX
    + r"\.?(?:,?\s*"
    + _UNIT
    + r"\.?\s*#?\s*\w+)?"
)

# ---------------------------------------------------------------------------
# Regex fallback recognizers (same entity types as the Presidio path).
# ---------------------------------------------------------------------------
_FALLBACK_PATTERNS: dict[str, re.Pattern[str]] = {
    # 16-digit grouped (4-4-4-4, covers 13-19 via trailing group), Amex 4-6-5,
    # or 13-19 contiguous digits. All candidates must also pass Luhn, so order
    # numbers like Amazon's "112-3456789-0123456" are never flagged.
    "CREDIT_CARD": re.compile(
        r"(?<![\d-])(?:\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{1,7}"
        r"|\d{4}[ -]\d{6}[ -]\d{5}"
        r"|\d{13,19})(?![\d-])"
    ),
    # US-style numbers with separators: (206) 555-0143, 206-555-0143,
    # +1 206 555 0143, 1-800-806-6453. Separators are required so dates
    # (10/31/2026) and plain order numbers never match.
    "PHONE_NUMBER": re.compile(
        r"(?<!\d)(?:\+?1[\s.-])?(?:\(\d{3}\)\s*|\d{3}[\s.-])\d{3}[\s.-]\d{4}(?!\d)"
    ),
    "EMAIL_ADDRESS": re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
    "STREET_ADDRESS": re.compile(STREET_ADDRESS_REGEX),
}


# Real card numbers are contiguous or grouped 4-4-4-4(-extra) / Amex 4-6-5.
# Oddly-grouped digit runs (e.g. Amazon order numbers "112-3456789-0123456",
# where a sub-run can accidentally pass Luhn) are rejected by this shape check.
_CARD_SHAPE_RE = re.compile(
    r"^(?:\d{13,19}"
    r"|\d{4}([ -])\d{4}\1\d{4}(?:\1\d{1,7})?"
    r"|\d{4}([ -])\d{6}\2\d{5})$"
)


def _card_shape_ok(text: str) -> bool:
    return bool(_CARD_SHAPE_RE.match(text.strip()))


def _luhn_ok(digits: str) -> bool:
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# ---------------------------------------------------------------------------
# Lazy singleton Presidio engine.
# ---------------------------------------------------------------------------
_analyzer: Any = None
_analyzer_failed = False
_analyzer_lock = threading.Lock()


def _get_analyzer() -> Any:
    """Build the Presidio AnalyzerEngine once; None if unavailable."""
    global _analyzer, _analyzer_failed
    if _analyzer is not None or _analyzer_failed:
        return _analyzer
    with _analyzer_lock:
        if _analyzer is not None or _analyzer_failed:
            return _analyzer
        try:
            from presidio_analyzer import (
                AnalyzerEngine,
                Pattern,
                PatternRecognizer,
            )
            from presidio_analyzer.nlp_engine import NlpEngineProvider

            provider = NlpEngineProvider(
                nlp_configuration={
                    "nlp_engine_name": "spacy",
                    "models": [
                        {"lang_code": "en", "model_name": "en_core_web_sm"}
                    ],
                }
            )
            analyzer = AnalyzerEngine(
                nlp_engine=provider.create_engine(),
                supported_languages=["en"],
            )
            analyzer.registry.add_recognizer(
                PatternRecognizer(
                    supported_entity="STREET_ADDRESS",
                    name="us_street_address_recognizer",
                    patterns=[
                        Pattern(
                            name="us_street_address",
                            regex=STREET_ADDRESS_REGEX,
                            score=0.75,
                        )
                    ],
                )
            )
            _analyzer = analyzer
            logger.info("Presidio analyzer loaded (spaCy en_core_web_sm)")
        except Exception as exc:  # noqa: BLE001 - any failure -> regex fallback
            logger.warning(
                "Presidio/spaCy unavailable (%s); using regex fallback", exc
            )
            _analyzer_failed = True
    return _analyzer


def warm_up() -> bool:
    """Eagerly load the engine (e.g. at app startup). True if Presidio is live."""
    return _get_analyzer() is not None


# ---------------------------------------------------------------------------
# Span collection + replacement.
# ---------------------------------------------------------------------------

def _presidio_spans(
    text: str, entities: Iterable[str]
) -> Optional[list[tuple[int, int, str, float]]]:
    analyzer = _get_analyzer()
    if analyzer is None:
        return None
    try:
        results = analyzer.analyze(
            text=text,
            entities=list(entities),
            language="en",
            score_threshold=_SCORE_THRESHOLD,
        )
    except Exception as exc:  # noqa: BLE001 - never crash the pipeline
        logger.warning("Presidio analyze failed (%s); using regex fallback", exc)
        return None
    return [(r.start, r.end, r.entity_type, r.score) for r in results]


def _fallback_spans(
    text: str, entities: Iterable[str]
) -> list[tuple[int, int, str, float]]:
    spans: list[tuple[int, int, str, float]] = []
    for entity in entities:
        pattern = _FALLBACK_PATTERNS[entity]
        for match in pattern.finditer(text):
            if entity == "CREDIT_CARD" and not _luhn_ok(
                re.sub(r"\D", "", match.group())
            ):
                continue
            spans.append((match.start(), match.end(), entity, 1.0))
    return spans


def redact_text(
    text: str | None,
    keep: set[str] = frozenset(),
    *,
    entities: tuple[str, ...] = _ALL_ENTITIES,
) -> tuple[str | None, dict[str, int]]:
    """Redact PII in plain text.

    Returns (redacted_text, counts-per-entity-type). ``keep`` is a set of
    email addresses (sender/recipient) that must NOT be redacted. ``None`` or
    empty input is returned unchanged with empty counts.
    """
    counts: dict[str, int] = {}
    if not text:
        return text, counts

    spans = _presidio_spans(text, entities)
    if spans is None:
        spans = _fallback_spans(text, entities)

    keep_lc = {k.strip().lower() for k in keep if k}
    candidates = []
    for span in spans:
        start, end, entity, _score = span
        matched = text[start:end]
        if (
            entity == "EMAIL_ADDRESS"
            and matched.strip().strip("<>").lower() in keep_lc
        ):
            continue
        if entity == "CREDIT_CARD" and not _card_shape_ok(matched):
            continue
        candidates.append(span)

    # Resolve overlaps: earliest start wins; ties go to the longer span, then
    # the higher score.
    candidates.sort(key=lambda s: (s[0], -(s[1] - s[0]), -s[3]))
    resolved: list[tuple[int, int, str]] = []
    last_end = -1
    for start, end, entity, _score in candidates:
        if start >= last_end:
            resolved.append((start, end, entity))
            last_end = end

    out = text
    for start, end, entity in reversed(resolved):
        out = out[:start] + TAGS[entity] + out[end:]
        counts[entity] = counts.get(entity, 0) + 1
    return out, counts


# ---------------------------------------------------------------------------
# HTML handling.
# ---------------------------------------------------------------------------
_SCRIPT_STYLE_RE = re.compile(r"(?is)<(script|style)\b[^>]*>.*?</\1\s*>")
_JSONLD_OPEN_RE = re.compile(
    r'(?is)^<script\b[^>]*type\s*=\s*["\']?application/ld\+json["\']?[^>]*>'
)
_TAG_SPLIT_RE = re.compile(r"(<[^>]*>)")


def _merge_counts(total: dict[str, int], part: dict[str, int]) -> None:
    for key, value in part.items():
        total[key] = total.get(key, 0) + value


def _redact_markup_segment(segment: str, keep: set[str]) -> tuple[str, dict[str, int]]:
    """Redact only the text nodes of an HTML segment containing no scripts."""
    counts: dict[str, int] = {}
    parts = _TAG_SPLIT_RE.split(segment)
    for i, part in enumerate(parts):
        if not part or part.startswith("<"):
            continue  # tag or empty -> leave markup untouched
        redacted, c = redact_text(part, keep)
        parts[i] = redacted or part
        _merge_counts(counts, c)
    return "".join(parts), counts


def redact_html(html: str | None, keep: set[str] = frozenset()) -> tuple[str | None, dict[str, int]]:
    """Redact text nodes of an HTML document without breaking markup.

    * Tags/attributes are never modified.
    * Non-JSON-LD <script> and <style> contents are left untouched.
    * JSON-LD blocks keep all promo fields; only email/phone values inside
      them are redacted.
    """
    counts: dict[str, int] = {}
    if not html:
        return html, counts

    pieces: list[str] = []
    pos = 0
    for match in _SCRIPT_STYLE_RE.finditer(html):
        segment, seg_counts = _redact_markup_segment(html[pos : match.start()], keep)
        pieces.append(segment)
        _merge_counts(counts, seg_counts)

        block = match.group(0)
        open_tag = _JSONLD_OPEN_RE.match(block)
        if open_tag:
            close_idx = block.lower().rfind("</script")
            inner = block[open_tag.end() : close_idx]
            redacted_inner, inner_counts = redact_text(
                inner, keep, entities=_JSONLD_ENTITIES
            )
            block = (
                block[: open_tag.end()]
                + (redacted_inner or inner)
                + block[close_idx:]
            )
            _merge_counts(counts, inner_counts)
        pieces.append(block)
        pos = match.end()

    segment, seg_counts = _redact_markup_segment(html[pos:], keep)
    pieces.append(segment)
    _merge_counts(counts, seg_counts)
    return "".join(pieces), counts


# ---------------------------------------------------------------------------
# Email-level entry point.
# ---------------------------------------------------------------------------

def _keep_addresses(email: InboundEmail) -> set[str]:
    keep: set[str] = set()
    sender = (email.FromFull or {}).get("Email")
    if sender:
        keep.add(str(sender).strip().lower())
    for recipient in email.ToFull or []:
        addr = (recipient or {}).get("Email")
        if addr:
            keep.add(str(addr).strip().lower())
    return keep


def redact_email(email: InboundEmail) -> tuple[InboundEmail, dict[str, int]]:
    """Redact TextBody and HtmlBody of an InboundEmail.

    Sender and recipient addresses are preserved everywhere (``keep``).
    Returns a NEW InboundEmail (the input is not mutated) plus merged counts
    per entity type.
    """
    keep = _keep_addresses(email)
    counts: dict[str, int] = {}

    new_text, text_counts = redact_text(email.TextBody, keep)
    _merge_counts(counts, text_counts)

    new_html, html_counts = redact_html(email.HtmlBody, keep)
    _merge_counts(counts, html_counts)

    redacted = email.model_copy(
        update={"TextBody": new_text, "HtmlBody": new_html}
    )
    return redacted, counts
