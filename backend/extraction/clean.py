"""Email parsing and cleaning module.

Provides functions to parse raw .eml files and clean HTML email content
into readable text.
"""
from __future__ import annotations

import email
import email.policy
import email.utils
import quopri
import base64
import re
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

from selectolax.parser import HTMLParser

from backend.app.schemas import InboundEmail
from backend.extraction.types import CleanedEmail


def parse_eml(raw: bytes) -> InboundEmail:
    """Parse raw EML bytes into an InboundEmail object.
    
    Handles multipart messages, quoted-printable, base64 encoding, and various charsets.
    """
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    
    from_header = msg.get("From", "")
    from_name, from_email_addr = email.utils.parseaddr(from_header)
    
    to_header = msg.get("To", "")
    to_list = []
    for name, addr in email.utils.getaddresses([to_header]):
        to_list.append({"Email": addr, "Name": name})
    
    subject = msg.get("Subject", "")
    date_str = msg.get("Date", "")
    message_id = msg.get("Message-ID", "").strip("<>")
    
    text_body: str | None = None
    html_body: str | None = None
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain" and text_body is None:
                text_body = _decode_payload(part)
            elif content_type == "text/html" and html_body is None:
                html_body = _decode_payload(part)
    else:
        content_type = msg.get_content_type()
        payload = _decode_payload(msg)
        if content_type == "text/html":
            html_body = payload
        else:
            text_body = payload
    
    headers = []
    for key, value in msg.items():
        headers.append({"Name": key, "Value": value})
    
    return InboundEmail(
        MessageID=message_id,
        FromFull={"Email": from_email_addr, "Name": from_name},
        ToFull=to_list,
        Subject=subject,
        TextBody=text_body,
        HtmlBody=html_body,
        Date=date_str,
        MailboxHash="",
        Attachments=[],
        Headers=headers,
    )


def _decode_payload(part: EmailMessage) -> str:
    """Decode email part payload handling various encodings."""
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace")


def clean_email(email_obj: InboundEmail) -> CleanedEmail:
    """Clean email content, extracting readable text from HTML.
    
    - Removes script/style/hidden elements
    - Removes tracking pixels
    - Strips footer/unsubscribe boilerplate where easy
    - Collapses whitespace
    - Keeps link text
    - Falls back to text part if HTML cleaning fails
    """
    sender = email_obj.FromFull.get("Email", "")
    sender_domain = _extract_domain(sender)
    
    received_at = _parse_date(email_obj.Date)
    
    html = email_obj.HtmlBody
    text = email_obj.TextBody or ""
    
    if html:
        cleaned_text = _clean_html(html)
        if cleaned_text.strip():
            text = cleaned_text
    
    text = _collapse_whitespace(text)
    
    return CleanedEmail(
        subject=email_obj.Subject,
        text=text,
        html=email_obj.HtmlBody,
        sender=sender,
        sender_domain=sender_domain,
        received_at=received_at,
    )


def _extract_domain(email_addr: str) -> str:
    """Extract domain from email address."""
    if "@" in email_addr:
        return email_addr.split("@")[1].lower()
    return ""


def _parse_date(date_str: str) -> datetime:
    """Parse email Date header into datetime."""
    if not date_str:
        return datetime.now(timezone.utc)
    
    try:
        parsed = email.utils.parsedate_to_datetime(date_str)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


def _clean_html(html: str) -> str:
    """Clean HTML content to readable text using selectolax."""
    parser = HTMLParser(html)
    
    _remove_elements_by_tag(parser, ["script", "style", "noscript", "head", "meta", "link"])
    
    _remove_hidden_elements(parser)
    
    _remove_tracking_pixels(parser)
    
    _remove_footer_boilerplate(parser)
    
    text_parts = []
    body = parser.body
    if body is None:
        body = parser.root
    
    if body:
        text_parts = _extract_text_with_links(body)
    
    return "\n".join(text_parts)


def _remove_elements_by_tag(parser: HTMLParser, tags: list[str]) -> None:
    """Remove all elements matching given tags."""
    for tag in tags:
        for node in parser.css(tag):
            node.decompose()


def _remove_hidden_elements(parser: HTMLParser) -> None:
    """Remove elements with display:none or visibility:hidden."""
    hidden_patterns = [
        "[style*='display:none']",
        "[style*='display: none']",
        "[style*='visibility:hidden']",
        "[style*='visibility: hidden']",
        "[hidden]",
        ".hidden",
        "[aria-hidden='true']",
    ]
    for pattern in hidden_patterns:
        try:
            for node in parser.css(pattern):
                node.decompose()
        except Exception:
            pass


def _remove_tracking_pixels(parser: HTMLParser) -> None:
    """Remove 1x1 tracking pixel images."""
    for img in parser.css("img"):
        attrs = img.attributes
        width = attrs.get("width", "")
        height = attrs.get("height", "")
        style = attrs.get("style", "")
        
        is_tiny = False
        if width in ("1", "0", "1px") or height in ("1", "0", "1px"):
            is_tiny = True
        if "width:1px" in style or "width: 1px" in style:
            is_tiny = True
        if "height:1px" in style or "height: 1px" in style:
            is_tiny = True
        
        if is_tiny:
            img.decompose()


def _remove_footer_boilerplate(parser: HTMLParser) -> None:
    """Remove common footer/unsubscribe sections."""
    footer_patterns = [
        "footer",
        "[role='contentinfo']",
    ]
    for pattern in footer_patterns:
        try:
            for node in parser.css(pattern):
                text_content = node.text(deep=True).lower()
                if "unsubscribe" in text_content or "opt out" in text_content:
                    node.decompose()
        except Exception:
            pass
    
    unsubscribe_keywords = ["unsubscribe", "opt-out", "opt out", "email preferences", "manage preferences"]
    for a in parser.css("a"):
        href = a.attributes.get("href", "").lower()
        text = a.text(deep=True).lower()
        for keyword in unsubscribe_keywords:
            if keyword in href or keyword in text:
                parent = a.parent
                if parent and parent.tag in ("p", "div", "span", "td"):
                    parent_text = parent.text(deep=True).strip()
                    if len(parent_text) < 200:
                        parent.decompose()
                        break
                else:
                    a.decompose()
                break


def _extract_text_with_links(node) -> list[str]:
    """Extract text content preserving link text and basic structure."""
    result = []
    
    for child in node.iter():
        if child.tag in ("script", "style", "head", "meta", "link", "noscript"):
            continue
        
        text = child.text(separator=" ", strip=True) if hasattr(child, "text") else ""
        if text:
            text = _normalize_text(text)
            if text:
                result.append(text)
    
    seen = set()
    deduped = []
    for line in result:
        if line not in seen:
            seen.add(line)
            deduped.append(line)
    
    return deduped[:1] if deduped else []


def _normalize_text(text: str) -> str:
    """Normalize text by collapsing whitespace."""
    text = re.sub(r"[\r\n]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _collapse_whitespace(text: str) -> str:
    """Collapse multiple whitespace/newlines into single spaces or newlines."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.split("\n")]
    return "\n".join(lines).strip()
