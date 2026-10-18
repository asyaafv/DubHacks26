"""Email parsing and cleaning for extraction pipeline."""
from __future__ import annotations

import email
import email.policy
import re
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import TYPE_CHECKING

from selectolax.lexbor import LexborHTMLParser as HTMLParser

from backend.app.schemas import InboundEmail
from backend.extraction.types import CleanedEmail

if TYPE_CHECKING:
    pass

TRACKING_PIXEL_PATTERN = re.compile(
    r'<img[^>]*(?:width|height)\s*=\s*["\']?1["\']?[^>]*>',
    re.IGNORECASE
)

FOOTER_PATTERNS = [
    re.compile(r'unsubscribe', re.IGNORECASE),
    re.compile(r'manage\s+(?:your\s+)?(?:email\s+)?preferences', re.IGNORECASE),
    re.compile(r'you\s+(?:are\s+)?receiv(?:ed?|ing)\s+this\s+(?:email|message)', re.IGNORECASE),
    re.compile(r'(?:to\s+)?opt[\s-]?out', re.IGNORECASE),
    re.compile(r'privacy\s+policy', re.IGNORECASE),
    re.compile(r'terms\s+(?:of\s+service|and\s+conditions)', re.IGNORECASE),
    re.compile(r'all\s+rights\s+reserved', re.IGNORECASE),
    re.compile(r'©\s*\d{4}', re.IGNORECASE),
    re.compile(r'if\s+you\s+no\s+longer\s+wish', re.IGNORECASE),
]

WHITESPACE_PATTERN = re.compile(r'\s+')
MULTIPLE_NEWLINES = re.compile(r'\n{3,}')


def parse_eml(raw: bytes) -> InboundEmail:
    """Parse raw .eml bytes into InboundEmail model.
    
    Handles multipart, quoted-printable, base64, and various charsets
    using Python's stdlib email package.
    """
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    
    from_header = msg.get("From", "")
    from_name, from_email_addr = _parse_address(from_header)
    
    to_header = msg.get("To", "")
    to_list = []
    if to_header:
        for addr in to_header.split(","):
            name, email_addr = _parse_address(addr.strip())
            to_list.append({"Email": email_addr, "Name": name})
    
    text_body = None
    html_body = None
    
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain" and text_body is None:
                text_body = _get_payload_text(part)
            elif content_type == "text/html" and html_body is None:
                html_body = _get_payload_text(part)
    else:
        content_type = msg.get_content_type()
        payload = _get_payload_text(msg)
        if content_type == "text/html":
            html_body = payload
        else:
            text_body = payload
    
    date_str = msg.get("Date", "")
    message_id = msg.get("Message-ID", "").strip("<>")
    subject = msg.get("Subject", "")
    
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


def _parse_address(addr_str: str) -> tuple[str, str]:
    """Parse 'Name <email>' or just 'email' format."""
    addr_str = addr_str.strip()
    if "<" in addr_str and ">" in addr_str:
        match = re.match(r'"?([^"<]*)"?\s*<([^>]+)>', addr_str)
        if match:
            return match.group(1).strip(), match.group(2).strip()
    return "", addr_str


def _get_payload_text(part: EmailMessage) -> str | None:
    """Extract text from email part, handling encoding."""
    try:
        payload = part.get_content()
        if isinstance(payload, bytes):
            charset = part.get_content_charset() or "utf-8"
            try:
                return payload.decode(charset)
            except (UnicodeDecodeError, LookupError):
                return payload.decode("utf-8", errors="replace")
        return payload if isinstance(payload, str) else None
    except Exception:
        return None


def clean_email(email_obj: InboundEmail) -> CleanedEmail:
    """Convert InboundEmail to CleanedEmail with cleaned text.
    
    - HTML to readable text using selectolax
    - Drops script/style/hidden elements
    - Removes tracking pixels
    - Drops footer boilerplate (unsubscribe, legal, etc.) where easy
    - Collapses whitespace
    - Keeps link text
    - Extracts sender_domain
    - Uses email date for received_at (fallback to now UTC)
    """
    sender_email = email_obj.FromFull.get("Email", "")
    sender_name = email_obj.FromFull.get("Name", "")
    sender = f"{sender_name} <{sender_email}>" if sender_name else sender_email
    sender_domain = _extract_domain(sender_email)
    
    received_at = _parse_email_date(email_obj.Date)
    
    text = ""
    html = email_obj.HtmlBody
    
    if html:
        text = _html_to_text(html)
    elif email_obj.TextBody:
        text = _clean_plain_text(email_obj.TextBody)
    
    return CleanedEmail(
        subject=email_obj.Subject,
        text=text,
        html=html,
        sender=sender,
        sender_domain=sender_domain,
        received_at=received_at,
    )


def _extract_domain(email_addr: str) -> str:
    """Extract domain from email address."""
    if "@" in email_addr:
        return email_addr.split("@")[-1].lower()
    return ""


def _parse_email_date(date_str: str) -> datetime:
    """Parse email date string to datetime, fallback to now UTC."""
    if not date_str:
        return datetime.now(timezone.utc)
    
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(date_str)
    except (ValueError, TypeError):
        pass
    
    return datetime.now(timezone.utc)


def _html_to_text(html: str) -> str:
    """Convert HTML to readable plain text using selectolax."""
    html = TRACKING_PIXEL_PATTERN.sub("", html)
    
    parser = HTMLParser(html)
    
    for tag in parser.css("script, style, noscript, head, meta, link"):
        tag.decompose()
    
    for tag in parser.css("[style*='display:none'], [style*='display: none']"):
        tag.decompose()
    for tag in parser.css("[hidden]"):
        tag.decompose()
    for tag in parser.css("[style*='visibility:hidden'], [style*='visibility: hidden']"):
        tag.decompose()
    
    for tag in parser.css("img[width='1'], img[height='1']"):
        tag.decompose()
    
    lines = []
    body = parser.body
    if body:
        text = body.text(separator="\n", strip=True)
        lines = text.split("\n")
    
    cleaned_lines = []
    in_footer = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        if _is_footer_line(line):
            in_footer = True
        
        if not in_footer:
            cleaned_lines.append(line)
    
    text = "\n".join(cleaned_lines)
    text = WHITESPACE_PATTERN.sub(" ", text.replace("\n", "\n ")).strip()
    text = text.replace("\n ", "\n")
    text = MULTIPLE_NEWLINES.sub("\n\n", text)
    
    return text


def _clean_plain_text(text: str) -> str:
    """Clean plain text email content."""
    lines = text.split("\n")
    cleaned_lines = []
    in_footer = False
    
    for line in lines:
        stripped = line.strip()
        
        if stripped.startswith("---") and len(stripped) <= 5:
            in_footer = True
            continue
        
        if _is_footer_line(stripped):
            in_footer = True
        
        if not in_footer:
            cleaned_lines.append(line.rstrip())
    
    text = "\n".join(cleaned_lines)
    text = MULTIPLE_NEWLINES.sub("\n\n", text)
    return text.strip()


def _is_footer_line(line: str) -> bool:
    """Check if a line looks like footer/legal boilerplate."""
    for pattern in FOOTER_PATTERNS:
        if pattern.search(line):
            return True
    return False
