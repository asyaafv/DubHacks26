"""Extraction pipeline orchestrator (Agent 6: integrator).

extract_rewards(email, user_id) runs the full cascade:

    clean_email -> classify_email -> extract_markup
        -> (if markup missing/incomplete) extract_fields (GLiNER2) + extract_fields_regex
        -> merge_candidates -> normalize -> classify_merchant -> Reward objects

Every sibling module (clean, classify, markup, gliner_extract, regex_extract,
normalize, merchants) is being written IN PARALLEL on other branches, so each
import is defensive: if the real module is missing we fall back to a minimal
built-in implementation defined in this file (clearly marked FALLBACK). When
the real modules land on main they automatically take over with no edits here.

Per-stage timings (ms) are collected for every run; use run_pipeline() to get
them alongside the rewards, or extract_rewards() for the plain contract.
"""
from __future__ import annotations

import html as _html
import json
import logging
import re
import time
from dataclasses import dataclass, field as _dc_field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Optional
from uuid import UUID, uuid4

from dateutil import parser as _dateutil_parser

from backend.app.schemas import (
    ClassifyMerchantResult,
    FieldConfidence,
    InboundEmail,
    Reward,
    RewardKind,
    RewardSource,
    RewardStatus,
)
from backend.extraction.types import CleanedEmail, FieldCandidates, FieldValue

logger = logging.getLogger("lapse.extraction.pipeline")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SEED_MERCHANTS_PATH = _REPO_ROOT / "shared" / "seed" / "seed_merchants.json"

# Tracks which stages are running on built-in fallbacks (real module missing).
FALLBACKS_ACTIVE: list[str] = []


# =============================================================================
# FALLBACK: clean.py  (clean_email + parse_eml)
# =============================================================================

def _fallback_strip_html(raw_html: str) -> str:
    """FALLBACK: basic HTML -> text (no bs4, stdlib only)."""
    text = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", raw_html)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</h[1-6]>|</li>|</tr>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _fallback_clean_email(email: InboundEmail) -> CleanedEmail:
    """FALLBACK for clean.clean_email."""
    sender = str(email.FromFull.get("Email", "") or "")
    sender_domain = sender.split("@")[-1].lower().strip() if "@" in sender else ""
    try:
        from email.utils import parsedate_to_datetime

        received_at = parsedate_to_datetime(email.Date)
    except (TypeError, ValueError):
        try:
            received_at = datetime.fromisoformat(email.Date)
        except ValueError:
            received_at = datetime.now(timezone.utc)
    text = (email.TextBody or "").strip()
    if not text and email.HtmlBody:
        text = _fallback_strip_html(email.HtmlBody)
    return CleanedEmail(
        subject=email.Subject or "",
        text=text,
        html=email.HtmlBody,
        sender=sender,
        sender_domain=sender_domain,
        received_at=received_at,
    )


def _fallback_parse_eml(raw: bytes) -> InboundEmail:
    """FALLBACK for clean.parse_eml (stdlib email module)."""
    from email import message_from_bytes
    from email.policy import default as _default_policy
    from email.utils import parseaddr

    msg = message_from_bytes(raw, policy=_default_policy)
    from_name, from_email = parseaddr(str(msg.get("From", "")))
    to_name, to_email = parseaddr(str(msg.get("To", "")))
    text_body: Optional[str] = None
    html_body: Optional[str] = None
    for part in msg.walk():
        ctype = part.get_content_type()
        if part.is_multipart():
            continue
        try:
            content = part.get_content()
        except Exception:  # noqa: BLE001 - malformed part, skip it
            continue
        if ctype == "text/plain" and text_body is None:
            text_body = content
        elif ctype == "text/html" and html_body is None:
            html_body = content
    message_id = str(msg.get("Message-ID", "")).strip().strip("<>") or f"local-{uuid4()}"
    return InboundEmail(
        MessageID=message_id,
        FromFull={"Email": from_email, "Name": from_name},
        ToFull=[{"Email": to_email, "Name": to_name}],
        Subject=str(msg.get("Subject", "")),
        TextBody=text_body,
        HtmlBody=html_body,
        Date=str(msg.get("Date", "")),
    )


try:
    from backend.extraction.clean import clean_email, parse_eml
except ImportError:
    clean_email = _fallback_clean_email
    parse_eml = _fallback_parse_eml
    FALLBACKS_ACTIVE.append("clean")


# =============================================================================
# FALLBACK: classify.py  (classify_email)
# =============================================================================

_RECEIPT_RE = re.compile(
    r"(?i)\b(order\s*(#|number|total)|has shipped|your order|receipt|invoice|"
    r"tracking number|track your package|delivered|arriving)\b"
)
_REWARD_RE = re.compile(
    r"(?i)(\d{1,3}\s*%\s*off|\$\s*\d+(\.\d{2})?\s*off|\bvoucher\b|\bcoupon\b|"
    r"\breward\b|you.ve earned|\bfree\s+[a-z]|\bpromo code\b|\bcode[:\s]+[A-Z0-9]{4,})"
)
_PROMO_RE = re.compile(r"(?i)\b(sale|new arrivals|exclusive|member|deal)\b")


def _fallback_classify_email(subject: str, text: str) -> tuple[str, float]:
    """FALLBACK for classify.classify_email (keyword heuristic, no SetFit)."""
    blob = f"{subject}\n{text[:2000]}"
    if _RECEIPT_RE.search(subject) or len(_RECEIPT_RE.findall(blob)) >= 2:
        return "receipt", 0.8
    reward_hits = len(_REWARD_RE.findall(blob))
    if reward_hits >= 2:
        return "reward", 0.8
    if reward_hits == 1:
        return "reward", 0.65
    if _PROMO_RE.search(blob):
        return "promo", 0.6
    return "other", 0.5


try:
    from backend.extraction.classify import classify_email
except ImportError:
    classify_email = _fallback_classify_email
    FALLBACKS_ACTIVE.append("classify")


# =============================================================================
# FALLBACK: markup.py  (extract_markup - schema.org JSON-LD)
# =============================================================================

_JSONLD_SCRIPT_RE = re.compile(
    r'(?is)<script[^>]*type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>'
)
_OFFER_TYPES = {"DiscountOffer", "Offer", "PromotionCard"}


def _iter_jsonld_nodes(obj: Any):
    if isinstance(obj, dict):
        yield obj
        for value in obj.values():
            yield from _iter_jsonld_nodes(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_jsonld_nodes(item)


def _fallback_extract_markup(html_body: Optional[str]) -> Optional[FieldCandidates]:
    """FALLBACK for markup.extract_markup (stdlib JSON-LD scrape, no extruct)."""
    if not html_body:
        return None
    offers: list[dict] = []
    for block in _JSONLD_SCRIPT_RE.findall(html_body):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        for node in _iter_jsonld_nodes(data):
            if node.get("@type") in _OFFER_TYPES:
                offers.append(node)
    if not offers:
        return None

    offer = offers[0]
    src = "email_jsonld"
    conf = 0.95
    fc = FieldCandidates()

    seller = offer.get("seller") or offer.get("offeredBy") or {}
    if isinstance(seller, dict) and seller.get("name"):
        fc.merchant = FieldValue(str(seller["name"]), conf, src)

    code = offer.get("discountCode") or offer.get("couponCode")
    if code:
        fc.code = FieldValue(str(code), conf, src)

    discount = offer.get("discount")
    discount_type = str(offer.get("discountType", "")).lower()
    price_spec = offer.get("priceSpecification") or {}
    if discount:
        if "percent" in discount_type:
            fc.discount_value = FieldValue(f"{discount}% off", conf, src)
        else:
            fc.discount_value = FieldValue(f"${discount} off", conf, src)
    elif isinstance(price_spec, dict) and price_spec.get("price"):
        fc.discount_value = FieldValue(f"${price_spec['price']} off", conf, src)

    if isinstance(price_spec, dict) and price_spec.get("maxPrice"):
        fc.max_discount = FieldValue(str(price_spec["maxPrice"]), conf, src)

    etv = offer.get("eligibleTransactionVolume") or {}
    min_price = (etv.get("minPrice") if isinstance(etv, dict) else None) or offer.get("minPrice")
    if min_price:
        fc.min_spend = FieldValue(str(min_price), conf, src)

    if offer.get("validThrough"):
        fc.expiry = FieldValue(str(offer["validThrough"]), conf, src)
    if offer.get("validFrom"):
        fc.starts = FieldValue(str(offer["validFrom"]), conf, src)

    return fc


try:
    from backend.extraction.markup import extract_markup
except ImportError:
    extract_markup = _fallback_extract_markup
    FALLBACKS_ACTIVE.append("markup")


# =============================================================================
# FALLBACK: gliner_extract.py  (extract_fields)
# =============================================================================

def _fallback_extract_fields(text: str) -> FieldCandidates:
    """FALLBACK for gliner_extract.extract_fields.

    No GLiNER model available here, so this contributes nothing; the regex
    extractor carries the load until the real module lands.
    """
    return FieldCandidates()


try:
    from backend.extraction.gliner_extract import extract_fields
except ImportError:
    extract_fields = _fallback_extract_fields
    FALLBACKS_ACTIVE.append("gliner")


# =============================================================================
# FALLBACK: regex_extract.py  (extract_fields_regex)
# =============================================================================

_RX = {
    "percent": re.compile(r"(?i)(\d{1,3})\s*%\s*off"),
    "amount": re.compile(r"(?i)\$\s*(\d+(?:\.\d{2})?)\s*off"),
    "free_item": re.compile(r"(?i)\bfree\s+([A-Za-z][A-Za-z']*(?:\s+[A-Za-z][A-Za-z']*)?)"),
    "bogo": re.compile(r"(?i)\b(bogo|buy one,? get one)\b"),
    "code": re.compile(r"(?i)\b(?:code|coupon|promo)\s*[:\s]\s*([A-Z0-9]{4,20})\b"),
    "min_spend": re.compile(
        r"(?i)(?:min(?:imum)?\s*purchase|minimum|spend)\s*[:\s]\s*\$\s*(\d+(?:\.\d{2})?)"
    ),
    "max_discount": re.compile(r"(?i)max(?:imum)?\s*discount\s*[:\s]\s*\$\s*(\d+(?:\.\d{2})?)"),
    "expiry": re.compile(
        r"(?i)(?:valid\s+through|valid\s+until|expires?|ends?)\s*[:\s]\s*"
        r"([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})"
    ),
    "exclusions": re.compile(r"(?i)exclu(?:des?|sions?)\s*[:\s]\s*([^\n]+)"),
    "stackable": re.compile(r"(?i)\b(stackable|can be combined|combine[sd]? with other)\b"),
}
_REGEX_CONF = 0.6


def _fallback_extract_fields_regex(text: str) -> FieldCandidates:
    """FALLBACK for regex_extract.extract_fields_regex."""
    fc = FieldCandidates()
    src = "regex"

    if m := _RX["percent"].search(text):
        fc.discount_value = FieldValue(f"{m.group(1)}% off", _REGEX_CONF, src)
    elif m := _RX["amount"].search(text):
        fc.discount_value = FieldValue(f"${m.group(1)} off", _REGEX_CONF, src)
    elif _RX["bogo"].search(text):
        fc.discount_value = FieldValue("bogo", _REGEX_CONF, src)
    elif m := _RX["free_item"].search(text):
        fc.discount_value = FieldValue(f"free {m.group(1).strip()}", _REGEX_CONF, src)

    if m := _RX["code"].search(text):
        fc.code = FieldValue(m.group(1), _REGEX_CONF, src)
    if m := _RX["min_spend"].search(text):
        fc.min_spend = FieldValue(m.group(1), _REGEX_CONF, src)
    if m := _RX["max_discount"].search(text):
        fc.max_discount = FieldValue(m.group(1), _REGEX_CONF, src)
    if m := _RX["expiry"].search(text):
        fc.expiry = FieldValue(m.group(1), _REGEX_CONF, src)
    if m := _RX["exclusions"].search(text):
        fc.exclusions = [FieldValue(m.group(1).strip(), _REGEX_CONF, src)]
    if _RX["stackable"].search(text):
        fc.stackable = FieldValue("true", _REGEX_CONF, src)

    return fc


try:
    from backend.extraction.regex_extract import extract_fields_regex
except ImportError:
    extract_fields_regex = _fallback_extract_fields_regex
    FALLBACKS_ACTIVE.append("regex")


# =============================================================================
# FALLBACK: normalize.py  (merge_candidates + normalize)
# =============================================================================

_SOURCE_PRIORITY = {"email_jsonld": 3, "gliner": 2, "regex": 1}
_FIELD_NAMES = (
    "merchant",
    "discount_value",
    "min_spend",
    "max_discount",
    "expiry",
    "starts",
    "code",
    "stackable",
)


def _fallback_merge_candidates(*candidates: Optional[FieldCandidates]) -> FieldCandidates:
    """FALLBACK for normalize.merge_candidates.

    Per field: highest source priority wins (email_jsonld > gliner > regex),
    ties broken by confidence.
    """
    merged = FieldCandidates()
    cands = [c for c in candidates if c is not None]
    for name in _FIELD_NAMES:
        best: Optional[FieldValue] = None
        for cand in cands:
            fv: Optional[FieldValue] = getattr(cand, name)
            if fv is None or not str(fv.value).strip():
                continue
            if best is None or (
                _SOURCE_PRIORITY.get(fv.source, 0),
                fv.confidence,
            ) > (_SOURCE_PRIORITY.get(best.source, 0), best.confidence):
                best = fv
        setattr(merged, name, best)
    for cand in cands:
        if cand.exclusions:
            merged.exclusions = cand.exclusions
            break
    return merged


def _parse_decimal(text: str) -> Optional[Decimal]:
    cleaned = re.sub(r"[^0-9.]", "", str(text))
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def _parse_dt(text: str, email_date: datetime) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(text))
    except ValueError:
        pass
    try:
        base = email_date if email_date.tzinfo is None else email_date.replace(tzinfo=None)
        return _dateutil_parser.parse(str(text), fuzzy=True, default=base)
    except (ValueError, OverflowError):
        return None


def _fallback_normalize(c: FieldCandidates, email_date: datetime) -> dict:
    """FALLBACK for normalize.normalize."""
    out: dict[str, Any] = {
        "kind": None,
        "value": None,
        "currency": "USD",
        "min_spend": None,
        "max_discount": None,
        "code": None,
        "expires_at": None,
        "starts_at": None,
        "stackable": False,
        "exclusions": [],
        "field_confidence": {},
    }
    conf = out["field_confidence"]

    if c.discount_value:
        raw = c.discount_value.value.strip().lower()
        if m := re.search(r"(\d{1,3}(?:\.\d+)?)\s*%", raw):
            out["kind"] = "percent_off"
            out["value"] = Decimal(m.group(1))
        elif m := re.search(r"\$\s*(\d+(?:\.\d{2})?)", raw):
            out["kind"] = "amount_off"
            out["value"] = Decimal(m.group(1))
        elif "bogo" in raw or "buy one" in raw:
            out["kind"] = "bogo"
            out["value"] = Decimal("0")
        elif raw.startswith("free"):
            out["kind"] = "free_item"
            out["value"] = Decimal("0")
        elif "cashback" in raw or "cash back" in raw:
            out["kind"] = "cashback"
            out["value"] = _parse_decimal(raw) or Decimal("0")
        elif "point" in raw:
            out["kind"] = "points"
            out["value"] = _parse_decimal(raw) or Decimal("0")
        if out["value"] is not None:
            conf["value"] = c.discount_value.confidence

    if c.min_spend and (dec := _parse_decimal(c.min_spend.value)) is not None:
        out["min_spend"] = dec
        conf["min_spend"] = c.min_spend.confidence
    if c.max_discount and (dec := _parse_decimal(c.max_discount.value)) is not None:
        out["max_discount"] = dec
    if c.code:
        out["code"] = c.code.value.strip().upper()
        conf["code"] = c.code.confidence
    if c.expiry and (dt := _parse_dt(c.expiry.value, email_date)) is not None:
        out["expires_at"] = dt
        conf["expires_at"] = c.expiry.confidence
    if c.starts and (dt := _parse_dt(c.starts.value, email_date)) is not None:
        out["starts_at"] = dt
    if c.stackable:
        out["stackable"] = c.stackable.value.strip().lower() in ("true", "yes", "1")
    for excl in c.exclusions:
        out["exclusions"].extend(p.strip() for p in excl.value.split(",") if p.strip())

    return out


try:
    from backend.extraction.normalize import merge_candidates, normalize
except ImportError:
    merge_candidates = _fallback_merge_candidates
    normalize = _fallback_normalize
    FALLBACKS_ACTIVE.append("normalize")


# =============================================================================
# FALLBACK: merchants.py  (classify_merchant)
# =============================================================================

_seed_merchants_cache: Optional[list[dict]] = None


def _load_seed_merchants() -> list[dict]:
    global _seed_merchants_cache
    if _seed_merchants_cache is None:
        try:
            data = json.loads(_SEED_MERCHANTS_PATH.read_text())
            _seed_merchants_cache = data.get("merchants", [])
        except (OSError, json.JSONDecodeError):
            _seed_merchants_cache = []
    return _seed_merchants_cache


def _fallback_classify_merchant(
    name: Optional[str] = None,
    domain: Optional[str] = None,
    sender_domain: Optional[str] = None,
) -> ClassifyMerchantResult:
    """FALLBACK for merchants.classify_merchant (seed_merchants.json lookup)."""
    lookup_domain = (domain or sender_domain or "").lower().strip()
    merchants = _load_seed_merchants()

    for m in merchants:
        domains = [m["domain"], *m.get("aliases", [])]
        if lookup_domain and any(
            lookup_domain == d or lookup_domain.endswith("." + d) for d in domains
        ):
            return ClassifyMerchantResult(
                domain=lookup_domain,
                merchant_id=UUID(m["id"]),
                merchant_name=m["name"],
                category=m["category"],
                mcc=m["mcc"],
                confidence=0.95,
                is_new=False,
            )

    if name:
        name_lc = name.lower().strip()
        for m in merchants:
            seed_lc = m["name"].lower()
            if seed_lc in name_lc or name_lc in seed_lc:
                return ClassifyMerchantResult(
                    domain=lookup_domain or m["domain"],
                    merchant_id=UUID(m["id"]),
                    merchant_name=m["name"],
                    category=m["category"],
                    mcc=m["mcc"],
                    confidence=0.85,
                    is_new=False,
                )

    inferred = name or (lookup_domain.split(".")[0].title() if lookup_domain else "Unknown Store")
    return ClassifyMerchantResult(
        domain=lookup_domain,
        merchant_id=None,
        merchant_name=inferred,
        category="Miscellaneous Retail",
        mcc="5999",
        confidence=0.3,
        is_new=True,
    )


try:
    from backend.extraction.merchants import classify_merchant
except ImportError:
    classify_merchant = _fallback_classify_merchant
    FALLBACKS_ACTIVE.append("merchants")


# =============================================================================
# PIPELINE
# =============================================================================

_SOURCE_MAP = {
    "email_jsonld": RewardSource.email_jsonld,
    "gliner": RewardSource.gliner,
    "regex": RewardSource.regex,
}
# Weighted mean over the key fields per the task spec.
_OVERALL_WEIGHTS = {"value": 0.5, "merchant": 0.3, "expires_at": 0.2}


@dataclass
class PipelineResult:
    rewards: list[Reward]
    classification: str
    classification_confidence: float
    timings_ms: dict[str, float]
    fallbacks_active: list[str] = _dc_field(default_factory=lambda: list(FALLBACKS_ACTIVE))


def _markup_incomplete(fc: Optional[FieldCandidates]) -> bool:
    """Markup counts as incomplete if any key field is missing."""
    return (
        fc is None
        or fc.discount_value is None
        or fc.merchant is None
        or fc.expiry is None
        or fc.code is None
    )


def _call_merge(candidates: list[FieldCandidates]) -> FieldCandidates:
    """Tolerate either merge_candidates(*cands) or merge_candidates(cands)."""
    try:
        return merge_candidates(*candidates)
    except TypeError:
        return merge_candidates(candidates)


def run_pipeline(email: InboundEmail, user_id: UUID | str) -> PipelineResult:
    """Full pipeline run with per-stage timings (ms)."""
    timings: dict[str, float] = {}
    total_start = time.perf_counter()

    def timed(stage: str, fn, *args, **kwargs):
        start = time.perf_counter()
        result = fn(*args, **kwargs)
        timings[stage] = round((time.perf_counter() - start) * 1000, 3)
        return result

    cleaned: CleanedEmail = timed("clean_ms", clean_email, email)

    label, label_conf = timed("classify_ms", classify_email, cleaned.subject, cleaned.text)
    if label in ("receipt", "other"):
        timings["total_ms"] = round((time.perf_counter() - total_start) * 1000, 3)
        logger.info("email %s classified as %r; skipping extraction", email.MessageID, label)
        return PipelineResult([], label, label_conf, timings)

    markup_fc: Optional[FieldCandidates] = timed("markup_ms", extract_markup, cleaned.html)

    candidates: list[FieldCandidates] = [markup_fc] if markup_fc else []
    if _markup_incomplete(markup_fc):
        candidates.append(timed("gliner_ms", extract_fields, cleaned.text))
        candidates.append(timed("regex_ms", extract_fields_regex, cleaned.text))

    merged: FieldCandidates = timed("merge_ms", _call_merge, candidates)
    norm: dict = timed("normalize_ms", normalize, merged, cleaned.received_at)

    merchant: ClassifyMerchantResult = timed(
        "merchant_ms",
        classify_merchant,
        name=merged.merchant.value if merged.merchant else None,
        sender_domain=cleaned.sender_domain,
    )

    build_start = time.perf_counter()
    rewards: list[Reward] = []
    if norm.get("kind") is not None and norm.get("value") is not None:
        field_conf_in: dict[str, float] = dict(norm.get("field_confidence") or {})
        field_conf_in["merchant"] = merchant.confidence
        field_confidence = FieldConfidence(
            value=field_conf_in.get("value", 0.0),
            expires_at=field_conf_in.get("expires_at", 0.0),
            code=field_conf_in.get("code", 0.0),
            min_spend=field_conf_in.get("min_spend", 0.0),
            merchant=field_conf_in.get("merchant", 0.0),
        )
        overall = round(
            sum(
                _OVERALL_WEIGHTS[name] * getattr(field_confidence, name)
                for name in _OVERALL_WEIGHTS
            ),
            4,
        )
        value_missing = norm.get("value") is None
        merchant_missing = merchant.is_new or not merchant.merchant_name
        status = (
            RewardStatus.needs_review
            if overall < 0.6 or value_missing or merchant_missing
            else RewardStatus.active
        )
        winning_source = merged.discount_value.source if merged.discount_value else "regex"
        rewards.append(
            Reward(
                id=uuid4(),
                user_id=UUID(str(user_id)),
                merchant_id=merchant.merchant_id,
                merchant_name=merchant.merchant_name,
                category=merchant.category,
                mcc=merchant.mcc,
                kind=RewardKind(norm["kind"]),
                value=norm["value"],
                currency=norm.get("currency") or "USD",
                min_spend=norm.get("min_spend"),
                max_discount=norm.get("max_discount"),
                code=norm.get("code"),
                expires_at=norm.get("expires_at"),
                starts_at=norm.get("starts_at"),
                stackable=bool(norm.get("stackable", False)),
                exclusions=list(norm.get("exclusions") or []),
                source=_SOURCE_MAP.get(winning_source, RewardSource.regex),
                source_email_id=email.MessageID,
                field_confidence=field_confidence,
                overall_confidence=overall,
                status=status,
            )
        )
    timings["build_ms"] = round((time.perf_counter() - build_start) * 1000, 3)
    timings["total_ms"] = round((time.perf_counter() - total_start) * 1000, 3)

    logger.info(
        "email %s -> %d reward(s) in %.1f ms (stages: %s)",
        email.MessageID,
        len(rewards),
        timings["total_ms"],
        timings,
    )
    return PipelineResult(rewards, label, label_conf, timings)


def extract_rewards(email: InboundEmail, user_id: UUID | str) -> list[Reward]:
    """Shared-interface entry point: InboundEmail -> list[Reward]."""
    return run_pipeline(email, user_id).rewards
