"""Tests for backend.intake.dedupe (MessageID + content-hash deduplication)."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from backend.app.schemas import InboundEmail
from backend.intake.dedupe import (
    content_hash,
    mark_processed,
    reset,
    seen_before,
)

USER_A = UUID("00000000-0000-0000-0000-000000000001")
USER_B = UUID("00000000-0000-0000-0000-000000000002")


def make_email(
    message_id: str = "msg-1",
    sender: str = "rewards@store.com",
    subject: str = "10% off your next order",
    text: str = "Use code SAVE10 at checkout.",
) -> InboundEmail:
    return InboundEmail(
        MessageID=message_id,
        FromFull={"Email": sender, "Name": "Store"},
        ToFull=[{"Email": "demo@lapse.app", "Name": ""}],
        Subject=subject,
        TextBody=text,
        Date="Mon, 13 Oct 2025 10:00:00 +0000",
    )


@pytest.fixture(autouse=True)
def fresh_store():
    reset()
    yield
    reset()


class TestMessageIdDedupe:
    def test_unseen_email_is_not_duplicate(self):
        assert seen_before(make_email(), USER_A) is False

    def test_same_message_id_is_skipped(self):
        email = make_email()
        mark_processed(email, USER_A)
        assert seen_before(email, USER_A) is True

    def test_same_message_id_different_content_still_skipped(self):
        mark_processed(make_email(message_id="msg-x"), USER_A)
        changed = make_email(message_id="msg-x", subject="totally different")
        assert seen_before(changed, USER_A) is True


class TestContentHashDedupe:
    def test_identical_resend_with_new_message_id_is_skipped(self):
        mark_processed(make_email(message_id="msg-1"), USER_A)
        resend = make_email(message_id="msg-2")
        assert seen_before(resend, USER_A) is True

    def test_resend_with_different_tracking_params_is_skipped(self):
        original = make_email(
            message_id="msg-1",
            text="Shop now: https://store.com/sale?item=1&utm_campaign=a&gclid=x1",
        )
        resend = make_email(
            message_id="msg-2",
            text="Shop now:  https://store.com/sale?item=1&utm_campaign=b&gclid=y2 ",
        )
        mark_processed(original, USER_A)
        assert seen_before(resend, USER_A) is True
        assert content_hash(original) == content_hash(resend)

    def test_different_email_from_same_sender_is_not_duplicate(self):
        mark_processed(make_email(message_id="msg-1"), USER_A)
        other = make_email(
            message_id="msg-2",
            subject="Your receipt",
            text="Order total: $42.00",
        )
        assert seen_before(other, USER_A) is False

    def test_meaningful_url_params_change_the_hash(self):
        a = make_email(text="https://store.com/sale?item=1")
        b = make_email(text="https://store.com/sale?item=2")
        assert content_hash(a) != content_hash(b)


class TestUserIsolation:
    def test_same_email_to_two_users_is_not_duplicate(self):
        email = make_email()
        mark_processed(email, USER_A)
        assert seen_before(email, USER_B) is False
        mark_processed(email, USER_B)
        assert seen_before(email, USER_B) is True
        assert seen_before(email, USER_A) is True

    def test_mark_is_idempotent(self):
        email = make_email()
        mark_processed(email, USER_A)
        mark_processed(email, USER_A)
        assert seen_before(email, USER_A) is True


class TestThreadSafety:
    def test_concurrent_marks_and_checks(self):
        import threading

        errors: list[Exception] = []

        def worker(i: int) -> None:
            try:
                user = uuid4()
                email = make_email(message_id=f"msg-{i}", subject=f"subject {i}")
                assert seen_before(email, user) is False
                mark_processed(email, user)
                assert seen_before(email, user) is True
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
