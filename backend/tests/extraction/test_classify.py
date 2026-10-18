"""
Tests for email classification module.

Tests rule-based fallback on seed .eml files.
Model-based tests are skipped if no model is available.
"""

import email
import time
from pathlib import Path

import pytest

from backend.extraction.classify import (
    LABELS,
    _rule_based_classify,
    classify_email,
    get_model_info,
)

SEED_EMAILS_DIR = Path(__file__).parent.parent.parent.parent / "shared" / "seed" / "emails"


def parse_eml(path: Path) -> tuple[str, str]:
    """Parse an .eml file and return (subject, text_body)."""
    with open(path, "rb") as f:
        msg = email.message_from_bytes(f.read())
    
    subject = msg.get("Subject", "")
    
    text_body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    text_body = payload.decode("utf-8", errors="replace")
                    break
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            text_body = payload.decode("utf-8", errors="replace")
    
    return subject, text_body


class TestRuleBasedClassifier:
    """Test the rule-based fallback classifier."""
    
    def test_hollister_reward(self):
        """Hollister 10% off voucher should classify as reward."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        
        subject, text = parse_eml(eml_path)
        label, confidence = _rule_based_classify(subject, text)
        
        assert label == "reward", f"Expected 'reward', got '{label}'"
        assert confidence > 0.3, f"Expected confidence > 0.3, got {confidence}"
    
    def test_target_reward(self):
        """Target Circle $5 off offer should classify as reward."""
        eml_path = SEED_EMAILS_DIR / "target_jsonld_offer.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        
        subject, text = parse_eml(eml_path)
        label, confidence = _rule_based_classify(subject, text)
        
        assert label == "reward", f"Expected 'reward', got '{label}'"
        assert confidence > 0.3, f"Expected confidence > 0.3, got {confidence}"
    
    def test_chipotle_reward(self):
        """Chipotle free guacamole should classify as reward."""
        eml_path = SEED_EMAILS_DIR / "chipotle_plaintext.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        
        subject, text = parse_eml(eml_path)
        label, confidence = _rule_based_classify(subject, text)
        
        assert label == "reward", f"Expected 'reward', got '{label}'"
        assert confidence > 0.3, f"Expected confidence > 0.3, got {confidence}"
    
    def test_nike_promo(self):
        """Nike fall sale should classify as promo or reward (borderline)."""
        eml_path = SEED_EMAILS_DIR / "nike_promo.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        
        subject, text = parse_eml(eml_path)
        label, confidence = _rule_based_classify(subject, text)
        
        assert label in ("promo", "reward"), f"Expected 'promo' or 'reward', got '{label}'"
    
    def test_amazon_receipt(self):
        """Amazon shipping confirmation should classify as receipt."""
        eml_path = SEED_EMAILS_DIR / "amazon_receipt.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        
        subject, text = parse_eml(eml_path)
        label, confidence = _rule_based_classify(subject, text)
        
        assert label == "receipt", f"Expected 'receipt', got '{label}'"
        assert confidence > 0.3, f"Expected confidence > 0.3, got {confidence}"
    
    def test_empty_email_defaults_to_reward(self):
        """Empty/unknown emails should default to 'reward' (fail open)."""
        label, confidence = _rule_based_classify("", "")
        assert label == "reward", f"Expected 'reward', got '{label}'"
        assert confidence < 0.5, f"Expected low confidence for empty email"
    
    def test_ambiguous_email_defaults_to_reward(self):
        """Ambiguous emails should lean toward 'reward'."""
        label, confidence = _rule_based_classify(
            "Hello",
            "Thank you for your interest."
        )
        assert label == "reward", f"Expected 'reward' for ambiguous email, got '{label}'"


class TestClassifyEmail:
    """Test the main classify_email function."""
    
    def test_returns_valid_label(self):
        """classify_email should always return a valid label."""
        label, confidence = classify_email("Test subject", "Test body")
        assert label in LABELS, f"Invalid label: {label}"
        assert 0.0 <= confidence <= 1.0, f"Invalid confidence: {confidence}"
    
    def test_seed_hollister(self):
        """Full classifier on Hollister seed email."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        
        subject, text = parse_eml(eml_path)
        label, confidence = classify_email(subject, text)
        
        assert label == "reward", f"Expected 'reward', got '{label}'"
    
    def test_seed_amazon(self):
        """Full classifier on Amazon receipt email."""
        eml_path = SEED_EMAILS_DIR / "amazon_receipt.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        
        subject, text = parse_eml(eml_path)
        label, confidence = classify_email(subject, text)
        
        assert label == "receipt", f"Expected 'receipt', got '{label}'"
    
    def test_latency_is_reasonable(self):
        """Classification should be fast (< 100ms per email without model)."""
        subject = "Your 10% Off Voucher"
        text = "Here's a special reward just for you: 10% OFF YOUR NEXT PURCHASE Code: TEST123"
        
        iterations = 10
        start = time.time()
        for _ in range(iterations):
            classify_email(subject, text)
        elapsed = time.time() - start
        
        avg_latency_ms = (elapsed / iterations) * 1000
        assert avg_latency_ms < 100, f"Average latency {avg_latency_ms:.2f}ms exceeds 100ms"


class TestModelIntegration:
    """Tests that require the trained model."""
    
    @pytest.fixture(autouse=True)
    def check_model(self):
        """Skip tests if model is not available."""
        info = get_model_info()
        if info["model_type"] != "setfit":
            pytest.skip("SetFit model not available")
    
    def test_model_loaded(self):
        """Model should load successfully."""
        info = get_model_info()
        assert info["model_type"] == "setfit"
        assert info["model_path"] is not None
    
    def test_model_classification(self):
        """Model should classify reward emails correctly."""
        label, confidence = classify_email(
            "Your $10 Reward is Ready!",
            "Congratulations! You've earned a $10 reward. Use code REWARD10 at checkout."
        )
        assert label == "reward"
        assert confidence > 0.5
    
    def test_model_receipt(self):
        """Model should classify receipts correctly."""
        label, confidence = classify_email(
            "Your order has shipped",
            "Order #123456 Sony Headphones $328.00 Total: $357.52 Arriving Friday"
        )
        assert label == "receipt"
    
    def test_model_promo(self):
        """Model should classify promos correctly."""
        label, confidence = classify_email(
            "FLASH SALE: 40% Off Everything!",
            "Don't miss out! For the next 48 hours only. Shop now at our website."
        )
        assert label == "promo"
    
    def test_model_latency(self):
        """Model inference should be reasonably fast."""
        subject = "Your 10% Off Voucher"
        text = "Here's a special reward just for you: 10% OFF YOUR NEXT PURCHASE"
        
        classify_email(subject, text)
        
        iterations = 5
        start = time.time()
        for _ in range(iterations):
            classify_email(subject, text)
        elapsed = time.time() - start
        
        avg_latency_ms = (elapsed / iterations) * 1000
        print(f"Model inference latency: {avg_latency_ms:.2f}ms")
        assert avg_latency_ms < 500, f"Average latency {avg_latency_ms:.2f}ms exceeds 500ms"


class TestGetModelInfo:
    """Test model info function."""
    
    def test_returns_dict(self):
        """get_model_info should return a dict with expected keys."""
        info = get_model_info()
        assert isinstance(info, dict)
        assert "model_type" in info
        assert "labels" in info
        assert info["model_type"] in ("setfit", "rule_based")
        assert set(info["labels"]) == set(LABELS)
