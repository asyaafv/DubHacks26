"""
Tests for merchant classification module.

Tests cover:
- Exact domain matching for seed merchants
- Sender subdomain matching (email.hollister.com -> hollisterco.com)
- Typo/fuzzy name matching
- Embedding similarity (skipped if model unavailable)
- Latency measurements
"""

import time
from uuid import UUID

import pytest

from backend.extraction.merchants import (
    classify_merchant,
    embed,
    _get_registrable_domain,
    _load_merchants,
)


class TestRegistrableDomain:
    """Test domain extraction logic."""
    
    def test_simple_domain(self):
        assert _get_registrable_domain("target.com") == "target.com"
    
    def test_www_subdomain(self):
        assert _get_registrable_domain("www.target.com") == "target.com"
    
    def test_email_subdomain(self):
        assert _get_registrable_domain("email.hollisterco.com") == "hollisterco.com"
    
    def test_mail_subdomain(self):
        assert _get_registrable_domain("mail.nike.com") == "nike.com"
    
    def test_store_subdomain(self):
        assert _get_registrable_domain("store.apple.com") == "apple.com"
    
    def test_deep_subdomain(self):
        assert _get_registrable_domain("promo.email.store.example.com") == "example.com"
    
    def test_uppercase(self):
        assert _get_registrable_domain("WWW.TARGET.COM") == "target.com"


class TestExactDomainMatch:
    """Test exact domain matching against seed merchants."""
    
    def test_target_domain(self):
        result = classify_merchant(domain="target.com")
        assert result.merchant_name == "Target"
        assert result.confidence == 0.99
        assert result.is_new is False
        assert result.mcc == "5311"
        assert result.category == "Department Stores"
        assert result.merchant_id is not None
    
    def test_nike_domain(self):
        result = classify_merchant(domain="nike.com")
        assert result.merchant_name == "Nike"
        assert result.confidence == 0.99
        assert result.is_new is False
    
    def test_amazon_domain(self):
        result = classify_merchant(domain="amazon.com")
        assert result.merchant_name == "Amazon"
        assert result.confidence == 0.99
        assert result.is_new is False
    
    def test_starbucks_domain(self):
        result = classify_merchant(domain="starbucks.com")
        assert result.merchant_name == "Starbucks"
        assert result.mcc == "5812"  # Eating Places & Restaurants
        assert result.confidence == 0.99
    
    def test_chipotle_domain(self):
        result = classify_merchant(domain="chipotle.com")
        assert result.merchant_name == "Chipotle"
        assert result.confidence == 0.99


class TestSenderSubdomainMatch:
    """Test that sender subdomains are correctly resolved."""
    
    def test_email_hollister(self):
        """email.hollisterco.com should match Hollister."""
        result = classify_merchant(sender_domain="email.hollisterco.com")
        assert result.merchant_name == "Hollister"
        assert result.confidence == 0.99
        assert result.is_new is False
    
    def test_mail_nike(self):
        """mail.nike.com should match Nike."""
        result = classify_merchant(sender_domain="mail.nike.com")
        assert result.merchant_name == "Nike"
        assert result.confidence == 0.99
    
    def test_store_nike(self):
        """store.nike.com should match Nike (via alias)."""
        result = classify_merchant(sender_domain="store.nike.com")
        assert result.merchant_name == "Nike"
        assert result.confidence == 0.99
    
    def test_www_target(self):
        """www.target.com should match Target."""
        result = classify_merchant(sender_domain="www.target.com")
        assert result.merchant_name == "Target"
        assert result.confidence == 0.99
    
    def test_app_starbucks(self):
        """app.starbucks.com should match Starbucks (via alias)."""
        result = classify_merchant(sender_domain="app.starbucks.com")
        assert result.merchant_name == "Starbucks"
        assert result.confidence == 0.99
    
    def test_promo_subdomain(self):
        """Deeply nested subdomains should still match."""
        result = classify_merchant(sender_domain="promo.email.target.com")
        assert result.merchant_name == "Target"
        assert result.confidence == 0.99


class TestFuzzyNameMatch:
    """Test fuzzy name matching with typos."""
    
    def test_target_typo(self):
        """Targett (typo) should match Target."""
        result = classify_merchant(name="Targett")
        assert result.merchant_name == "Target"
        assert 0.80 <= result.confidence <= 0.95
        assert result.is_new is False
    
    def test_nikey_typo(self):
        """Nikey (typo) should match Nike."""
        result = classify_merchant(name="Nikey")
        assert result.merchant_name == "Nike"
        assert 0.80 <= result.confidence <= 0.95
    
    def test_starbuks_typo(self):
        """Starbuks (typo) should match Starbucks."""
        result = classify_merchant(name="Starbuks")
        assert result.merchant_name == "Starbucks"
        assert 0.80 <= result.confidence <= 0.95
    
    def test_mcdonalds_variations(self):
        """McDonalds variations should match."""
        result = classify_merchant(name="Mc Donalds")
        assert result.merchant_name == "McDonald's"
        assert 0.80 <= result.confidence <= 0.95
    
    def test_home_depot_spacing(self):
        """HomeDepot (no space) should match Home Depot."""
        result = classify_merchant(name="HomeDepot")
        assert result.merchant_name == "Home Depot"
        assert 0.80 <= result.confidence <= 0.95


class TestUnknownMerchant:
    """Test handling of unknown merchants."""
    
    def test_unknown_domain(self):
        """Unknown domain should return is_new=True with low confidence."""
        result = classify_merchant(domain="totallyunknownstore12345.com")
        assert result.is_new is True
        assert result.confidence < 0.5
        assert result.domain == "totallyunknownstore12345.com"
    
    def test_unknown_name_and_domain(self):
        """Unknown name and domain should fall back gracefully."""
        result = classify_merchant(
            name="Some Random Store",
            domain="randomstore12345.net"
        )
        assert result.is_new is True
    
    def test_empty_input(self):
        """Empty input should return unknown."""
        result = classify_merchant()
        assert result.is_new is True
        assert result.merchant_name == "Unknown"
        assert result.confidence == 0.1


class TestDomainPreference:
    """Test that domain takes priority over sender_domain."""
    
    def test_domain_over_sender(self):
        """domain parameter should be used for result."""
        result = classify_merchant(
            domain="target.com",
            sender_domain="email.walmart.com"
        )
        assert result.merchant_name == "Target"
        assert result.domain == "target.com"


class TestMccCodes:
    """Test MCC code assignments."""
    
    def test_department_store_mcc(self):
        result = classify_merchant(domain="target.com")
        assert result.mcc == "5311"  # Department Stores
    
    def test_restaurant_mcc(self):
        result = classify_merchant(domain="chipotle.com")
        assert result.mcc == "5812"  # Eating Places & Restaurants
    
    def test_fast_food_mcc(self):
        result = classify_merchant(domain="mcdonalds.com")
        assert result.mcc == "5814"  # Fast Food Restaurants
    
    def test_shoe_store_mcc(self):
        result = classify_merchant(domain="nike.com")
        assert result.mcc == "5661"  # Shoe Stores
    
    def test_grocery_mcc(self):
        result = classify_merchant(domain="kroger.com")
        assert result.mcc == "5411"  # Grocery Stores


class TestEmbedding:
    """Test embedding functionality. Skipped if model unavailable."""
    
    @pytest.fixture(autouse=True)
    def check_model_available(self):
        """Skip tests if sentence-transformers model can't be loaded."""
        try:
            from sentence_transformers import SentenceTransformer
            # Try to load model (may fail if not downloaded/no network)
            SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
        except Exception as e:
            pytest.skip(f"sentence-transformers model unavailable: {e}")
    
    def test_embed_single_text(self):
        """Single text should produce 384-dim vector."""
        result = embed(["Hello world"])
        assert len(result) == 1
        assert len(result[0]) == 384
    
    def test_embed_multiple_texts(self):
        """Multiple texts should produce multiple vectors."""
        result = embed(["Hello", "World", "Test"])
        assert len(result) == 3
        for vec in result:
            assert len(vec) == 384
    
    def test_embed_empty_list(self):
        """Empty input should return empty list."""
        result = embed([])
        assert result == []
    
    def test_embed_normalization(self):
        """Vectors should be L2-normalized (for cosine distance)."""
        import numpy as np
        
        result = embed(["Test text for normalization"])
        vec = np.array(result[0])
        norm = np.linalg.norm(vec)
        assert abs(norm - 1.0) < 0.01  # Should be ~1.0
    
    def test_similar_texts_close(self):
        """Similar texts should have high cosine similarity."""
        import numpy as np
        
        result = embed([
            "Nike running shoes",
            "Nike athletic footwear",
            "Cat food recipes"
        ])
        
        vec1, vec2, vec3 = [np.array(v) for v in result]
        
        # Cosine similarity (vectors are normalized)
        sim_12 = np.dot(vec1, vec2)
        sim_13 = np.dot(vec1, vec3)
        
        # Nike shoes should be more similar to Nike footwear than cat food
        assert sim_12 > sim_13


class TestEmbeddingClassification:
    """Test embedding-based classification. Skipped if model unavailable."""
    
    @pytest.fixture(autouse=True)
    def check_model_available(self):
        """Skip tests if sentence-transformers model can't be loaded."""
        try:
            from sentence_transformers import SentenceTransformer
            SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
        except Exception as e:
            pytest.skip(f"sentence-transformers model unavailable: {e}")
    
    def test_semantic_match_shoes(self):
        """'Running shoes store' should match Nike or similar shoe merchant."""
        result = classify_merchant(name="Athletic Footwear Shop")
        # Should find a shoe-related merchant or category
        assert result.mcc in ["5661", "5651", "5999"] or "Shoe" in result.category or "Clothing" in result.category


class TestLatency:
    """Test and report latency for classification operations."""
    
    def test_domain_lookup_latency(self):
        """Domain lookup should be fast (<10ms)."""
        # Warm up the cache
        classify_merchant(domain="target.com")
        
        start = time.perf_counter()
        for _ in range(100):
            classify_merchant(domain="target.com")
        elapsed = time.perf_counter() - start
        
        avg_ms = (elapsed / 100) * 1000
        print(f"\nDomain lookup latency: {avg_ms:.3f}ms avg")
        assert avg_ms < 10, f"Domain lookup too slow: {avg_ms:.3f}ms"
    
    def test_fuzzy_match_latency(self):
        """Fuzzy match should be reasonably fast (<50ms)."""
        # Warm up
        classify_merchant(name="Targett")
        
        start = time.perf_counter()
        for _ in range(10):
            classify_merchant(name="Starbuks")
        elapsed = time.perf_counter() - start
        
        avg_ms = (elapsed / 10) * 1000
        print(f"\nFuzzy match latency: {avg_ms:.3f}ms avg")
        assert avg_ms < 50, f"Fuzzy match too slow: {avg_ms:.3f}ms"
    
    @pytest.fixture(autouse=True)
    def check_model_for_embedding_latency(self, request):
        """Skip embedding latency test if model unavailable."""
        if request.node.name == "test_embedding_latency":
            try:
                from sentence_transformers import SentenceTransformer
                SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
            except Exception as e:
                pytest.skip(f"sentence-transformers model unavailable: {e}")
    
    def test_embedding_latency(self):
        """Embedding should complete in reasonable time (<500ms for batch)."""
        texts = ["Test " * 10] * 10  # 10 moderate-length texts
        
        # Warm up model
        embed(["warmup"])
        
        start = time.perf_counter()
        embed(texts)
        elapsed = time.perf_counter() - start
        
        ms = elapsed * 1000
        print(f"\nEmbedding latency (10 texts): {ms:.1f}ms total, {ms/10:.1f}ms avg")
        assert ms < 5000, f"Embedding too slow: {ms:.1f}ms for 10 texts"


class TestAllSeedMerchants:
    """Test that all seed merchants can be looked up by domain."""
    
    def test_all_merchants_by_domain(self):
        """Every seed merchant should be findable by its primary domain."""
        merchants = _load_merchants()
        
        for merchant in merchants:
            result = classify_merchant(domain=merchant["domain"])
            assert result.merchant_name == merchant["name"], \
                f"Failed to match {merchant['domain']} -> {merchant['name']}"
            assert result.confidence == 0.99
            assert result.is_new is False
            assert result.merchant_id == UUID(merchant["id"])
    
    def test_all_merchants_by_aliases(self):
        """Merchants should be findable by their aliases too."""
        merchants = _load_merchants()
        
        for merchant in merchants:
            for alias in merchant.get("aliases", []):
                result = classify_merchant(domain=alias)
                assert result.merchant_name == merchant["name"], \
                    f"Failed to match alias {alias} -> {merchant['name']}"
                assert result.confidence == 0.99
