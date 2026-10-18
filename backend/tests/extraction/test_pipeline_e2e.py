"""End-to-end tests: every seed .eml -> extract_rewards -> schema-valid Rewards."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest

from backend.app.schemas import InboundEmail, Reward, RewardKind, RewardStatus
from backend.extraction.pipeline import extract_rewards, parse_eml, run_pipeline

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_EMAILS_DIR = REPO_ROOT / "shared" / "seed" / "emails"
USER_ID = UUID("00000000-0000-0000-0000-000000000001")

# Seed emails that must yield at least one reward (classification reward/promo).
REWARD_EMAILS = [
    "hollister_10_percent.eml",
    "chipotle_plaintext.eml",
    "nike_promo.eml",
    "target_jsonld_offer.eml",
]
RECEIPT_EMAILS = ["amazon_receipt.eml"]

ALL_EMAILS = sorted(p.name for p in SEED_EMAILS_DIR.glob("*.eml"))


def _load(name: str) -> InboundEmail:
    return parse_eml((SEED_EMAILS_DIR / name).read_bytes())


def test_seed_emails_present():
    assert set(REWARD_EMAILS + RECEIPT_EMAILS) <= set(ALL_EMAILS)


@pytest.mark.parametrize("name", ALL_EMAILS)
def test_every_seed_email_runs_without_error(name: str):
    rewards = extract_rewards(_load(name), USER_ID)
    assert isinstance(rewards, list)
    for reward in rewards:
        assert isinstance(reward, Reward)


@pytest.mark.parametrize("name", REWARD_EMAILS)
def test_reward_and_promo_emails_yield_schema_valid_rewards(name: str):
    rewards = extract_rewards(_load(name), USER_ID)
    assert rewards, f"{name} should yield at least one reward"
    for reward in rewards:
        # Round-trip through Pydantic validation to prove schema validity.
        revalidated = Reward.model_validate(reward.model_dump())
        assert revalidated.user_id == USER_ID
        assert revalidated.merchant_name
        assert revalidated.mcc
        assert revalidated.value >= 0
        assert 0.0 <= revalidated.overall_confidence <= 1.0
        assert revalidated.source_email_id
        assert revalidated.status in (RewardStatus.active, RewardStatus.needs_review)


def test_hollister_yields_10_percent_off_with_expiry():
    rewards = extract_rewards(_load("hollister_10_percent.eml"), USER_ID)
    assert len(rewards) == 1
    reward = rewards[0]
    assert reward.kind == RewardKind.percent_off
    assert reward.value == Decimal("10")
    assert reward.expires_at is not None
    assert reward.expires_at.year == 2026
    assert reward.expires_at.month == 10
    assert reward.code == "HCOFALL10"
    assert "hollister" in reward.merchant_name.lower()


def test_receipt_yields_nothing():
    for name in RECEIPT_EMAILS:
        assert extract_rewards(_load(name), USER_ID) == []


def test_pipeline_reports_stage_timings():
    result = run_pipeline(_load("hollister_10_percent.eml"), USER_ID)
    timings = result.timings_ms
    assert "total_ms" in timings
    for stage in ("clean_ms", "classify_ms", "markup_ms"):
        assert stage in timings
        assert timings[stage] >= 0
    assert timings["total_ms"] >= max(v for k, v in timings.items() if k != "total_ms")
