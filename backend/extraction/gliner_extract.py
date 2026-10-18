"""GLiNER2-based entity extraction for reward emails.

Uses GLiNER2 (fastino/gliner2-base-v1) for zero-shot NER extraction.
Provides lazy, thread-safe singleton model loading with warmup support.
Falls back gracefully if model unavailable.
"""
from __future__ import annotations

import re
import threading
from typing import Optional

from backend.extraction.types import FieldCandidates, FieldValue


class ExtractionUnavailable(Exception):
    """Raised when GLiNER2 model cannot be loaded or is not installed."""
    pass


_model = None
_model_lock = threading.Lock()
_model_error: Optional[Exception] = None

MODEL_NAME = "fastino/gliner2-base-v1"
SOURCE = "gliner"
MAX_CHUNK_SIZE = 2000


ENTITY_LABELS = {
    "merchant": "Name of a store, brand, or company offering the reward or discount",
    "discount_value": "Discount amount like '10% off', '$15 off', '2x points', 'free drink', 'BOGO'",
    "min_spend": "Minimum purchase requirement like 'spend $50', 'minimum $25 purchase'",
    "max_discount": "Maximum discount cap like 'up to $20 off', 'max $50 savings'",
    "expiry": "Expiration date phrase like 'October 20', 'Sunday', 'expires 10/31'",
    "starts": "Start date phrase like 'valid from October 1', 'starting Monday'",
    "code": "Promo code or coupon code like 'SAVE20', 'FREESHIP', alphanumeric codes",
    "stackable_signal": "Phrase indicating stackability like 'can be combined', 'cannot be combined with other offers'",
    "exclusion": "Excluded items or categories like 'excludes clearance', 'not valid on gift cards'",
}


def _load_model():
    """Load the GLiNER2 model. Thread-safe, lazy initialization."""
    global _model, _model_error
    
    if _model is not None:
        return _model
    if _model_error is not None:
        raise _model_error
    
    with _model_lock:
        if _model is not None:
            return _model
        if _model_error is not None:
            raise _model_error
        
        try:
            from gliner2 import AutoExtractor
            _model = AutoExtractor.from_pretrained(MODEL_NAME)
            return _model
        except ImportError as e:
            _model_error = ExtractionUnavailable(
                f"gliner2 package not installed. Install with: pip install 'gliner2[local]'. Error: {e}"
            )
            raise _model_error
        except Exception as e:
            _model_error = ExtractionUnavailable(
                f"Failed to load GLiNER2 model '{MODEL_NAME}': {e}"
            )
            raise _model_error


def warmup() -> None:
    """Pre-load the model to avoid cold-start latency on first extraction.
    
    Raises:
        ExtractionUnavailable: If the model cannot be loaded.
    """
    model = _load_model()
    model.extract_entities("Test warmup text.", list(ENTITY_LABELS.keys()))


def _split_into_chunks(text: str, max_size: int = MAX_CHUNK_SIZE) -> list[str]:
    """Split text on paragraph boundaries, keeping chunks under max_size.
    
    Returns list of text chunks, each <= max_size characters.
    """
    if len(text) <= max_size:
        return [text]
    
    paragraphs = re.split(r'\n\s*\n|\n{2,}', text)
    
    chunks = []
    current_chunk = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        if len(para) > max_size:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            
            sentences = re.split(r'(?<=[.!?])\s+', para)
            for sentence in sentences:
                if len(current_chunk) + len(sentence) + 1 <= max_size:
                    current_chunk = f"{current_chunk} {sentence}".strip() if current_chunk else sentence
                else:
                    if current_chunk:
                        chunks.append(current_chunk)
                    if len(sentence) > max_size:
                        for i in range(0, len(sentence), max_size):
                            chunks.append(sentence[i:i+max_size])
                        current_chunk = ""
                    else:
                        current_chunk = sentence
        elif len(current_chunk) + len(para) + 2 <= max_size:
            current_chunk = f"{current_chunk}\n\n{para}" if current_chunk else para
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = para
    
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks if chunks else [text[:max_size]]


def _parse_stackable(signal_text: str) -> str:
    """Parse stackable signal text into 'true' or 'false'."""
    signal_lower = signal_text.lower()
    
    negative_patterns = [
        "cannot be combined",
        "can't be combined",
        "not combinable",
        "not stackable",
        "cannot stack",
        "excludes other",
        "not valid with other",
        "one per",
        "limit one",
    ]
    
    for pattern in negative_patterns:
        if pattern in signal_lower:
            return "false"
    
    positive_patterns = [
        "can be combined",
        "stackable",
        "combine with",
        "stack with",
        "use with other",
    ]
    
    for pattern in positive_patterns:
        if pattern in signal_lower:
            return "true"
    
    return "true"


def extract_fields(text: str) -> FieldCandidates:
    """Extract reward fields from text using GLiNER2.
    
    Args:
        text: Email text content to extract from.
        
    Returns:
        FieldCandidates with extracted fields and confidence scores.
        
    Raises:
        ExtractionUnavailable: If GLiNER2 is not available.
    """
    model = _load_model()
    
    chunks = _split_into_chunks(text)
    
    all_entities: dict[str, list[dict]] = {label: [] for label in ENTITY_LABELS.keys()}
    
    for chunk in chunks:
        if not chunk.strip():
            continue
            
        result = model.extract_entities(
            chunk,
            ENTITY_LABELS,
            include_confidence=True,
        )
        
        entities = result.get("entities", {})
        for label, items in entities.items():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        all_entities[label].append(item)
                    elif isinstance(item, str):
                        all_entities[label].append({"text": item, "confidence": 0.8})
    
    def best_match(label: str) -> Optional[FieldValue]:
        """Get highest confidence match for a label."""
        matches = all_entities.get(label, [])
        if not matches:
            return None
        best = max(matches, key=lambda x: x.get("confidence", 0))
        return FieldValue(
            value=best.get("text", ""),
            confidence=best.get("confidence", 0.8),
            source=SOURCE,
        )
    
    stackable_value = None
    stackable_matches = all_entities.get("stackable_signal", [])
    if stackable_matches:
        best_stackable = max(stackable_matches, key=lambda x: x.get("confidence", 0))
        parsed = _parse_stackable(best_stackable.get("text", ""))
        stackable_value = FieldValue(
            value=parsed,
            confidence=best_stackable.get("confidence", 0.8),
            source=SOURCE,
        )
    
    exclusions_list = []
    for exc in all_entities.get("exclusion", []):
        exclusions_list.append(FieldValue(
            value=exc.get("text", ""),
            confidence=exc.get("confidence", 0.8),
            source=SOURCE,
        ))
    
    return FieldCandidates(
        merchant=best_match("merchant"),
        discount_value=best_match("discount_value"),
        min_spend=best_match("min_spend"),
        max_discount=best_match("max_discount"),
        expiry=best_match("expiry"),
        starts=best_match("starts"),
        code=best_match("code"),
        stackable=stackable_value,
        exclusions=exclusions_list,
    )
