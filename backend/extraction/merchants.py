"""
Merchant classification module.

Resolves merchant identity from name, domain, or sender_domain using a cascade:
1. Exact or registrable-domain match (confidence 0.99)
2. Fuzzy name match with rapidfuzz (confidence 0.80-0.95)
3. MiniLM embedding similarity (confidence based on cosine similarity)
4. Unknown fallback (low confidence)

The embed() function produces 384-dimensional normalized vectors suitable for
pgvector storage with cosine distance.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import tldextract
from rapidfuzz import fuzz, process

if TYPE_CHECKING:
    import numpy as np
    from sentence_transformers import SentenceTransformer

from backend.app.schemas import ClassifyMerchantResult

# Paths to data files
_DATA_DIR = Path(__file__).parent / "data"
_SEED_MERCHANTS_PATH = Path(__file__).parent.parent.parent / "shared" / "seed" / "seed_merchants.json"
_MCC_CODES_PATH = _DATA_DIR / "mcc_codes.json"

# Confidence thresholds
DOMAIN_MATCH_CONFIDENCE = 0.99
FUZZY_MIN_CONFIDENCE = 0.80
FUZZY_MAX_CONFIDENCE = 0.95
EMBEDDING_MIN_CONFIDENCE = 0.50

# Lazy-loaded model and embeddings cache
_model: "SentenceTransformer | None" = None
_merchant_embeddings: "np.ndarray | None" = None
_merchant_names: list[str] = []
_mcc_embeddings: "np.ndarray | None" = None
_mcc_codes: list[dict] = []


@lru_cache(maxsize=1)
def _load_merchants() -> list[dict]:
    """Load seed merchants from JSON file."""
    with open(_SEED_MERCHANTS_PATH) as f:
        data = json.load(f)
    return data.get("merchants", [])


@lru_cache(maxsize=1)
def _load_mcc_codes() -> list[dict]:
    """Load MCC codes from JSON file."""
    with open(_MCC_CODES_PATH) as f:
        data = json.load(f)
    return data.get("codes", [])


def _get_registrable_domain(domain: str) -> str:
    """
    Extract the registrable domain (domain + suffix) from a full domain.
    
    Examples:
        email.hollister.com -> hollisterco.com (needs alias check)
        mail.nike.com -> nike.com
        www.target.com -> target.com
    """
    extracted = tldextract.extract(domain.lower())
    if extracted.domain and extracted.suffix:
        return f"{extracted.domain}.{extracted.suffix}"
    return domain.lower()


def _normalize_domain(domain: str) -> str:
    """Normalize domain to lowercase, strip www prefix."""
    d = domain.lower().strip()
    if d.startswith("www."):
        d = d[4:]
    return d


def _build_domain_index() -> tuple[dict[str, dict], dict[str, dict]]:
    """
    Build lookup indices for domain matching.
    
    Returns:
        Tuple of (exact_index, registrable_index)
        - exact_index: Maps normalized full domains to merchants
        - registrable_index: Maps registrable domains to merchants (fallback)
    """
    merchants = _load_merchants()
    exact_index: dict[str, dict] = {}
    registrable_index: dict[str, dict] = {}
    
    for merchant in merchants:
        # Index primary domain
        primary_norm = _normalize_domain(merchant["domain"])
        exact_index[primary_norm] = merchant
        
        primary_registrable = _get_registrable_domain(merchant["domain"])
        if primary_registrable not in registrable_index:
            registrable_index[primary_registrable] = merchant
        
        # Index all aliases
        for alias in merchant.get("aliases", []):
            alias_norm = _normalize_domain(alias)
            if alias_norm not in exact_index:
                exact_index[alias_norm] = merchant
            
            alias_registrable = _get_registrable_domain(alias)
            if alias_registrable not in registrable_index:
                registrable_index[alias_registrable] = merchant
    
    return exact_index, registrable_index


@lru_cache(maxsize=1)
def _get_domain_indices() -> tuple[dict[str, dict], dict[str, dict]]:
    """Cached domain indices (exact, registrable)."""
    return _build_domain_index()


def _get_model() -> "SentenceTransformer":
    """
    Lazy-load the sentence-transformers model.
    
    Uses all-MiniLM-L6-v2 which produces 384-dimensional normalized vectors.
    The model is CPU-only to avoid GPU dependencies.
    """
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    return _model


def _ensure_embeddings_loaded() -> None:
    """
    Precompute and cache embeddings for merchants and MCC codes.
    Called lazily on first embedding-based lookup.
    """
    global _merchant_embeddings, _merchant_names, _mcc_embeddings, _mcc_codes
    
    if _merchant_embeddings is not None:
        return
    
    import numpy as np
    
    model = _get_model()
    merchants = _load_merchants()
    mcc_list = _load_mcc_codes()
    
    # Embed merchant names
    _merchant_names = [m["name"] for m in merchants]
    if _merchant_names:
        _merchant_embeddings = model.encode(_merchant_names, normalize_embeddings=True)
    else:
        _merchant_embeddings = np.array([])
    
    # Embed MCC descriptions
    _mcc_codes = mcc_list
    mcc_texts = [f"{m['mcc']} {m['description']}" for m in mcc_list]
    if mcc_texts:
        _mcc_embeddings = model.encode(mcc_texts, normalize_embeddings=True)
    else:
        _mcc_embeddings = np.array([])


def embed(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a list of texts.
    
    Uses sentence-transformers all-MiniLM-L6-v2 model which produces
    384-dimensional normalized vectors. Suitable for pgvector storage
    with cosine distance.
    
    Args:
        texts: List of strings to embed
        
    Returns:
        List of 384-dimensional float vectors (normalized)
        
    Note:
        - Dimension: 384
        - Distance metric: cosine (vectors are L2-normalized)
        - Model: all-MiniLM-L6-v2
    """
    if not texts:
        return []
    
    model = _get_model()
    embeddings = model.encode(texts, normalize_embeddings=True)
    return embeddings.tolist()


def _fuzzy_match_merchant(name: str) -> tuple[dict | None, float]:
    """
    Find the best fuzzy match for a merchant name.
    
    Returns:
        Tuple of (matched_merchant, confidence) or (None, 0.0)
    """
    merchants = _load_merchants()
    if not merchants or not name:
        return None, 0.0
    
    merchant_names = [m["name"] for m in merchants]
    
    # Use rapidfuzz for fuzzy matching
    result = process.extractOne(
        name,
        merchant_names,
        scorer=fuzz.WRatio,
        score_cutoff=60  # Minimum 60% match
    )
    
    if result is None:
        return None, 0.0
    
    matched_name, score, _ = result
    
    # Find the merchant with this name
    for merchant in merchants:
        if merchant["name"] == matched_name:
            # Convert score (0-100) to confidence (0.80-0.95)
            confidence = FUZZY_MIN_CONFIDENCE + (score / 100) * (FUZZY_MAX_CONFIDENCE - FUZZY_MIN_CONFIDENCE)
            return merchant, min(confidence, FUZZY_MAX_CONFIDENCE)
    
    return None, 0.0


def _embedding_match(query: str) -> tuple[dict | None, str, str, float]:
    """
    Find the best embedding similarity match.
    
    Returns:
        Tuple of (merchant_or_none, category, mcc, confidence)
    """
    import numpy as np
    
    _ensure_embeddings_loaded()
    
    model = _get_model()
    query_embedding = model.encode([query], normalize_embeddings=True)[0]
    
    best_merchant = None
    best_category = "Unknown"
    best_mcc = "0000"
    best_score = 0.0
    
    # Check merchant name similarity
    if _merchant_embeddings is not None and len(_merchant_embeddings) > 0:
        similarities = np.dot(_merchant_embeddings, query_embedding)
        best_idx = int(np.argmax(similarities))
        merchant_score = float(similarities[best_idx])
        
        if merchant_score > best_score:
            merchants = _load_merchants()
            best_merchant = merchants[best_idx]
            best_category = best_merchant["category"]
            best_mcc = best_merchant["mcc"]
            best_score = merchant_score
    
    # Check MCC description similarity (for category inference)
    if _mcc_embeddings is not None and len(_mcc_embeddings) > 0:
        mcc_similarities = np.dot(_mcc_embeddings, query_embedding)
        best_mcc_idx = int(np.argmax(mcc_similarities))
        mcc_score = float(mcc_similarities[best_mcc_idx])
        
        # Only use MCC match if no good merchant match
        if mcc_score > best_score and best_merchant is None:
            matched_mcc = _mcc_codes[best_mcc_idx]
            best_category = matched_mcc["description"]
            best_mcc = matched_mcc["mcc"]
            best_score = mcc_score
    
    # Convert cosine similarity to confidence
    confidence = max(0.0, min(1.0, best_score))
    
    return best_merchant, best_category, best_mcc, confidence


def _infer_from_domain(domain: str) -> tuple[str, str, str]:
    """
    Infer merchant name and category from domain when no match found.
    
    Returns:
        Tuple of (inferred_name, category, mcc)
    """
    registrable = _get_registrable_domain(domain)
    
    # Remove common suffixes and clean up
    name = registrable.split(".")[0]
    name = re.sub(r"[-_]", " ", name)
    name = name.title()
    
    return name, "Unknown", "0000"


def classify_merchant(
    name: str | None = None,
    domain: str | None = None,
    sender_domain: str | None = None,
) -> ClassifyMerchantResult:
    """
    Classify a merchant using a cascade of methods, cheapest first.
    
    Resolution order:
    1. Exact or registrable-domain match (confidence 0.99)
    2. Fuzzy name match with rapidfuzz (confidence 0.80-0.95)
    3. MiniLM embedding similarity (confidence based on cosine)
    4. Unknown fallback (low confidence)
    
    Args:
        name: Merchant name to classify (optional)
        domain: Primary domain to check (optional)
        sender_domain: Sender email domain to check (optional)
        
    Returns:
        ClassifyMerchantResult with merchant details and confidence
    """
    exact_index, registrable_index = _get_domain_indices()
    
    # Determine which domain to use for lookup and result
    lookup_domain = domain or sender_domain or ""
    result_domain = domain or sender_domain or "unknown"
    
    # Step 1: Exact or registrable domain match (cheapest)
    if lookup_domain:
        # First try exact match (normalized full domain)
        normalized = _normalize_domain(lookup_domain)
        if normalized in exact_index:
            merchant = exact_index[normalized]
            return ClassifyMerchantResult(
                domain=result_domain,
                merchant_id=UUID(merchant["id"]),
                merchant_name=merchant["name"],
                category=merchant["category"],
                mcc=merchant["mcc"],
                confidence=DOMAIN_MATCH_CONFIDENCE,
                is_new=False,
            )
        
        # Fall back to registrable domain match
        registrable = _get_registrable_domain(lookup_domain)
        if registrable in registrable_index:
            merchant = registrable_index[registrable]
            return ClassifyMerchantResult(
                domain=result_domain,
                merchant_id=UUID(merchant["id"]),
                merchant_name=merchant["name"],
                category=merchant["category"],
                mcc=merchant["mcc"],
                confidence=DOMAIN_MATCH_CONFIDENCE,
                is_new=False,
            )
    
    # Step 2: Fuzzy name match (medium cost)
    if name:
        merchant, confidence = _fuzzy_match_merchant(name)
        if merchant and confidence >= FUZZY_MIN_CONFIDENCE:
            return ClassifyMerchantResult(
                domain=result_domain,
                merchant_id=UUID(merchant["id"]),
                merchant_name=merchant["name"],
                category=merchant["category"],
                mcc=merchant["mcc"],
                confidence=confidence,
                is_new=False,
            )
    
    # Step 3: Embedding similarity (expensive, requires model load)
    query = name or lookup_domain
    if query:
        try:
            merchant, category, mcc, confidence = _embedding_match(query)
            if confidence >= EMBEDDING_MIN_CONFIDENCE:
                if merchant:
                    return ClassifyMerchantResult(
                        domain=result_domain,
                        merchant_id=UUID(merchant["id"]),
                        merchant_name=merchant["name"],
                        category=merchant["category"],
                        mcc=merchant["mcc"],
                        confidence=confidence,
                        is_new=False,
                    )
                else:
                    # Got category from MCC but no exact merchant
                    inferred_name = name or _infer_from_domain(lookup_domain)[0]
                    return ClassifyMerchantResult(
                        domain=result_domain,
                        merchant_id=None,
                        merchant_name=inferred_name,
                        category=category,
                        mcc=mcc,
                        confidence=confidence,
                        is_new=True,
                    )
        except Exception:
            # Model not available, fall through to unknown
            pass
    
    # Step 4: Unknown fallback
    inferred_name, category, mcc = _infer_from_domain(lookup_domain) if lookup_domain else ("Unknown", "Unknown", "0000")
    final_name = name or inferred_name
    
    return ClassifyMerchantResult(
        domain=result_domain,
        merchant_id=None,
        merchant_name=final_name,
        category=category,
        mcc=mcc,
        confidence=0.1,
        is_new=True,
    )
