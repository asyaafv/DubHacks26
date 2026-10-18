"""Tests for GLiNER2-based field extraction.

Tests extraction quality on seed .eml files and measures CPU latency.
Tests are skipped if the GLiNER2 model is not available.
"""
import email
import time
from pathlib import Path

import pytest

from backend.extraction.gliner_extract import (
    ExtractionUnavailable,
    extract_fields,
    warmup,
    _split_into_chunks,
    _parse_stackable,
)
from backend.extraction.types import FieldCandidates


SEED_EMAILS_DIR = Path(__file__).parent.parent.parent.parent / "shared" / "seed" / "emails"


def decode_eml(eml_path: Path) -> str:
    """Simple .eml decoder - extracts text body content."""
    with open(eml_path, "rb") as f:
        msg = email.message_from_bytes(f.read())
    
    text_parts = []
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    text_parts.append(payload.decode(charset, errors="replace"))
    else:
        content_type = msg.get_content_type()
        if content_type == "text/plain":
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                text_parts.append(payload.decode(charset, errors="replace"))
    
    if not text_parts:
        payload = msg.get_payload(decode=True)
        if payload:
            text_parts.append(payload.decode("utf-8", errors="replace"))
    
    subject = msg.get("Subject", "")
    full_text = f"Subject: {subject}\n\n" + "\n".join(text_parts)
    return full_text


def model_available() -> bool:
    """Check if GLiNER2 model can be loaded."""
    try:
        warmup()
        return True
    except ExtractionUnavailable:
        return False
    except Exception:
        return False


requires_model = pytest.mark.skipif(
    not model_available(),
    reason="GLiNER2 model not available"
)


class TestChunking:
    """Test text chunking functionality (no model needed)."""
    
    def test_short_text_no_split(self):
        text = "Short text that fits."
        chunks = _split_into_chunks(text, max_size=100)
        assert len(chunks) == 1
        assert chunks[0] == text
    
    def test_paragraph_split(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = _split_into_chunks(text, max_size=30)
        assert len(chunks) >= 2
        assert all(len(c) <= 30 for c in chunks)
    
    def test_empty_text(self):
        chunks = _split_into_chunks("", max_size=100)
        assert len(chunks) == 1


class TestStackableParsing:
    """Test stackable signal parsing (no model needed)."""
    
    def test_can_be_combined_true(self):
        assert _parse_stackable("This offer can be combined with other offers") == "true"
        assert _parse_stackable("Stackable with other promotions") == "true"
    
    def test_cannot_be_combined_false(self):
        assert _parse_stackable("Cannot be combined with other offers") == "false"
        assert _parse_stackable("Not valid with other promotions") == "false"
        assert _parse_stackable("Limit one per customer") == "false"
    
    def test_unclear_defaults_true(self):
        assert _parse_stackable("Some random text") == "true"


@requires_model
class TestExtractionOnSeedEmails:
    """Test extraction quality on seed .eml files."""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Ensure model is warmed up before tests."""
        warmup()
    
    def test_hollister_email(self):
        """Test extraction from Hollister 10% off email."""
        eml_path = SEED_EMAILS_DIR / "hollister_10_percent.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        
        text = decode_eml(eml_path)
        
        start = time.perf_counter()
        result = extract_fields(text)
        latency_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n=== Hollister Email Extraction ===")
        print(f"Latency: {latency_ms:.1f} ms")
        print(f"Merchant: {result.merchant}")
        print(f"Discount: {result.discount_value}")
        print(f"Code: {result.code}")
        print(f"Min Spend: {result.min_spend}")
        print(f"Expiry: {result.expiry}")
        print(f"Exclusions: {result.exclusions}")
        
        assert isinstance(result, FieldCandidates)
        
        if result.code:
            assert "HCOFALL10" in result.code.value.upper() or result.code.confidence > 0.5
        if result.discount_value:
            assert "10" in result.discount_value.value or "%" in result.discount_value.value
    
    def test_nike_email(self):
        """Test extraction from Nike promo email."""
        eml_path = SEED_EMAILS_DIR / "nike_promo.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        
        text = decode_eml(eml_path)
        
        start = time.perf_counter()
        result = extract_fields(text)
        latency_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n=== Nike Email Extraction ===")
        print(f"Latency: {latency_ms:.1f} ms")
        print(f"Merchant: {result.merchant}")
        print(f"Discount: {result.discount_value}")
        print(f"Code: {result.code}")
        print(f"Min Spend: {result.min_spend}")
        print(f"Max Discount: {result.max_discount}")
        print(f"Expiry: {result.expiry}")
        print(f"Exclusions: {result.exclusions}")
        
        assert isinstance(result, FieldCandidates)
    
    def test_target_email(self):
        """Test extraction from Target $5 off email."""
        eml_path = SEED_EMAILS_DIR / "target_jsonld_offer.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        
        text = decode_eml(eml_path)
        
        start = time.perf_counter()
        result = extract_fields(text)
        latency_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n=== Target Email Extraction ===")
        print(f"Latency: {latency_ms:.1f} ms")
        print(f"Merchant: {result.merchant}")
        print(f"Discount: {result.discount_value}")
        print(f"Code: {result.code}")
        print(f"Min Spend: {result.min_spend}")
        print(f"Expiry: {result.expiry}")
        print(f"Stackable: {result.stackable}")
        
        assert isinstance(result, FieldCandidates)
        
        if result.stackable:
            assert result.stackable.value == "true"
    
    def test_chipotle_email(self):
        """Test extraction from Chipotle free guac email (plaintext only)."""
        eml_path = SEED_EMAILS_DIR / "chipotle_plaintext.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        
        text = decode_eml(eml_path)
        
        start = time.perf_counter()
        result = extract_fields(text)
        latency_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n=== Chipotle Email Extraction ===")
        print(f"Latency: {latency_ms:.1f} ms")
        print(f"Merchant: {result.merchant}")
        print(f"Discount: {result.discount_value}")
        print(f"Code: {result.code}")
        print(f"Min Spend: {result.min_spend}")
        print(f"Expiry: {result.expiry}")
        print(f"Stackable: {result.stackable}")
        
        assert isinstance(result, FieldCandidates)
        
        if result.code:
            assert "FREEGUAC" in result.code.value.upper() or result.code.confidence > 0.5
        
        if result.stackable:
            assert result.stackable.value == "true"
    
    def test_amazon_receipt_minimal_extraction(self):
        """Test that receipt emails extract minimal reward fields."""
        eml_path = SEED_EMAILS_DIR / "amazon_receipt.eml"
        if not eml_path.exists():
            pytest.skip(f"Seed email not found: {eml_path}")
        
        text = decode_eml(eml_path)
        
        start = time.perf_counter()
        result = extract_fields(text)
        latency_ms = (time.perf_counter() - start) * 1000
        
        print(f"\n=== Amazon Receipt Extraction ===")
        print(f"Latency: {latency_ms:.1f} ms")
        print(f"Merchant: {result.merchant}")
        print(f"Discount: {result.discount_value}")
        print(f"Code: {result.code}")
        
        assert isinstance(result, FieldCandidates)


@requires_model
class TestExtractionLatencyBenchmark:
    """Benchmark extraction latency across all seed emails."""
    
    def test_latency_benchmark(self):
        """Measure and report CPU latency for all seed emails."""
        warmup()
        
        eml_files = list(SEED_EMAILS_DIR.glob("*.eml"))
        if not eml_files:
            pytest.skip("No seed emails found")
        
        results = []
        
        for eml_path in eml_files:
            text = decode_eml(eml_path)
            
            start = time.perf_counter()
            extract_fields(text)
            latency_ms = (time.perf_counter() - start) * 1000
            
            results.append({
                "file": eml_path.name,
                "text_len": len(text),
                "latency_ms": latency_ms,
            })
        
        print("\n" + "=" * 60)
        print("GLiNER2 EXTRACTION LATENCY BENCHMARK")
        print("=" * 60)
        print(f"{'Email':<35} {'Length':>8} {'Latency':>10}")
        print("-" * 60)
        
        for r in results:
            print(f"{r['file']:<35} {r['text_len']:>8} {r['latency_ms']:>8.1f} ms")
        
        avg_latency = sum(r['latency_ms'] for r in results) / len(results)
        total_latency = sum(r['latency_ms'] for r in results)
        
        print("-" * 60)
        print(f"{'Average':<35} {'-':>8} {avg_latency:>8.1f} ms")
        print(f"{'Total':<35} {'-':>8} {total_latency:>8.1f} ms")
        print("=" * 60)
        
        assert avg_latency < 10000, f"Average latency too high: {avg_latency:.1f} ms"


@requires_model
class TestExtractionAccuracyReport:
    """Report extraction accuracy on seed emails."""
    
    def test_accuracy_report(self):
        """Generate accuracy report comparing extracted vs expected fields."""
        warmup()
        
        expected = {
            "hollister_10_percent.eml": {
                "code": "HCOFALL10",
                "discount_contains": ["10", "%"],
                "min_spend_contains": ["50"],
                "expiry_contains": ["October", "20"],
                "exclusion_any": ["Gift Card", "Clearance"],
            },
            "nike_promo.eml": {
                "code": "NIKE20FALL",
                "discount_contains": ["20", "%"],
                "min_spend_contains": ["100"],
                "max_discount_contains": ["50"],
                "expiry_contains": ["October", "19"],
                "exclusion_any": ["Jordan", "Limited"],
            },
            "target_jsonld_offer.eml": {
                "code": "TARGET5",
                "discount_contains": ["5"],
                "min_spend_contains": ["25"],
                "expiry_contains": ["October", "19"],
                "stackable": "true",
            },
            "chipotle_plaintext.eml": {
                "code": "FREEGUAC",
                "discount_contains": ["FREE", "Guacamole"],
                "min_spend_contains": ["10"],
                "expiry_contains": ["October", "31"],
                "stackable": "true",
            },
        }
        
        print("\n" + "=" * 70)
        print("GLiNER2 EXTRACTION ACCURACY REPORT")
        print("=" * 70)
        
        total_checks = 0
        passed_checks = 0
        
        for filename, expectations in expected.items():
            eml_path = SEED_EMAILS_DIR / filename
            if not eml_path.exists():
                print(f"\nSKIPPED: {filename} (file not found)")
                continue
            
            text = decode_eml(eml_path)
            result = extract_fields(text)
            
            print(f"\n--- {filename} ---")
            
            if "code" in expectations:
                total_checks += 1
                exp_code = expectations["code"]
                got_code = result.code.value if result.code else ""
                match = exp_code.upper() in got_code.upper()
                status = "✓" if match else "✗"
                print(f"  {status} code: expected '{exp_code}', got '{got_code}'")
                if match:
                    passed_checks += 1
            
            if "discount_contains" in expectations:
                total_checks += 1
                got = result.discount_value.value if result.discount_value else ""
                matches = any(kw.lower() in got.lower() for kw in expectations["discount_contains"])
                status = "✓" if matches else "✗"
                print(f"  {status} discount: got '{got}' (looking for {expectations['discount_contains']})")
                if matches:
                    passed_checks += 1
            
            if "min_spend_contains" in expectations:
                total_checks += 1
                got = result.min_spend.value if result.min_spend else ""
                matches = any(kw in got for kw in expectations["min_spend_contains"])
                status = "✓" if matches else "✗"
                print(f"  {status} min_spend: got '{got}' (looking for {expectations['min_spend_contains']})")
                if matches:
                    passed_checks += 1
            
            if "max_discount_contains" in expectations:
                total_checks += 1
                got = result.max_discount.value if result.max_discount else ""
                matches = any(kw in got for kw in expectations["max_discount_contains"])
                status = "✓" if matches else "✗"
                print(f"  {status} max_discount: got '{got}' (looking for {expectations['max_discount_contains']})")
                if matches:
                    passed_checks += 1
            
            if "expiry_contains" in expectations:
                total_checks += 1
                got = result.expiry.value if result.expiry else ""
                matches = any(kw.lower() in got.lower() for kw in expectations["expiry_contains"])
                status = "✓" if matches else "✗"
                print(f"  {status} expiry: got '{got}' (looking for {expectations['expiry_contains']})")
                if matches:
                    passed_checks += 1
            
            if "stackable" in expectations:
                total_checks += 1
                got = result.stackable.value if result.stackable else ""
                matches = got == expectations["stackable"]
                status = "✓" if matches else "✗"
                print(f"  {status} stackable: expected '{expectations['stackable']}', got '{got}'")
                if matches:
                    passed_checks += 1
            
            if "exclusion_any" in expectations:
                total_checks += 1
                exc_texts = [e.value for e in result.exclusions] if result.exclusions else []
                got_combined = " ".join(exc_texts).lower()
                matches = any(kw.lower() in got_combined for kw in expectations["exclusion_any"])
                status = "✓" if matches else "✗"
                print(f"  {status} exclusions: got {exc_texts} (looking for any of {expectations['exclusion_any']})")
                if matches:
                    passed_checks += 1
        
        print("\n" + "=" * 70)
        accuracy = (passed_checks / total_checks * 100) if total_checks > 0 else 0
        print(f"ACCURACY: {passed_checks}/{total_checks} checks passed ({accuracy:.1f}%)")
        print("=" * 70)
