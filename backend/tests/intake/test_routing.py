"""Tests for backend.intake.routing (user resolution for inbound emails)."""
from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest

from backend.app.schemas import InboundEmail
from backend.intake.routing import (
    DEMO_USER_ID,
    inbox_address_for,
    register_inbox,
    reset_registry,
    resolve_user,
)

SEED_EMAILS_DIR = Path(__file__).parent.parent.parent.parent / "shared" / "seed" / "emails"
SEED_FILES = [
    "hollister_10_percent.eml",
    "target_jsonld_offer.eml",
    "chipotle_plaintext.eml",
    "nike_promo.eml",
    "amazon_receipt.eml",
]


def _parse_eml(raw: bytes) -> InboundEmail:
    try:
        from backend.extraction.clean import parse_eml
    except ImportError:
        from backend.extraction.pipeline import parse_eml
    return parse_eml(raw)


def make_email(
    to: str = "someone@example.com",
    mailbox_hash: str = "",
) -> InboundEmail:
    return InboundEmail(
        MessageID="test-msg-1",
        FromFull={"Email": "rewards@store.com", "Name": "Store"},
        ToFull=[{"Email": to, "Name": ""}],
        Subject="Test",
        TextBody="hello",
        Date="Mon, 13 Oct 2025 10:00:00 +0000",
        MailboxHash=mailbox_hash,
    )


@pytest.fixture(autouse=True)
def clean_registry():
    reset_registry()
    yield
    reset_registry()


class TestMailboxHash:
    def test_mailbox_hash_routes_demo_user(self):
        email = make_email(mailbox_hash="aamir")
        assert resolve_user(email) == DEMO_USER_ID

    def test_mailbox_hash_case_insensitive(self):
        email = make_email(mailbox_hash="DEMO")
        assert resolve_user(email) == DEMO_USER_ID

    def test_mailbox_hash_takes_priority_over_to(self):
        user = uuid4()
        register_inbox("priority-test", user)
        email = make_email(to="aamir@lapse.app", mailbox_hash="priority-test")
        assert resolve_user(email) == user

    def test_unknown_mailbox_hash_falls_through_to_recipient(self):
        email = make_email(to="demo@lapse.app", mailbox_hash="nobody")
        assert resolve_user(email) == DEMO_USER_ID


class TestLapseAddress:
    def test_lapse_local_part(self):
        assert resolve_user(make_email(to="aamir@lapse.app")) == DEMO_USER_ID
        assert resolve_user(make_email(to="demo@lapse.app")) == DEMO_USER_ID

    def test_lapse_local_part_case_insensitive(self):
        assert resolve_user(make_email(to="AAMIR@LAPSE.APP")) == DEMO_USER_ID

    def test_lapse_plus_tag_routes_to_base_local_part(self):
        assert resolve_user(make_email(to="aamir+stores@lapse.app")) == DEMO_USER_ID

    def test_unknown_lapse_address(self):
        assert resolve_user(make_email(to="stranger@lapse.app")) is None


class TestPostmarkDefaultInbound:
    def test_bare_hash_address(self):
        email = make_email(to="aamir@inbound.postmarkapp.com")
        assert resolve_user(email) == DEMO_USER_ID

    def test_server_plus_hash_address(self):
        email = make_email(to="a1b2c3server+demo@inbound.postmarkapp.com")
        assert resolve_user(email) == DEMO_USER_ID

    def test_case_insensitive(self):
        email = make_email(to="SERVER+AAMIR@INBOUND.POSTMARKAPP.COM")
        assert resolve_user(email) == DEMO_USER_ID

    def test_unknown_hash(self):
        email = make_email(to="server+nobody@inbound.postmarkapp.com")
        assert resolve_user(email) is None


class TestRegistry:
    def test_register_inbox_and_resolve(self):
        user = uuid4()
        register_inbox("newuser", user)
        assert resolve_user(make_email(to="newuser@lapse.app")) == user
        assert resolve_user(make_email(mailbox_hash="newuser")) == user

    def test_register_inbox_rejects_empty(self):
        with pytest.raises(ValueError):
            register_inbox("   ", uuid4())

    def test_unknown_everything_returns_none(self):
        assert resolve_user(make_email(to="random@gmail.com")) is None

    def test_inbox_address_for_demo_user(self):
        addr = inbox_address_for(DEMO_USER_ID)
        assert addr.endswith("@lapse.app")
        assert resolve_user(make_email(to=addr)) == DEMO_USER_ID

    def test_inbox_address_for_unregistered_user_round_trips(self):
        user = uuid4()
        addr = inbox_address_for(user)
        assert addr.endswith("@lapse.app")
        assert resolve_user(make_email(to=addr)) == user


class TestSeedEmails:
    @pytest.mark.parametrize("filename", SEED_FILES)
    def test_seed_email_routes_to_demo_user(self, filename: str):
        raw = (SEED_EMAILS_DIR / filename).read_bytes()
        email = _parse_eml(raw)
        assert resolve_user(email) == DEMO_USER_ID
