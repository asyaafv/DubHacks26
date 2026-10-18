#!/usr/bin/env python3
"""Smoke-test the /inbound webhook without real email.

Builds a Postmark-format inbound JSON payload from a seed .eml file and POSTs
it to a running Lapse API, then prints the InboundResult. Stdlib only — works
anywhere Python 3.11+ is installed, no repo deps needed.

Examples:
    # Local container
    python scripts/postmark_smoke.py --base-url http://localhost:8000

    # Deployed host, specific seed email, route to the demo user via +hash
    python scripts/postmark_smoke.py \
        --base-url https://lapse-api.onrender.com \
        --eml shared/seed/emails/chipotle_plaintext.eml \
        --mailbox-hash demo

    # Exercise /demo/inject instead of the webhook
    python scripts/postmark_smoke.py --base-url http://localhost:8000 --demo-inject
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from email import message_from_bytes
from email.policy import default as default_policy
from email.utils import parseaddr
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EML = REPO_ROOT / "shared" / "seed" / "emails" / "hollister_10_percent.eml"


def eml_to_postmark_json(raw: bytes, mailbox_hash: str = "") -> dict:
    """Convert a raw .eml into the Postmark inbound webhook JSON shape
    (the subset of fields InboundEmail in backend/app/schemas.py uses)."""
    msg = message_from_bytes(raw, policy=default_policy)

    from_name, from_email = parseaddr(str(msg.get("From", "")))
    to_name, to_email = parseaddr(str(msg.get("To", "")))

    text_body: str | None = None
    html_body: str | None = None
    for part in msg.walk():
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        try:
            content = part.get_content()
        except Exception:
            continue
        if ctype == "text/plain" and text_body is None:
            text_body = content
        elif ctype == "text/html" and html_body is None:
            html_body = content

    message_id = str(msg.get("Message-ID", "")).strip().strip("<>")
    if not message_id:
        message_id = f"smoke-{uuid.uuid4()}"

    return {
        "MessageID": message_id,
        "FromFull": {"Email": from_email, "Name": from_name},
        "ToFull": [{"Email": to_email, "Name": to_name, "MailboxHash": mailbox_hash}],
        "Subject": str(msg.get("Subject", "")),
        "TextBody": text_body,
        "HtmlBody": html_body,
        "Date": str(msg.get("Date", "")),
        "MailboxHash": mailbox_hash,
        "Attachments": [],
        "Headers": [
            {"Name": k, "Value": str(v)}
            for k, v in msg.items()
            if k.lower() in ("message-id", "date", "from", "to", "subject")
        ],
    }


def post_json(url: str, payload: dict, user_id: str | None, timeout: float) -> tuple[int, str]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    if user_id:
        req.add_header("X-User-Id", user_id)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="http://localhost:8000",
                        help="API base URL (default: http://localhost:8000)")
    parser.add_argument("--eml", default=str(DEFAULT_EML),
                        help="Seed .eml file (default: hollister_10_percent.eml)")
    parser.add_argument("--mailbox-hash", default="demo",
                        help="MailboxHash for user routing, e.g. 'aamir' or 'demo'")
    parser.add_argument("--user-id", default=None,
                        help="Optional X-User-Id header (UUID)")
    parser.add_argument("--demo-inject", action="store_true",
                        help="POST to /demo/inject (by filename) instead of /inbound")
    parser.add_argument("--timeout", type=float, default=120.0,
                        help="Request timeout in seconds (first GLiNER call is slow)")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    eml_path = Path(args.eml)

    if args.demo_inject:
        url = f"{base}/demo/inject"
        payload: dict = {"eml_filename": eml_path.name}
        print(f"POST {url}  (eml_filename={eml_path.name})")
    else:
        if not eml_path.exists():
            print(f"error: eml file not found: {eml_path}", file=sys.stderr)
            return 2
        url = f"{base}/inbound"
        payload = eml_to_postmark_json(eml_path.read_bytes(), args.mailbox_hash)
        print(f"POST {url}  (MessageID={payload['MessageID']}, "
              f"MailboxHash={payload['MailboxHash']!r})")

    status, body = post_json(url, payload, args.user_id, args.timeout)

    print(f"HTTP {status}")
    try:
        result = json.loads(body)
        print(json.dumps(result, indent=2))
    except json.JSONDecodeError:
        print(body)
        return 1

    if status != 200:
        return 1

    print(
        f"\nInboundResult: classification={result.get('classification')} "
        f"rewards_extracted={result.get('rewards_extracted')} "
        f"needs_review={result.get('needs_review')} "
        f"processing_time_ms={result.get('processing_time_ms')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
