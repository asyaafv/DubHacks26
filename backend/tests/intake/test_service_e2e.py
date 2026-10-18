"""End-to-end intake tests (Agent C): FastAPI TestClient against the real app.

Covers: every seed .eml through /demo/inject with expected rewards, dedupe +
force replay, raw Postmark JSON through /inbound with MailboxHash routing,
unknown recipients, /demo/emails, reward_added events, and /sync + /wallet
visibility with per-user isolation.

/sync and /wallet require a database on app.state; these tests install a
minimal in-memory fake (real Postgres is not available in CI) whose wallet
counts are computed from the same in-memory rewards store the intake service
persists to.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app import main
from backend.app.schemas import EventType, RewardKind, RewardStatus, Wallet
from backend.intake import service

REPO_ROOT = Path(__file__).resolve().parents[3]
SEED_EMAILS_DIR = REPO_ROOT / "shared" / "seed" / "emails"
DEMO_USER = UUID("00000000-0000-0000-0000-000000000001")
OTHER_USER = UUID("00000000-0000-0000-0000-000000000002")

ALL_SEED_EMAILS = [
    "amazon_receipt.eml",
    "chipotle_plaintext.eml",
    "hollister_10_percent.eml",
    "nike_promo.eml",
    "target_jsonld_offer.eml",
]

# filename -> (count, kind, value, code, merchant substring)
EXPECTED = {
    "hollister_10_percent.eml": (1, RewardKind.percent_off, Decimal("10"), "HCOFALL10", "hollister"),
    "chipotle_plaintext.eml": (1, RewardKind.free_item, Decimal("1"), "FREEGUAC", "chipotle"),
    "nike_promo.eml": (1, RewardKind.percent_off, Decimal("20"), None, "nike"),
    "target_jsonld_offer.eml": (1, RewardKind.amount_off, Decimal("5.00"), "TARGET5", "target"),
    "amazon_receipt.eml": (0, None, None, None, None),
}


# =============================================================================
# In-memory stand-in for the decisions Postgres database (/sync + /wallet)
# =============================================================================


class FakeRepo:
    def __init__(self, user_id: UUID):
        self.user_id = user_id

    async def get_wallet(self) -> Wallet:
        now = datetime.now(timezone.utc)
        active = [
            r
            for r in main.get_rewards()
            if r.user_id == self.user_id and r.status == RewardStatus.active
        ]
        expiring = [
            r
            for r in active
            if r.expires_at
            and r.expires_at.replace(tzinfo=r.expires_at.tzinfo or timezone.utc)
            <= now + timedelta(days=3)
        ]
        return Wallet(
            user_id=self.user_id,
            cards=[],
            memberships=[],
            active_rewards_count=len(active),
            expiring_soon_count=len(expiring),
        )


class FakeDatabase:
    @asynccontextmanager
    async def transaction(self, user_id: UUID):
        yield FakeRepo(user_id)

    async def close(self):  # called by the app lifespan on shutdown
        pass


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture()
def client():
    original_rewards = main._rewards
    main._rewards = []  # clean in-memory store per test
    service.reset_intake_state()
    with TestClient(main.app) as test_client:
        main.app.state.database = FakeDatabase()
        yield test_client
    main._rewards = original_rewards
    service.reset_intake_state()


def inject(client, filename: str, *, user_id: UUID | None = None, force: bool = False):
    body: dict = {"eml_filename": filename}
    if user_id is not None:
        body["user_id"] = str(user_id)
    if force:
        body["force"] = True
    return client.post("/demo/inject", json=body)


def postmark_payload(filename: str, mailbox_hash: str = "aamir", message_id: str | None = None) -> dict:
    """Build a Postmark-shaped inbound webhook payload from a seed .eml."""
    from backend.extraction.pipeline import parse_eml

    email = parse_eml((SEED_EMAILS_DIR / filename).read_bytes())
    return {
        # Postmark sends many more fields than InboundEmail declares; include
        # extras to prove the endpoint is tolerant of them.
        "MessageID": message_id or f"pm-{uuid4()}",
        "MessageStream": "inbound",
        "From": email.FromFull.get("Email", ""),
        "FromName": email.FromFull.get("Name", ""),
        "FromFull": email.FromFull,
        "To": ", ".join(t.get("Email", "") for t in email.ToFull),
        "ToFull": email.ToFull,
        "Cc": "",
        "CcFull": [],
        "Bcc": "",
        "BccFull": [],
        "OriginalRecipient": email.ToFull[0].get("Email", "") if email.ToFull else "",
        "Subject": email.Subject,
        "Date": email.Date,
        "MailboxHash": mailbox_hash,
        "TextBody": email.TextBody,
        "HtmlBody": email.HtmlBody,
        "StrippedTextReply": "",
        "Tag": "",
        "Headers": [{"Name": "X-Spam-Status", "Value": "No"}],
        "Attachments": [],
    }


# =============================================================================
# /demo/inject: expected rewards per seed email
# =============================================================================


@pytest.mark.parametrize("filename", ALL_SEED_EMAILS)
def test_each_seed_email_produces_expected_rewards(client, filename):
    count, kind, value, code, merchant = EXPECTED[filename]

    response = inject(client, filename)
    assert response.status_code == 200
    result = response.json()

    assert result["rewards_extracted"] == count
    assert len(result["reward_ids"]) == count
    assert result["processing_time_ms"] >= 0
    assert result["duplicate"] is False

    stored = [r for r in main.get_rewards() if r.user_id == DEMO_USER]
    assert len(stored) == count
    if count:
        reward = stored[0]
        assert reward.kind == kind
        assert reward.value == value
        if code is not None:
            assert reward.code == code
        assert merchant in reward.merchant_name.lower()
        assert result["classification"] in ("reward", "promo")
    else:
        assert result["classification"] == "receipt"


def test_inject_unknown_file_returns_404(client):
    response = inject(client, "does_not_exist.eml")
    assert response.status_code == 404


def test_demo_emails_listing(client):
    response = client.get("/demo/emails")
    assert response.status_code == 200
    assert response.json()["emails"] == ALL_SEED_EMAILS


# =============================================================================
# Dedupe and force replay
# =============================================================================


def test_second_inject_is_deduped_and_force_replays(client):
    first = inject(client, "hollister_10_percent.eml").json()
    assert first["rewards_extracted"] == 1

    second = inject(client, "hollister_10_percent.eml").json()
    assert second["rewards_extracted"] == 0
    assert second["duplicate"] is True
    assert second["note"] == "duplicate"
    assert len([r for r in main.get_rewards() if r.user_id == DEMO_USER]) == 1

    forced = inject(client, "hollister_10_percent.eml", force=True).json()
    assert forced["rewards_extracted"] == 1
    assert forced["duplicate"] is False
    assert len([r for r in main.get_rewards() if r.user_id == DEMO_USER]) == 2


# =============================================================================
# /inbound: raw Postmark webhook payloads
# =============================================================================


def test_postmark_payload_routes_via_mailbox_hash(client):
    payload = postmark_payload("hollister_10_percent.eml", mailbox_hash="aamir")

    response = client.post("/inbound", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["rewards_extracted"] == 1
    assert result["classification"] == "reward"

    stored = [r for r in main.get_rewards() if r.user_id == DEMO_USER]
    assert len(stored) == 1
    assert stored[0].code == "HCOFALL10"


def test_postmark_duplicate_message_id_is_deduped(client):
    payload = postmark_payload("hollister_10_percent.eml", message_id="pm-dup-1")
    assert client.post("/inbound", json=payload).json()["rewards_extracted"] == 1
    repeat = client.post("/inbound", json=payload)
    assert repeat.status_code == 200  # Postmark still gets a 200
    assert repeat.json()["duplicate"] is True


def test_unknown_recipient_gets_200_with_note(client):
    payload = postmark_payload("hollister_10_percent.eml", mailbox_hash="nobody-here")
    payload["ToFull"] = [{"Email": "stranger@lapse.app", "Name": ""}]
    payload["To"] = "stranger@lapse.app"

    response = client.post("/inbound", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["rewards_extracted"] == 0
    assert result["note"] == "unknown_recipient"
    assert main.get_rewards() == []


def test_malformed_but_parseable_payload_gets_200(client):
    # Missing MessageID/FromFull/Date etc. must not trigger a 422 retry loop.
    response = client.post("/inbound", json={"TextBody": "hello", "To": "aamir@lapse.app"})
    assert response.status_code == 200

    response = client.post("/inbound", json={})
    assert response.status_code == 200
    assert response.json()["note"] == "unknown_recipient"


def test_non_json_body_gets_400(client):
    response = client.post(
        "/inbound", content=b"not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400


# =============================================================================
# Events: reward_added emitted on the /events mechanism
# =============================================================================


def test_inject_emits_reward_added_events(client):
    inject(client, "hollister_10_percent.eml")
    events = service.drain_events(DEMO_USER)
    assert len(events) == 1
    assert events[0].event_type == EventType.reward_added
    assert events[0].user_id == DEMO_USER
    assert events[0].reward_id is not None
    assert events[0].data["code"] == "HCOFALL10"
    # Drained once; queue is now empty.
    assert service.drain_events(DEMO_USER) == []


# =============================================================================
# /sync and /wallet visibility + user isolation
# =============================================================================


def test_injected_rewards_appear_in_sync_and_wallet(client):
    inject(client, "hollister_10_percent.eml")
    headers = {"X-User-Id": str(DEMO_USER)}

    sync = client.get("/sync", headers=headers)
    assert sync.status_code == 200
    sync_body = sync.json()
    assert sync_body["user_id"] == str(DEMO_USER)
    codes = [r["code"] for r in sync_body["rewards"]]
    assert codes == ["HCOFALL10"]
    assert sync_body["wallet"]["active_rewards_count"] == 1

    wallet = client.get("/wallet", headers=headers)
    assert wallet.status_code == 200
    assert wallet.json()["active_rewards_count"] == 1


def test_other_users_rewards_never_leak(client):
    inject(client, "hollister_10_percent.eml", user_id=DEMO_USER)
    inject(client, "target_jsonld_offer.eml", user_id=OTHER_USER)

    demo_sync = client.get("/sync", headers={"X-User-Id": str(DEMO_USER)}).json()
    demo_codes = {r["code"] for r in demo_sync["rewards"]}
    assert demo_codes == {"HCOFALL10"}
    assert demo_sync["wallet"]["active_rewards_count"] == 1

    other_sync = client.get("/sync", headers={"X-User-Id": str(OTHER_USER)}).json()
    other_codes = {r["code"] for r in other_sync["rewards"]}
    assert other_codes == {"TARGET5"}
    assert other_sync["wallet"]["active_rewards_count"] == 1

    demo_wallet = client.get("/wallet", headers={"X-User-Id": str(DEMO_USER)}).json()
    other_wallet = client.get("/wallet", headers={"X-User-Id": str(OTHER_USER)}).json()
    assert demo_wallet["active_rewards_count"] == 1
    assert other_wallet["active_rewards_count"] == 1

    demo_events = service.drain_events(DEMO_USER)
    other_events = service.drain_events(OTHER_USER)
    assert {e.user_id for e in demo_events} == {DEMO_USER}
    assert {e.user_id for e in other_events} == {OTHER_USER}


# =============================================================================
# Fallback transparency
# =============================================================================


def test_intake_status_reports_real_vs_fallback():
    status = service.intake_status()
    assert set(status) == {"routing", "dedupe", "redact"}
    assert set(status.values()) <= {"real", "fallback"}
    print(f"\nintake stage status: {json.dumps(status)}")


def test_fallback_redaction_keeps_promo_fields_and_participants():
    from backend.app.schemas import InboundEmail

    email = InboundEmail(
        MessageID="redact-test-1",
        FromFull={"Email": "rewards@store.com", "Name": "Store"},
        ToFull=[{"Email": "aamir@lapse.app", "Name": ""}],
        Subject="20% off",
        TextBody=(
            "Code: SAVE20. Call 415-555-1234 or email support@store.com. "
            "Card on file: 4111 1111 1111 1111. Valid through: October 20, 2026. "
            "Reply to rewards@store.com."
        ),
        HtmlBody=(
            '<script type="application/ld+json">{"discountCode": "SAVE20"}</script>'
            "<p>Call 415-555-1234</p>"
        ),
        Date="Tue, 15 Oct 2026 10:30:00 -0700",
    )
    redacted, counts = service._fallback_redact_email(email)
    text = redacted.TextBody
    assert "SAVE20" in text
    assert "October 20, 2026" in text
    assert "415-555-1234" not in text
    assert "4111 1111 1111 1111" not in text
    assert "support@store.com" not in text
    # Sender and recipient addresses are preserved.
    assert "rewards@store.com" in text
    assert counts["PHONE_NUMBER"] >= 1
    assert counts["CREDIT_CARD"] >= 1
    assert counts["EMAIL_ADDRESS"] >= 1
    # JSON-LD script block is untouched; HTML text nodes are redacted.
    assert '"discountCode": "SAVE20"' in redacted.HtmlBody
    assert "415-555-1234" not in redacted.HtmlBody
