"""GLiNER2 NER extraction of reward fields from email text.

Public interface (see backend/extraction/README.md and shared contracts):

    extract_fields(text: str) -> FieldCandidates

The model (``fastino/gliner2-base-v1``) is lazily loaded once per process,
CPU-only. If the ``gliner2`` package is missing or the model cannot be
downloaded/loaded, ``extract_fields`` logs a warning and returns an empty
``FieldCandidates`` — it never raises.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Optional

from .types import FieldCandidates, FieldValue

logger = logging.getLogger(__name__)

MODEL_ID = "fastino/gliner2-base-v1"
SOURCE = "gliner"

# Entity labels with descriptions (descriptions improve GLiNER2 accuracy).
LABELS: dict[str, str] = {
    "merchant": "Name of the store, brand, or merchant offering the reward or discount",
    "discount_value": "The discount or reward value, such as '10% off', '$10 off', or 'FREE Guacamole'",
    "min_spend": "Minimum purchase or spend required to use the offer, such as '$50' or 'orders over $25'",
    "max_discount": "Maximum discount cap, such as 'up to $25 off'",
    "expiry": "Expiration date or deadline of the offer, such as 'October 20, 2026' or 'this Sunday'",
    "starts": "Start date when the offer becomes valid, such as 'starting October 15'",
    "code": "Promo, coupon, or reward code to enter at checkout, such as 'SAVE10' or 'FREEGUAC'",
    "stackable": "Statement about combining this offer with other offers, such as 'cannot be combined with other offers' or 'stackable with other offers'",
    "exclusions": "Items, brands, or categories excluded from the offer, such as 'gift cards' or 'clearance items'",
}

# Word-level chunking for long emails (encoder window is ~512 subword tokens).
CHUNK_WORDS = 300
CHUNK_OVERLAP_WORDS = 50
MAX_CHUNKS = 12  # hard cap: ~3600 words is plenty for any marketing email

# Phrases indicating the offer can NOT be combined with others.
_NON_STACKABLE_MARKERS = (
    "cannot be combined",
    "can't be combined",
    "cannot combine",
    "not combinable",
    "may not be combined",
    "not valid with",
    "not valid in combination",
    "no other offer",
    "no other discount",
    "one offer per",
    "one coupon per",
    "not stackable",
    "excludes other offers",
)
# Phrases indicating the offer CAN be combined with others.
_STACKABLE_MARKERS = (
    "can be combined",
    "stackable",
    "stack with",
    "combine with other",
    "combined with other",
    "valid with other",
)

_model_lock = threading.Lock()
_model: Any = None
_model_load_failed = False


def _get_model() -> Any | None:
    """Lazily load the GLiNER2 model once (module-level singleton), CPU-only.

    Returns None (and logs a warning) if gliner2 is not installed or the
    model cannot be downloaded/loaded.
    """
    global _model, _model_load_failed
    if _model is not None:
        return _model
    if _model_load_failed:
        return None
    with _model_lock:
        if _model is not None:
            return _model
        if _model_load_failed:
            return None
        try:
            from gliner2 import GLiNER2

            _model = GLiNER2.from_pretrained(MODEL_ID, map_location="cpu")
        except ImportError:
            _model_load_failed = True
            logger.warning(
                "gliner2 is not installed; GLiNER extraction disabled. "
                "Install backend/extraction/requirements/gliner.txt."
            )
        except Exception:
            _model_load_failed = True
            logger.warning(
                "Failed to load GLiNER2 model %s; GLiNER extraction disabled.",
                MODEL_ID,
                exc_info=True,
            )
        return _model


def _chunk_text(text: str) -> list[str]:
    """Split text into overlapping word chunks that fit the model window."""
    words = text.split()
    if len(words) <= CHUNK_WORDS:
        return [text] if text.strip() else []
    chunks: list[str] = []
    step = CHUNK_WORDS - CHUNK_OVERLAP_WORDS
    for start in range(0, len(words), step):
        chunks.append(" ".join(words[start : start + CHUNK_WORDS]))
        if len(chunks) >= MAX_CHUNKS or start + CHUNK_WORDS >= len(words):
            break
    return chunks


def _best_spans(text: str, model: Any) -> dict[str, list[tuple[str, float]]]:
    """Run the model over chunks and collect (text, confidence) spans per label."""
    spans: dict[str, list[tuple[str, float]]] = {label: [] for label in LABELS}
    for chunk in _chunk_text(text):
        try:
            result = model.extract_entities(chunk, LABELS, include_confidence=True)
        except Exception:
            logger.warning("GLiNER2 extraction failed on a chunk; skipping.", exc_info=True)
            continue
        for label, entities in (result.get("entities") or {}).items():
            if label not in spans:
                continue
            for ent in entities:
                if isinstance(ent, dict):
                    value = str(ent.get("text", "")).strip()
                    confidence = float(ent.get("confidence", 0.0))
                else:  # plain string fallback if confidence isn't returned
                    value, confidence = str(ent).strip(), 0.5
                if value:
                    spans[label].append((value, min(max(confidence, 0.0), 1.0)))
    return spans


def _pick_best(candidates: list[tuple[str, float]]) -> Optional[FieldValue]:
    """Keep the highest-scoring span for a field."""
    if not candidates:
        return None
    value, confidence = max(candidates, key=lambda c: c[1])
    return FieldValue(value=value, confidence=confidence, source=SOURCE)


def _stackable_from_span(candidates: list[tuple[str, float]]) -> Optional[FieldValue]:
    """Map a combination-policy phrase to a 'true'/'false' FieldValue."""
    best = _pick_best(candidates)
    if best is None:
        return None
    phrase = best.value.lower()
    if any(marker in phrase for marker in _NON_STACKABLE_MARKERS):
        verdict = "false"
    elif any(marker in phrase for marker in _STACKABLE_MARKERS):
        verdict = "true"
    else:
        # A combination statement was detected but polarity is unclear;
        # default to non-stackable per contract guidance.
        verdict = "false"
    return FieldValue(value=verdict, confidence=best.confidence, source=SOURCE)


def _exclusion_values(candidates: list[tuple[str, float]]) -> list[FieldValue]:
    """Deduplicate exclusion spans (case-insensitive), keeping best score each."""
    best_by_text: dict[str, tuple[str, float]] = {}
    for value, confidence in candidates:
        key = value.lower()
        if key not in best_by_text or confidence > best_by_text[key][1]:
            best_by_text[key] = (value, confidence)
    return [
        FieldValue(value=value, confidence=confidence, source=SOURCE)
        for value, confidence in sorted(best_by_text.values(), key=lambda c: -c[1])
    ]


def extract_fields(text: str) -> FieldCandidates:
    """Extract reward fields from plain email text using GLiNER2.

    Never raises: returns an empty FieldCandidates if the model is
    unavailable or the text is empty.
    """
    if not text or not text.strip():
        return FieldCandidates()
    model = _get_model()
    if model is None:
        return FieldCandidates()

    spans = _best_spans(text, model)
    return FieldCandidates(
        merchant=_pick_best(spans["merchant"]),
        discount_value=_pick_best(spans["discount_value"]),
        min_spend=_pick_best(spans["min_spend"]),
        max_discount=_pick_best(spans["max_discount"]),
        expiry=_pick_best(spans["expiry"]),
        starts=_pick_best(spans["starts"]),
        code=_pick_best(spans["code"]),
        stackable=_stackable_from_span(spans["stackable"]),
        exclusions=_exclusion_values(spans["exclusions"]),
    )
