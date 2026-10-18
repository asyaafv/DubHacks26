"""
Email classifier for Lapse.

Classifies emails into: reward, receipt, promo, other

Uses SetFit model when available, with rule-based fallback.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from setfit import SetFitModel

LABELS = ("reward", "receipt", "promo", "other")
MODEL_DIR = Path(__file__).parent / "models" / "email_classifier"

_model: "SetFitModel | None" = None
_model_loaded = False


def _load_model() -> "SetFitModel | None":
    """Lazy-load the SetFit model if available."""
    global _model, _model_loaded
    
    if _model_loaded:
        return _model
    
    _model_loaded = True
    
    if not MODEL_DIR.exists():
        return None
    
    try:
        from setfit import SetFitModel
        _model = SetFitModel.from_pretrained(str(MODEL_DIR))
        return _model
    except Exception:
        return None


def _truncate_text(text: str, max_tokens: int = 512) -> str:
    """Truncate text to approximately max_tokens (rough word-based estimate)."""
    words = text.split()
    if len(words) <= max_tokens:
        return text
    return " ".join(words[:max_tokens])


def _rule_based_classify(subject: str, text: str) -> tuple[str, float]:
    """
    Fast keyword/rule-based fallback classifier.
    
    Returns (label, confidence) where confidence is typically lower (0.5-0.8)
    to indicate rule-based classification.
    """
    combined = f"{subject}\n{text}".lower()
    
    reward_strong = [
        "you've earned",
        "you earned",
        "your reward",
        "here's your",
        "your $",
        "your voucher",
        "your coupon",
        "your personal",
        "just for you",
        "earned free",
        "free guacamole",
        "free entree",
        "free drink",
        "free fries",
        "birthday reward",
        "birthday gift",
        "bonus points",
        "earned points",
        "your points",
        "store credit",
        "your personal coupon",
        "vip reward",
        "member reward",
        "thanks for being a loyal",
        "loyalty reward",
        "special reward",
        "exclusive reward",
        "claim your",
    ]
    
    reward_moderate = [
        "% off your next",
        "off your next purchase",
        "off your next order",
        "valid through",
        "expires",
        "code:",
        "promo code",
        "coupon code",
        "use code",
        "apply code",
        "redeem",
        "minimum purchase",
        "min purchase",
    ]
    
    receipt_patterns = [
        "order confirmation",
        "order confirmed",
        "your order has shipped",
        "has shipped",
        "order #",
        "order number",
        "order total",
        "payment receipt",
        "payment confirmation",
        "invoice",
        "receipt for",
        "thank you for your purchase",
        "thanks for your purchase",
        "thank you for your order",
        "your purchase",
        "transaction #",
        "transaction id",
        "subtotal:",
        "tax:",
        "total:",
        "qty:",
        "quantity:",
        "sold by:",
        "arriving:",
        "delivery estimate",
    ]
    
    promo_patterns = [
        "flash sale",
        "sale starts",
        "sale ends",
        "% off everything",
        "% off sitewide",
        "up to % off",
        "black friday",
        "cyber monday",
        "memorial day",
        "labor day",
        "clearance",
        "end of season",
        "semi-annual",
        "anniversary sale",
        "friends & family",
        "friends and family",
        "member sale",
        "vip sale",
        "vip early access",
        "shop now",
        "shop early",
        "limited time",
        "while supplies last",
        "don't miss out",
        "bogo",
        "buy one get one",
        "new arrivals",
        "shop our",
        "discover what's new",
    ]
    
    other_patterns = [
        "has been delivered",
        "out for delivery",
        "in transit",
        "tracking update",
        "tracking number",
        "security alert",
        "password reset",
        "verify your email",
        "confirm your email",
        "newsletter",
        "weekly summary",
        "monthly statement",
        "subscription renew",
        "update payment",
        "flight itinerary",
        "appointment reminder",
        "privacy policy",
        "terms of service",
        "package delayed",
        "returned to sender",
        "two-factor",
        "2fa",
        "sign-in",
        "new device",
        "welcome to",
    ]
    
    scores = {"reward": 0.0, "receipt": 0.0, "promo": 0.0, "other": 0.0}
    
    for pattern in reward_strong:
        if pattern in combined:
            scores["reward"] += 3.0
    
    for pattern in reward_moderate:
        if pattern in combined:
            scores["reward"] += 1.0
    
    for pattern in receipt_patterns:
        if pattern in combined:
            scores["receipt"] += 2.0
    
    for pattern in promo_patterns:
        if pattern in combined:
            scores["promo"] += 2.0
    
    for pattern in other_patterns:
        if pattern in combined:
            scores["other"] += 2.0
    
    if re.search(r"order\s*#?\s*[\w-]{6,}", combined):
        scores["receipt"] += 1.5
    
    if re.search(r"\$\d+\.\d{2}", combined):
        if "order" in combined or "total" in combined or "subtotal" in combined:
            scores["receipt"] += 1.0
        else:
            scores["reward"] += 0.5
    
    if re.search(r"code:\s*[A-Z0-9]{4,}", combined, re.IGNORECASE):
        if scores["receipt"] < scores["reward"]:
            scores["reward"] += 1.0
    
    max_label = max(scores, key=lambda k: scores[k])
    max_score = scores[max_label]
    total_score = sum(scores.values())
    
    if total_score == 0:
        return ("reward", 0.3)
    
    confidence = min(0.8, 0.3 + (max_score / total_score) * 0.5)
    
    if max_score < 1.0:
        return ("reward", 0.35)
    
    return (max_label, confidence)


def classify_email(subject: str, text: str) -> tuple[str, float]:
    """
    Classify an email into one of: reward, receipt, promo, other.
    
    Args:
        subject: Email subject line
        text: Email body text (plain text preferred)
    
    Returns:
        Tuple of (label, confidence) where:
        - label is one of "reward", "receipt", "promo", "other"
        - confidence is a float from 0.0 to 1.0
        
        When unsure (confidence < 0.5), leans toward "reward" so the
        pipeline still tries extraction.
    """
    combined = f"{subject}\n\n{_truncate_text(text)}"
    
    model = _load_model()
    
    if model is not None:
        try:
            predictions = model.predict([combined])
            
            if hasattr(predictions, "tolist"):
                pred = predictions[0]
            else:
                pred = predictions[0]
            
            if isinstance(pred, str):
                label = pred
            else:
                label = LABELS[int(pred)]
            
            probas = None
            if hasattr(model, "predict_proba"):
                try:
                    probas = model.predict_proba([combined])
                    if hasattr(probas, "tolist"):
                        probas = probas[0]
                    confidence = float(max(probas))
                except Exception:
                    confidence = 0.85
            else:
                confidence = 0.85
            
            if confidence < 0.5 and label != "reward":
                return ("reward", confidence)
            
            return (label, confidence)
            
        except Exception:
            pass
    
    label, confidence = _rule_based_classify(subject, text)
    
    if confidence < 0.5 and label != "reward":
        return ("reward", confidence)
    
    return (label, confidence)


def get_model_info() -> dict:
    """Get information about the loaded model."""
    model = _load_model()
    if model is None:
        return {
            "model_type": "rule_based",
            "model_path": None,
            "labels": list(LABELS),
        }
    return {
        "model_type": "setfit",
        "model_path": str(MODEL_DIR),
        "labels": list(LABELS),
    }
