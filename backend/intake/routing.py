"""User routing for inbound emails.

Resolves which Lapse user an inbound email belongs to, in priority order:

1. Postmark ``MailboxHash`` (set when the message was delivered to a
   plus-addressed inbox, e.g. ``server+aamir@inbound.postmarkapp.com``).
2. The recipient local-part on the ``lapse.app`` domain
   (``aamir@lapse.app`` -> user).
3. Postmark default inbound addresses: ``<hash>@inbound.postmarkapp.com``
   and ``<server>+<hash>@inbound.postmarkapp.com``.

All matching is case-insensitive. Unknown addresses resolve to ``None``.

The inbox registry is an in-memory dict seeded with the demo user; register
additional inboxes with :func:`register_inbox`.
"""
from __future__ import annotations

import threading
from uuid import UUID

from backend.app.schemas import InboundEmail

LAPSE_DOMAIN = "lapse.app"
POSTMARK_INBOUND_DOMAIN = "inbound.postmarkapp.com"

DEMO_USER_ID = UUID("00000000-0000-0000-0000-000000000001")

_registry_lock = threading.Lock()
# local-part / mailbox hash (lowercase) -> user id
_inbox_registry: dict[str, UUID] = {}


def _seed_registry() -> None:
    _inbox_registry.clear()
    _inbox_registry["aamir"] = DEMO_USER_ID
    _inbox_registry["demo"] = DEMO_USER_ID


_seed_registry()


def register_inbox(local_part: str, user_id: UUID) -> None:
    """Register ``<local_part>@lapse.app`` (and MailboxHash) for a user."""
    key = local_part.strip().lower()
    if not key:
        raise ValueError("local_part must be non-empty")
    with _registry_lock:
        _inbox_registry[key] = user_id


def reset_registry() -> None:
    """Restore the registry to its seeded state (intended for tests)."""
    with _registry_lock:
        _seed_registry()


def _lookup(key: str) -> UUID | None:
    with _registry_lock:
        return _inbox_registry.get(key)


def _recipient_addresses(email: InboundEmail) -> list[str]:
    addresses: list[str] = []
    for recipient in email.ToFull or []:
        addr = str(recipient.get("Email") or "").strip().lower()
        if addr and "@" in addr:
            addresses.append(addr)
    # Some payloads carry a raw "To" header string as well; schemas.InboundEmail
    # does not define it, but tolerate it if present.
    raw_to = getattr(email, "To", None)
    if isinstance(raw_to, str):
        for piece in raw_to.split(","):
            addr = piece.strip().lower()
            if addr and "@" in addr and addr not in addresses:
                addresses.append(addr)
    return addresses


def resolve_user(email: InboundEmail) -> UUID | None:
    """Resolve the owning user for an inbound email, or ``None`` if unknown."""
    mailbox_hash = (email.MailboxHash or "").strip().lower()
    if mailbox_hash:
        user_id = _lookup(mailbox_hash)
        if user_id is not None:
            return user_id

    for addr in _recipient_addresses(email):
        local, _, domain = addr.partition("@")
        if domain == LAPSE_DOMAIN:
            user_id = _lookup(local)
            if user_id is None and "+" in local:
                # aamir+stores@lapse.app -> aamir
                user_id = _lookup(local.split("+", 1)[0])
            if user_id is not None:
                return user_id
        elif domain == POSTMARK_INBOUND_DOMAIN:
            # <server>+<hash>@inbound.postmarkapp.com or <hash>@inbound...
            hash_part = local.split("+", 1)[1] if "+" in local else local
            user_id = _lookup(hash_part)
            if user_id is not None:
                return user_id

    return None


def inbox_address_for(user_id: UUID) -> str:
    """Return the user's lapse.app inbox address.

    If the user has no registered inbox yet, a deterministic one is created
    from the user id so the address round-trips through :func:`resolve_user`.
    """
    with _registry_lock:
        for local, registered_id in _inbox_registry.items():
            if registered_id == user_id:
                return f"{local}@{LAPSE_DOMAIN}"
        local = f"user-{user_id.hex[:12]}"
        _inbox_registry[local] = user_id
        return f"{local}@{LAPSE_DOMAIN}"
