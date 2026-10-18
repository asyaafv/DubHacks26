"""
Lapse Contract Tests

Validates:
1. Seed data files conform to Pydantic schemas
2. Stub endpoints return schema-valid responses
3. Type consistency between schemas and API
"""

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

# Import schemas for validation
from backend.app.schemas import (
    Card,
    CardNetwork,
    CategoryRate,
    ChosenReward,
    ClassifyMerchantRequest,
    ClassifyMerchantResult,
    DemoInjectRequest,
    EmailClassification,
    Event,
    EventType,
    FieldConfidence,
    HealthCheck,
    InboundEmail,
    InboundResult,
    LookupRequest,
    LookupResult,
    Membership,
    Merchant,
    Reward,
    RewardKind,
    RewardSource,
    RewardStatus,
    ScoredReward,
    StackRequest,
    StackResult,
    SyncResponse,
    Wallet,
)

# Import FastAPI app
from backend.app.main import app

SEED_DIR = Path(__file__).parent.parent.parent / "shared" / "seed"


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def seed_merchants():
    """Load seed merchants JSON."""
    with open(SEED_DIR / "seed_merchants.json") as f:
        return json.load(f)


@pytest.fixture
def seed_rewards():
    """Load seed rewards JSON."""
    with open(SEED_DIR / "seed_rewards.json") as f:
        return json.load(f)


@pytest.fixture
def seed_cards():
    """Load seed cards JSON."""
    with open(SEED_DIR / "seed_cards.json") as f:
        return json.load(f)


@pytest.fixture
def seed_memberships():
    """Load seed memberships JSON."""
    with open(SEED_DIR / "seed_memberships.json") as f:
        return json.load(f)


@pytest.fixture
def demo_user_id():
    """Demo user UUID."""
    return "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def client():
    """Sync HTTP client for testing FastAPI app."""
    from fastapi.testclient import TestClient
    return TestClient(app)


# =============================================================================
# SEED DATA VALIDATION TESTS
# =============================================================================


class TestSeedMerchants:
    """Validate seed_merchants.json against Merchant schema."""

    def test_merchants_file_exists(self):
        assert (SEED_DIR / "seed_merchants.json").exists()

    def test_merchants_valid_json(self, seed_merchants):
        assert "merchants" in seed_merchants
        assert len(seed_merchants["merchants"]) >= 50

    def test_each_merchant_valid(self, seed_merchants):
        for m in seed_merchants["merchants"]:
            # Validate UUID format
            assert UUID(m["id"])
            
            # Validate required fields
            assert m["name"]
            assert m["domain"]
            assert m["mcc"]
            assert len(m["mcc"]) == 4
            assert m["category"]
            
            # Validate MCC is numeric
            assert m["mcc"].isdigit()

    def test_merchant_domains_unique(self, seed_merchants):
        domains = [m["domain"] for m in seed_merchants["merchants"]]
        assert len(domains) == len(set(domains))


class TestSeedRewards:
    """Validate seed_rewards.json against Reward schema."""

    def test_rewards_file_exists(self):
        assert (SEED_DIR / "seed_rewards.json").exists()

    def test_rewards_valid_json(self, seed_rewards):
        assert "rewards" in seed_rewards
        assert "demo_user_id" in seed_rewards
        assert len(seed_rewards["rewards"]) >= 20

    def test_each_reward_valid(self, seed_rewards):
        for r in seed_rewards["rewards"]:
            # Validate UUIDs
            assert UUID(r["id"])
            assert UUID(r["user_id"])
            if r.get("merchant_id"):
                assert UUID(r["merchant_id"])
            
            # Validate enum values
            assert r["kind"] in [k.value for k in RewardKind]
            assert r["source"] in [s.value for s in RewardSource]
            assert r["status"] in [s.value for s in RewardStatus]
            
            # Validate value is positive
            assert Decimal(r["value"]) >= 0
            
            # Validate confidence scores
            if "field_confidence" in r:
                for key, val in r["field_confidence"].items():
                    assert 0.0 <= val <= 1.0
            if "overall_confidence" in r:
                assert 0.0 <= r["overall_confidence"] <= 1.0

    def test_rewards_have_required_fields(self, seed_rewards):
        required = ["id", "user_id", "merchant_name", "category", "mcc", 
                    "kind", "value", "source", "status"]
        for r in seed_rewards["rewards"]:
            for field in required:
                assert field in r, f"Missing field: {field}"

    def test_expiring_rewards_exist(self, seed_rewards):
        """Check that some rewards expire within 3 days of 2026-10-18."""
        base = datetime(2026, 10, 18)
        expiring_soon = []
        for r in seed_rewards["rewards"]:
            if r.get("expires_at"):
                exp = datetime.fromisoformat(r["expires_at"].replace("Z", "+00:00"))
                if (exp.replace(tzinfo=None) - base).days <= 3:
                    expiring_soon.append(r)
        
        assert len(expiring_soon) >= 3, "Need at least 3 rewards expiring within 3 days"

    def test_needs_review_rewards_exist(self, seed_rewards):
        """Check that some rewards have needs_review status."""
        needs_review = [r for r in seed_rewards["rewards"] if r["status"] == "needs_review"]
        assert len(needs_review) >= 2, "Need at least 2 rewards with needs_review status"


class TestSeedCards:
    """Validate seed_cards.json against Card schema."""

    def test_cards_file_exists(self):
        assert (SEED_DIR / "seed_cards.json").exists()

    def test_cards_valid_json(self, seed_cards):
        assert "cards" in seed_cards
        assert len(seed_cards["cards"]) >= 3

    def test_each_card_valid(self, seed_cards):
        for c in seed_cards["cards"]:
            # Validate UUIDs
            assert UUID(c["id"])
            assert UUID(c["user_id"])
            
            # Validate network
            assert c["network"] in [n.value for n in CardNetwork]
            
            # Validate rates
            assert Decimal(c["base_rate"]) >= 0
            for rate in c.get("category_rates", []):
                assert Decimal(rate["rate"]) >= 0
            
            # Should be demo cards
            assert c.get("is_demo", True)

    def test_visa_cards_exist(self, seed_cards):
        """All cards should be Visa for this hackathon track."""
        visa_cards = [c for c in seed_cards["cards"] if c["network"] == "visa"]
        assert len(visa_cards) == len(seed_cards["cards"])


class TestSeedMemberships:
    """Validate seed_memberships.json against Membership schema."""

    def test_memberships_file_exists(self):
        assert (SEED_DIR / "seed_memberships.json").exists()

    def test_memberships_valid_json(self, seed_memberships):
        assert "memberships" in seed_memberships
        assert len(seed_memberships["memberships"]) >= 3

    def test_each_membership_valid(self, seed_memberships):
        for m in seed_memberships["memberships"]:
            # Validate UUIDs
            assert UUID(m["id"])
            assert UUID(m["user_id"])
            
            # Validate required fields
            assert m["merchant_name"]
            assert m["program_name"]


class TestSampleEmails:
    """Validate sample .eml files exist."""

    def test_emails_directory_exists(self):
        assert (SEED_DIR / "emails").is_dir()

    def test_required_emails_exist(self):
        emails_dir = SEED_DIR / "emails"
        required = [
            "hollister_10_percent.eml",
            "target_jsonld_offer.eml",
            "chipotle_plaintext.eml",
            "nike_promo.eml",
            "amazon_receipt.eml",
        ]
        for filename in required:
            assert (emails_dir / filename).exists(), f"Missing: {filename}"

    def test_emails_not_empty(self):
        emails_dir = SEED_DIR / "emails"
        for eml_file in emails_dir.glob("*.eml"):
            assert eml_file.stat().st_size > 100, f"Email too small: {eml_file.name}"


class TestFixtures:
    """Validate test fixture files."""

    def test_hollister_fixture_exists(self):
        fixture_path = SEED_DIR / "fixtures" / "hollister_500_cart.json"
        assert fixture_path.exists()

    def test_hollister_fixture_valid(self):
        fixture_path = SEED_DIR / "fixtures" / "hollister_500_cart.json"
        with open(fixture_path) as f:
            data = json.load(f)
        
        assert "request" in data
        assert "expected_result" in data
        assert Decimal(data["request"]["cart_total"]) == Decimal("500.00")


# =============================================================================
# API ENDPOINT TESTS
# =============================================================================


class TestHealthEndpoint:
    """Test /health endpoint."""

    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_valid_schema(self, client):
        response = client.get("/health")
        data = response.json()
        
        # Validate against HealthCheck schema
        health = HealthCheck(**data)
        assert health.status == "healthy"
        assert health.version == "0.1.0"


class TestWalletEndpoint:
    """Test /wallet endpoint."""

    def test_get_wallet_returns_200(self, client, demo_user_id):
        response = client.get(
            "/wallet",
            headers={"X-User-Id": demo_user_id}
        )
        assert response.status_code == 200

    def test_get_wallet_valid_schema(self, client, demo_user_id):
        response = client.get(
            "/wallet",
            headers={"X-User-Id": demo_user_id}
        )
        data = response.json()
        
        # Validate against Wallet schema
        wallet = Wallet(**data)
        assert str(wallet.user_id) == demo_user_id
        assert len(wallet.cards) >= 1
        assert len(wallet.memberships) >= 1


class TestStackEndpoint:
    """Test /stack endpoint."""

    def test_stack_returns_200(self, client, demo_user_id):
        response = client.post(
            "/stack",
            headers={"X-User-Id": demo_user_id},
            json={
                "user_id": demo_user_id,
                "domain": "hollisterco.com",
                "cart_total": "500.00",
                "items": []
            }
        )
        assert response.status_code == 200

    def test_stack_valid_schema(self, client, demo_user_id):
        response = client.post(
            "/stack",
            headers={"X-User-Id": demo_user_id},
            json={
                "user_id": demo_user_id,
                "domain": "target.com",
                "cart_total": "100.00",
                "items": []
            }
        )
        data = response.json()
        
        # Validate against StackResult schema
        result = StackResult(**data)
        assert result.original_price == Decimal("100.00")
        assert result.final_price <= result.original_price


class TestLookupEndpoint:
    """Test /lookup endpoint."""

    def test_lookup_returns_200(self, client, demo_user_id):
        response = client.post(
            "/lookup",
            headers={"X-User-Id": demo_user_id},
            json={
                "user_id": demo_user_id,
                "domain": "target.com",
                "limit": 3
            }
        )
        assert response.status_code == 200

    def test_lookup_valid_schema(self, client, demo_user_id):
        response = client.post(
            "/lookup",
            headers={"X-User-Id": demo_user_id},
            json={
                "user_id": demo_user_id,
                "domain": "target.com",
                "limit": 3
            }
        )
        data = response.json()
        
        # Validate against LookupResult schema
        result = LookupResult(**data)
        assert len(result.rewards) <= 3


class TestSyncEndpoint:
    """Test /sync endpoint."""

    def test_sync_returns_200(self, client, demo_user_id):
        response = client.get(
            "/sync",
            headers={"X-User-Id": demo_user_id}
        )
        assert response.status_code == 200

    def test_sync_valid_schema(self, client, demo_user_id):
        response = client.get(
            "/sync",
            headers={"X-User-Id": demo_user_id}
        )
        data = response.json()
        
        # Validate against SyncResponse schema
        result = SyncResponse(**data)
        assert str(result.user_id) == demo_user_id
        assert len(result.rewards) >= 1


class TestClassifyMerchantEndpoint:
    """Test /classify-merchant endpoint."""

    def test_known_merchant(self, client):
        response = client.post(
            "/classify-merchant",
            json={"domain": "target.com"}
        )
        assert response.status_code == 200
        data = response.json()
        
        result = ClassifyMerchantResult(**data)
        assert result.merchant_name == "Target"
        assert result.confidence > 0.9
        assert result.is_new is False

    def test_unknown_merchant(self, client):
        response = client.post(
            "/classify-merchant",
            json={"domain": "unknownstore12345.com", "page_title": "Unknown Store"}
        )
        assert response.status_code == 200
        data = response.json()
        
        result = ClassifyMerchantResult(**data)
        assert result.is_new is True
        assert result.confidence < 0.5


class TestInboundEndpoint:
    """Test /inbound endpoint."""

    def test_inbound_returns_200(self, client, demo_user_id):
        response = client.post(
            "/inbound",
            headers={"X-User-Id": demo_user_id},
            json={
                "MessageID": "test-msg-001",
                "FromFull": {"Email": "rewards@test.com", "Name": "Test"},
                "ToFull": [{"Email": "demo@lapse.app", "Name": ""}],
                "Subject": "Test Offer",
                "TextBody": "Use code TEST10 for 10% off",
                "HtmlBody": None,
                "Date": "2026-10-18T10:00:00Z",
                "MailboxHash": "demo",
                "Attachments": [],
                "Headers": []
            }
        )
        assert response.status_code == 200

    def test_inbound_valid_schema(self, client, demo_user_id):
        response = client.post(
            "/inbound",
            headers={"X-User-Id": demo_user_id},
            json={
                "MessageID": "test-msg-002",
                "FromFull": {"Email": "rewards@test.com", "Name": "Test"},
                "ToFull": [{"Email": "demo@lapse.app", "Name": ""}],
                "Subject": "Test Offer",
                "TextBody": "Test email body",
                "HtmlBody": None,
                "Date": "2026-10-18T10:00:00Z",
                "MailboxHash": "demo",
                "Attachments": [],
                "Headers": []
            }
        )
        data = response.json()
        
        result = InboundResult(**data)
        assert result.message_id == "test-msg-002"
        assert result.classification in [c.value for c in EmailClassification]


class TestDemoInjectEndpoint:
    """Test /demo/inject endpoint."""

    def test_inject_valid_file(self, client, demo_user_id):
        response = client.post(
            "/demo/inject",
            headers={"X-User-Id": demo_user_id},
            json={"eml_filename": "hollister_10_percent.eml"}
        )
        assert response.status_code == 200
        
        data = response.json()
        result = InboundResult(**data)
        assert result.classification == EmailClassification.reward.value

    def test_inject_invalid_file(self, client, demo_user_id):
        response = client.post(
            "/demo/inject",
            headers={"X-User-Id": demo_user_id},
            json={"eml_filename": "nonexistent.eml"}
        )
        assert response.status_code == 404


# =============================================================================
# SCHEMA CONSISTENCY TESTS
# =============================================================================


class TestSchemaConsistency:
    """Test that schemas are internally consistent."""

    def test_reward_kind_values(self):
        """All RewardKind values should be valid."""
        expected = {"percent_off", "amount_off", "points", "free_item", "bogo", "cashback"}
        actual = {k.value for k in RewardKind}
        assert expected == actual

    def test_reward_source_values(self):
        """All RewardSource values should be valid."""
        expected = {"email_jsonld", "gliner", "regex", "manual", "seed"}
        actual = {s.value for s in RewardSource}
        assert expected == actual

    def test_reward_status_values(self):
        """All RewardStatus values should be valid."""
        expected = {"active", "needs_review", "used", "expired"}
        actual = {s.value for s in RewardStatus}
        assert expected == actual

    def test_event_type_values(self):
        """All EventType values should be valid."""
        expected = {"reward_added", "reward_expiring", "reward_updated", "reward_used", "sync_complete"}
        actual = {e.value for e in EventType}
        assert expected == actual
