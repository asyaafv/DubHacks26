"""Email deduplication.

An email is a duplicate for a user when EITHER:

- its Postmark ``MessageID`` has already been processed for that user, OR
- its content hash matches one already processed for that user. The content
  hash is ``sha256(sender_domain + subject + text)`` after normalization
  (lowercased, whitespace collapsed, tracking query params stripped from
  URLs), so an identical re-send with a fresh MessageID is still skipped.

Dedupe state is per-user: the same email delivered to two different users is
not a duplicate.

By default state lives in a thread-safe in-memory store. If ``DATABASE_URL``
is set, a Postgres-backed store is used instead (table ``processed_emails``
with a ``content_hash`` column); the driver (psycopg or asyncpg) is imported
lazily and any failure falls back to the in-memory store.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import threading
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID

from backend.app.schemas import InboundEmail

logger = logging.getLogger(__name__)

PROCESSED_EMAILS_DDL = """
CREATE TABLE IF NOT EXISTS processed_emails (
    message_id TEXT NOT NULL,
    user_id UUID NOT NULL,
    content_hash TEXT NOT NULL,
    received_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (message_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_processed_emails_user_content
    ON processed_emails (user_id, content_hash);
"""

# ---------------------------------------------------------------------------
# Content hashing
# ---------------------------------------------------------------------------

_URL_RE = re.compile(r"https?://[^\s<>\"']+")
_WS_RE = re.compile(r"\s+")
_TRACKING_PARAMS = {
    "fbclid", "gclid", "msclkid", "dclid", "twclid", "igshid",
    "mc_cid", "mc_eid", "ck_subscriber_id", "vero_id", "ref",
}


def _is_tracking_param(name: str) -> bool:
    name = name.lower()
    return name.startswith("utm_") or name in _TRACKING_PARAMS


def _strip_tracking(url: str) -> str:
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.query:
        return url
    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking_param(k)
    ]
    return urlunsplit(parts._replace(query=urlencode(kept)))


def _normalize(text: str) -> str:
    return _WS_RE.sub(" ", text).strip().lower()


def content_hash(email: InboundEmail) -> str:
    """sha256 of normalized sender_domain + subject + text body."""
    sender = str((email.FromFull or {}).get("Email") or "").strip().lower()
    sender_domain = sender.rpartition("@")[2]
    subject = _normalize(email.Subject or "")
    body = email.TextBody or email.HtmlBody or ""
    body = _URL_RE.sub(lambda m: _strip_tracking(m.group(0)), body)
    body = _normalize(body)
    payload = "\n".join((sender_domain, subject, body))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------


class InMemoryDedupeStore:
    """Thread-safe in-memory dedupe store (the default)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._message_ids: set[tuple[UUID, str]] = set()
        self._content_hashes: set[tuple[UUID, str]] = set()

    def seen(self, user_id: UUID, message_id: str, digest: str) -> bool:
        with self._lock:
            return (
                (user_id, message_id) in self._message_ids
                or (user_id, digest) in self._content_hashes
            )

    def add(self, user_id: UUID, message_id: str, digest: str) -> None:
        with self._lock:
            self._message_ids.add((user_id, message_id))
            self._content_hashes.add((user_id, digest))


class PostgresDedupeStore:
    """Postgres-backed store using the ``processed_emails`` table.

    Prefers psycopg (sync); falls back to asyncpg run on a private event
    loop. Both drivers are imported lazily so neither is a hard dependency.
    """

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn
        self._lock = threading.Lock()
        self._psycopg = None
        self._asyncpg = None
        try:
            import psycopg  # type: ignore[import-not-found]

            self._psycopg = psycopg
        except ImportError:
            import asyncpg  # type: ignore[import-not-found]

            self._asyncpg = asyncpg
        self._execute(PROCESSED_EMAILS_DDL)

    _SEEN_SQL = (
        "SELECT 1 FROM processed_emails "
        "WHERE user_id = {p1} AND (message_id = {p2} OR content_hash = {p3}) "
        "LIMIT 1"
    )
    _INSERT_SQL = (
        "INSERT INTO processed_emails (message_id, user_id, content_hash) "
        "VALUES ({p2}, {p1}, {p3}) ON CONFLICT DO NOTHING"
    )

    def _execute(self, sql: str, params: tuple = (), fetch: bool = False):
        if self._psycopg is not None:
            with self._lock, self._psycopg.connect(self._dsn) as conn:
                cur = conn.execute(sql.format(p1="%s", p2="%s", p3="%s"), params)
                return cur.fetchone() if fetch else None
        import asyncio

        async def _run():
            conn = await self._asyncpg.connect(self._dsn)
            try:
                formatted = sql.format(p1="$1", p2="$2", p3="$3")
                if fetch:
                    return await conn.fetchrow(formatted, *params)
                await conn.execute(formatted, *params)
                return None
            finally:
                await conn.close()

        with self._lock:
            return asyncio.new_event_loop().run_until_complete(_run())

    def seen(self, user_id: UUID, message_id: str, digest: str) -> bool:
        row = self._execute(
            self._SEEN_SQL, (str(user_id), message_id, digest), fetch=True
        )
        return row is not None

    def add(self, user_id: UUID, message_id: str, digest: str) -> None:
        self._execute(self._INSERT_SQL, (str(user_id), message_id, digest))


_store_lock = threading.Lock()
_store: InMemoryDedupeStore | PostgresDedupeStore | None = None


def _get_store() -> InMemoryDedupeStore | PostgresDedupeStore:
    global _store
    with _store_lock:
        if _store is None:
            dsn = os.environ.get("DATABASE_URL")
            if dsn:
                try:
                    _store = PostgresDedupeStore(dsn)
                except Exception as exc:  # pragma: no cover - depends on env
                    logger.warning(
                        "Postgres dedupe store unavailable (%s); "
                        "falling back to in-memory store",
                        exc,
                    )
            if _store is None:
                _store = InMemoryDedupeStore()
        return _store


def reset(*, use_memory: bool = True) -> None:
    """Reset dedupe state. With ``use_memory=True`` (default) the next call
    uses a fresh in-memory store regardless of DATABASE_URL (for tests)."""
    global _store
    with _store_lock:
        _store = InMemoryDedupeStore() if use_memory else None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def seen_before(email: InboundEmail, user_id: UUID) -> bool:
    """True if this email was already processed for this user."""
    return _get_store().seen(user_id, email.MessageID, content_hash(email))


def mark_processed(email: InboundEmail, user_id: UUID) -> None:
    """Record this email as processed for this user."""
    _get_store().add(user_id, email.MessageID, content_hash(email))
