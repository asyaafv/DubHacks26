"""Audit harness: run every seed email, every console template, and 5 synthetic
emails through the full ML pipeline (SetFit + GLiNER2 + extruct + dateparser +
price-parser + sentence-transformers), twice (cold then warm), and print a report.

Usage:
    python -m backend.tests.extraction.audit_run

Not a pytest module (name does not start with test_). Read-only against the
pipeline; makes no network calls beyond initial HF model downloads.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.schemas import InboundEmail  # noqa: E402
from backend.extraction import pipeline  # noqa: E402
from backend.intake.console import emails as console_emails  # noqa: E402

USER_ID = "00000000-0000-0000-0000-000000000001"
SEED_DIR = REPO_ROOT / "shared" / "seed" / "emails"

NOW = datetime.now(timezone.utc)


def _mk(subject: str, text: str, sender: str, msg_id: str) -> InboundEmail:
    return InboundEmail(
        MessageID=msg_id,
        FromFull={"Email": sender, "Name": sender.split("@")[1].split(".")[0].title()},
        ToFull=[{"Email": "aamir@lapse.app", "Name": "Aamir"}],
        Subject=subject,
        TextBody=text,
        HtmlBody=None,
        Date=NOW.strftime("%a, %d %b %Y %H:%M:%S %z"),
    )


def _future(days: int) -> str:
    d = NOW + timedelta(days=days)
    return f"{d.strftime('%B')} {d.day}, {d.year}"


SYNTHETIC: list[tuple[str, InboundEmail, str]] = [
    (
        "custom/sephora_points",
        _mk(
            "You've earned 250 bonus points, Beauty Insider!",
            "Hi,\n\nYour Beauty Insider account just got a boost: 250 bonus points\n"
            "have been added for your recent purchases.\n\nReward: 250 bonus points\n"
            f"Valid through: {_future(30)}\n\nPoints apply automatically at checkout when you sign in.\n\nSephora",
            "beautyinsider@sephora.com",
            "audit-sephora-1",
        ),
        "expect: reward, points 250",
    ),
    (
        "custom/starbucks_bogo",
        _mk(
            "Your Reward: Buy One Get One FREE handcrafted drink",
            "Hey,\n\nYou've earned it: buy one handcrafted drink, get one free this weekend.\n\n"
            f"Deal: BOGO handcrafted drinks\nUse code: SIPSHARE\nValid through: {_future(3)}\n\n"
            "Show this email or redeem in the app. One per member.\n\nStarbucks Rewards",
            "rewards@starbucks.com",
            "audit-starbucks-1",
        ),
        "expect: reward, bogo, code SIPSHARE",
    ),
    (
        "custom/oldnavy_10_off_50",
        _mk(
            "$10 off $50 - your reward is here",
            "Hi,\n\nHere's a little thank-you: $10 off when you spend $50 or more.\n\n"
            f"$10 OFF your purchase of $50+\nPromo code: NAVY10\nValid through: {_future(7)}\n"
            "Excludes: clearance and gift cards.\n\nOld Navy",
            "oldnavy@email.oldnavy.com",
            "audit-oldnavy-1",
        ),
        "expect: reward, amount_off 10, min_spend 50, code NAVY10",
    ),
    (
        "custom/newsletter_non_reward",
        _mk(
            "The Weekend Read: 5 fall recipes we love",
            "Hi,\n\nWelcome to this week's newsletter. Inside: five cozy fall recipes,\n"
            "a interview with chef Dana Ruiz, and our favorite kitchen playlists.\n\n"
            "Read the full issue on our site. No purchase necessary - just enjoy.\n\n"
            "Unsubscribe anytime.\n\nThe Tasteful Table newsletter",
            "hello@tastefultable.com",
            "audit-newsletter-1",
        ),
        "expect: other/promo, NO reward",
    ),
    (
        "custom/shipping_notification",
        _mk(
            "Your order has shipped! Tracking inside",
            "Hi,\n\nGood news - your order #84721-A has shipped.\n\n"
            "Tracking number: 1Z999AA10123456784\nCarrier: UPS\nArriving: Thursday\n\n"
            "Order total: $42.17\n\nTrack your package anytime from your account.\n\nREI Co-op",
            "orders@rei.com",
            "audit-shipping-1",
        ),
        "expect: receipt/other, NO reward",
    ),
]


def gather_cases() -> list[tuple[str, InboundEmail, str]]:
    cases: list[tuple[str, InboundEmail, str]] = []
    for eml in sorted(SEED_DIR.glob("*.eml")):
        cases.append((f"seed/{eml.stem}", pipeline.parse_eml(eml.read_bytes()), ""))
    for spec in console_emails.TEMPLATES:
        rendered = console_emails.render_email(spec.id)
        cases.append(
            (
                f"console/{spec.id}",
                pipeline.parse_eml(rendered.eml_bytes),
                f"expect: {spec.kind} v={spec.value} code={spec.code} min={spec.min_spend}",
            )
        )
    cases.extend(SYNTHETIC)
    return cases


def run_once(cases, tag: str) -> list[dict]:
    rows = []
    for name, email, expect in cases:
        res = pipeline.run_pipeline(email, USER_ID)
        row: dict = {
            "case": name,
            "expect": expect,
            "classification": f"{res.classification} ({res.classification_confidence:.2f})",
            "n_rewards": len(res.rewards),
            "timings_ms": res.timings_ms,
            "fallbacks": res.fallbacks_active,
        }
        if res.rewards:
            r = res.rewards[0]
            row.update(
                kind=r.kind.value,
                value=str(r.value),
                code=r.code,
                expires_at=r.expires_at.isoformat() if r.expires_at else None,
                merchant=r.merchant_name,
                merchant_id=str(r.merchant_id) if r.merchant_id else None,
                min_spend=str(r.min_spend) if r.min_spend is not None else None,
                stackable=r.stackable,
                source=r.source.value,
                status=r.status.value,
                overall_confidence=r.overall_confidence,
                field_confidence=r.field_confidence.model_dump(),
            )
        rows.append(row)
        print(f"[{tag}] {name}: {row['classification']} -> {row['n_rewards']} reward(s)"
              f" total={res.timings_ms.get('total_ms')}ms")
    return rows


def main() -> None:
    cases = gather_cases()
    print(f"=== PASS 1 (cold: first run loads SetFit/GLiNER2/MiniLM) — {len(cases)} cases ===")
    cold = run_once(cases, "cold")
    print("\n=== PASS 2 (warm) ===")
    warm = run_once(cases, "warm")
    out = {"cold": cold, "warm": warm}
    out_path = Path("/tmp/audit_extraction_results.json")
    out_path.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nFull results written to {out_path}")

    print("\n=== WARM DETAIL ===")
    for row in warm:
        print(json.dumps(row, indent=2, default=str))


if __name__ == "__main__":
    main()
