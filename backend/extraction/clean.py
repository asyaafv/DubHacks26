"""Email parsing and cleaning: raw .eml -> InboundEmail -> CleanedEmail.

parse_eml maps a raw RFC-5322 message onto the Postmark-compatible
InboundEmail schema. clean_email turns the HTML (or plain text) body into
readable text with selectolax, dropping scripts/styles/hidden elements,
tracking pixels, and easy unsubscribe/footer boilerplate, while keeping
image alt text (promo copy often lives there).
"""
from __future__ import annotations

import email
import email.policy
import email.utils
import re
from datetime import datetime, timezone

from selectolax.lexbor import LexborHTMLParser

from backend.app.schemas import InboundEmail
from backend.extraction.types import CleanedEmail

# Tags whose content is never user-visible text.
_NON_CONTENT_TAGS = ("script", "style", "head", "title", "meta", "link", "noscript", "template")

# Lines that are footer/unsubscribe boilerplate (cheap wins only).
_BOILERPLATE_RE = re.compile(
    r"unsubscribe|view (this email )?in (your )?browser|manage (your )?(email )?preferences"
    r"|email preferences|privacy policy|update your preferences|no longer wish to receive",
    re.IGNORECASE,
)

_HIDDEN_STYLE_RE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden|opacity\s*:\s*0(?:\.0*)?(?:;|$)")


def parse_eml(raw: bytes) -> InboundEmail:
    """Parse a raw .eml file into the Postmark-compatible InboundEmail schema."""
    msg = email.message_from_bytes(raw, policy=email.policy.default)

    from_name, from_addr = email.utils.parseaddr(msg.get("From", ""))
    to_full = [
        {"Email": addr, "Name": name}
        for name, addr in email.utils.getaddresses([msg.get("To", "")])
        if addr
    ]

    text_body: str | None = None
    html_body: str | None = None
    plain_part = msg.get_body(preferencelist=("plain",))
    if plain_part is not None:
        text_body = plain_part.get_content()
    html_part = msg.get_body(preferencelist=("html",))
    if html_part is not None:
        html_body = html_part.get_content()

    message_id = (msg.get("Message-ID") or "").strip().strip("<>")

    return InboundEmail(
        MessageID=message_id,
        FromFull={"Email": from_addr, "Name": from_name},
        ToFull=to_full,
        Subject=msg.get("Subject", "") or "",
        TextBody=text_body,
        HtmlBody=html_body,
        Date=msg.get("Date", "") or "",
        MailboxHash="",
        Attachments=[],
        Headers=[{"Name": name, "Value": str(value)} for name, value in msg.items()],
    )


def clean_email(email_in: InboundEmail) -> CleanedEmail:
    """Produce readable text plus sender/date metadata from an inbound email."""
    if email_in.HtmlBody:
        text = _html_to_text(email_in.HtmlBody)
    else:
        text = email_in.TextBody or ""
    text = _strip_boilerplate(text)
    text = _collapse_whitespace(text)

    sender = str(email_in.FromFull.get("Email") or "").strip().lower()
    sender_domain = sender.rsplit("@", 1)[1] if "@" in sender else ""

    return CleanedEmail(
        subject=email_in.Subject,
        text=text,
        html=email_in.HtmlBody,
        sender=sender,
        sender_domain=sender_domain,
        received_at=_parse_date(email_in.Date),
    )


def _parse_date(date_str: str) -> datetime:
    """Parse an RFC-2822 or ISO-8601 date header; fall back to now (UTC)."""
    if date_str:
        try:
            dt = email.utils.parsedate_to_datetime(date_str)
            if dt is not None:
                return dt
        except (TypeError, ValueError):
            pass
        try:
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _is_hidden(node) -> bool:
    attrs = node.attributes or {}
    if "hidden" in attrs:
        return True
    style = (attrs.get("style") or "").lower()
    return bool(_HIDDEN_STYLE_RE.search(style))


def _is_tracking_pixel(attrs: dict) -> bool:
    width = (attrs.get("width") or "").strip().rstrip("px")
    height = (attrs.get("height") or "").strip().rstrip("px")
    return width in ("0", "1") or height in ("0", "1")


def _html_to_text(html: str) -> str:
    tree = LexborHTMLParser(html)

    for tag in _NON_CONTENT_TAGS:
        for node in tree.css(tag):
            node.decompose()

    # Hidden elements can nest; remove one at a time and re-query so we never
    # touch a node whose ancestor was already freed.
    while True:
        hidden = next((n for n in tree.css("[style], [hidden]") if _is_hidden(n)), None)
        if hidden is None:
            break
        hidden.decompose()

    # Keep alt text of real images (promo text often lives there); drop
    # tracking pixels and alt-less images.
    for img in tree.css("img"):
        attrs = img.attributes or {}
        alt = (attrs.get("alt") or "").strip()
        if alt and not _is_tracking_pixel(attrs):
            img.replace_with(alt)
        else:
            img.decompose()

    root = tree.body or tree.root
    return root.text(separator="\n") if root is not None else ""


def _strip_boilerplate(text: str) -> str:
    kept = [line for line in text.splitlines() if not _BOILERPLATE_RE.search(line)]
    return "\n".join(kept)


def _collapse_whitespace(text: str) -> str:
    lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.splitlines()]
    collapsed = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return re.sub(r"^\n+|\n+$", "", collapsed).strip()
