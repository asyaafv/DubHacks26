"""Marketing-email templates for the demo merchant console (Agent D).

Each template renders a realistic RFC-822 .eml (multipart text+HTML with
schema.org DiscountOffer JSON-LD for some merchants, plain text for others)
that `backend.extraction.pipeline.parse_eml` accepts and the extraction
pipeline turns into the expected reward.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid
from typing import Any

DEFAULT_RECIPIENT = "aamir@lapse.app"


@dataclass(frozen=True)
class TemplateSpec:
    """Static definition of one store template shown in the console."""

    id: str
    merchant: str
    domain: str
    from_name: str
    from_email: str
    kind: str  # percent_off | amount_off | points | free_item | bogo
    summary: str
    brand: str  # accent color for the console UI
    value: float | None = None
    code: str | None = None
    expiry_days: int | None = None
    min_spend: float | None = None
    item: str | None = None
    jsonld: bool = False


TEMPLATES: list[TemplateSpec] = [
    TemplateSpec(
        id="hollister_10",
        merchant="Hollister Co.",
        domain="hollisterco.com",
        from_name="Hollister Co.",
        from_email="rewards@hollisterco.com",
        kind="percent_off",
        summary="10% off voucher (JSON-LD)",
        brand="#1f3a5f",
        value=10,
        code="HCOFALL10",
        expiry_days=3,
        min_spend=50,
        jsonld=True,
    ),
    TemplateSpec(
        id="tacobell_crunchwrap",
        merchant="Taco Bell",
        domain="tacobell.com",
        from_name="Taco Bell Rewards",
        from_email="rewards@tacobell.com",
        kind="free_item",
        summary="Free Crunchwrap Supreme (plain text)",
        brand="#702082",
        code="CRUNCHTIME",
        expiry_days=7,
        item="Crunchwrap Supreme",
    ),
    TemplateSpec(
        id="ulta_points",
        merchant="Ulta Beauty",
        domain="ulta.com",
        from_name="Ulta Beauty",
        from_email="rewards@ulta.com",
        kind="points",
        summary="500 bonus points (plain text)",
        brand="#e0501f",
        value=500,
        expiry_days=14,
    ),
    TemplateSpec(
        id="pacsun_bogo",
        merchant="PacSun",
        domain="pacsun.com",
        from_name="PacSun",
        from_email="offers@pacsun.com",
        kind="bogo",
        summary="BOGO jeans (plain text)",
        brand="#0b0b0b",
        code="PACBOGO",
        expiry_days=5,
        item="jeans",
    ),
    TemplateSpec(
        id="aero_50",
        merchant="Aéropostale",
        domain="aeropostale.com",
        from_name="Aéropostale",
        from_email="deals@aeropostale.com",
        kind="percent_off",
        summary="50% off select items (JSON-LD)",
        brand="#003da5",
        value=50,
        code="AERO50",
        expiry_days=4,
        jsonld=True,
    ),
    TemplateSpec(
        id="target_5off",
        merchant="Target",
        domain="target.com",
        from_name="Target Circle",
        from_email="offers@target.com",
        kind="amount_off",
        summary="$5 off reward (JSON-LD)",
        brand="#cc0000",
        value=5,
        code="CIRCLE5",
        expiry_days=10,
        min_spend=25,
        jsonld=True,
    ),
]

TEMPLATES_BY_ID: dict[str, TemplateSpec] = {t.id: t for t in TEMPLATES}


@dataclass
class RenderedEmail:
    """A fully rendered marketing email ready to send or inject."""

    template_id: str
    merchant: str
    subject: str
    text: str
    html: str | None
    to: str
    from_name: str
    from_email: str
    message_id: str
    eml_bytes: bytes = field(repr=False, default=b"")
    expires_at: datetime | None = None


def _fmt_num(value: float) -> str:
    """Format 10.0 -> '10', 7.5 -> '7.5'."""
    return f"{value:g}"


def _resolve(spec: TemplateSpec, overrides: dict[str, Any]) -> dict[str, Any]:
    """Apply presenter overrides (discount, code, expiry, min spend) to a spec."""
    value = overrides.get("value", spec.value)
    expiry_days = overrides.get("expiry_days", spec.expiry_days)
    now = datetime.now(timezone.utc)
    expires_at = None
    if expiry_days is not None:
        expires_at = (now + timedelta(days=int(expiry_days))).replace(
            hour=23, minute=59, second=59, microsecond=0
        )
    return {
        "value": float(value) if value is not None else None,
        "code": (overrides.get("code") or spec.code) or None,
        "min_spend": overrides.get("min_spend", spec.min_spend),
        "item": overrides.get("item", spec.item),
        "expires_at": expires_at,
        "now": now,
    }


def _expiry_str(expires_at: datetime | None) -> str:
    if expires_at is None:
        return ""
    day = expires_at.strftime("%d").lstrip("0")
    return f"{expires_at.strftime('%B')} {day}, {expires_at.strftime('%Y')}"


def _jsonld_discount_offer(
    spec: TemplateSpec, offer: dict[str, Any], name: str, description: str
) -> dict[str, Any]:
    """Build a schema.org DiscountOffer node the markup extractor understands."""
    node: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": "DiscountOffer",
        "name": name,
        "description": description,
        "validFrom": offer["now"].isoformat(),
        "seller": {
            "@type": "Organization",
            "name": spec.merchant,
            "url": f"https://www.{spec.domain}",
        },
    }
    if offer["code"]:
        node["discountCode"] = offer["code"]
    if spec.kind == "percent_off":
        node["discount"] = _fmt_num(offer["value"])
        node["discountType"] = "Percent"
    elif spec.kind == "amount_off":
        node["discount"] = _fmt_num(offer["value"])
        node["discountType"] = "Amount"
        node["discountCurrency"] = "USD"
    if offer["expires_at"] is not None:
        node["validThrough"] = offer["expires_at"].isoformat()
    if offer["min_spend"]:
        node["eligibleTransactionVolume"] = {
            "@type": "PriceSpecification",
            "minPrice": f"{float(offer['min_spend']):.2f}",
            "priceCurrency": "USD",
        }
    return node


def _marketing_html(
    spec: TemplateSpec,
    offer: dict[str, Any],
    headline: str,
    body_lines: list[str],
    fine_print: str,
    jsonld: dict[str, Any] | None,
) -> str:
    """Realistic single-column marketing email HTML with optional JSON-LD."""
    script = ""
    if jsonld is not None:
        script = (
            '<script type="application/ld+json">\n'
            + json.dumps(jsonld, indent=2, ensure_ascii=False)
            + "\n</script>"
        )
    code_block = ""
    if offer["code"]:
        code_block = (
            f'<p style="font-size:22px;font-weight:bold;letter-spacing:2px;'
            f'margin:8px 0;">Use code: {offer["code"]}</p>'
        )
    detail_rows = ""
    if offer["min_spend"]:
        detail_rows += f"<p style=\"margin:4px 0;\">Minimum purchase: ${_fmt_num(float(offer['min_spend']))}</p>"
    if offer["expires_at"] is not None:
        detail_rows += f'<p style="margin:4px 0;">Valid through: {_expiry_str(offer["expires_at"])}</p>'
    paragraphs = "".join(f'<p style="margin:10px 0;">{line}</p>' for line in body_lines)
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
{script}
</head>
<body style="margin:0;background:#f4f4f4;">
<div style="max-width:600px;margin:0 auto;background:#ffffff;font-family:Arial,Helvetica,sans-serif;color:#1a1a1a;">
  <div style="background:{spec.brand};color:#ffffff;padding:18px 24px;font-size:20px;font-weight:bold;letter-spacing:1px;">{spec.merchant}</div>
  <div style="padding:24px;">
    <h1 style="font-size:26px;margin:0 0 12px;color:{spec.brand};">{headline}</h1>
    {paragraphs}
    <div style="background:#f7f7f7;border:1px dashed {spec.brand};padding:18px;text-align:center;margin:18px 0;">
      {code_block}
      {detail_rows}
    </div>
    <a href="https://www.{spec.domain}" style="display:inline-block;background:{spec.brand};color:#ffffff;padding:12px 22px;text-decoration:none;font-weight:bold;">Redeem Your Reward</a>
    <p style="font-size:11px;color:#888888;margin-top:22px;">{fine_print}</p>
  </div>
</div>
</body>
</html>"""


def _render_hollister(spec: TemplateSpec, offer: dict[str, Any]) -> tuple[str, str, str | None]:
    val = _fmt_num(offer["value"])
    expiry = _expiry_str(offer["expires_at"])
    subject = f"Your {val}% Off Voucher - Just for You"
    text = f"""Hi there,

Thanks for being a loyal Hollister customer. Here's a special reward, just for you:

{val}% OFF YOUR NEXT PURCHASE
Use code: {offer['code']}
Minimum purchase: ${_fmt_num(float(offer['min_spend']))}
Valid through: {expiry}

Excludes: gift cards and clearance items.

See you soon,
The Hollister Crew
"""
    jsonld = _jsonld_discount_offer(
        spec, offer, f"{val}% Off Voucher", f"{val}% off your next purchase at Hollister"
    )
    html = _marketing_html(
        spec,
        offer,
        f"Your {val}% Off Voucher",
        [
            "Hi there,",
            "Thanks for being a loyal Hollister customer. Here's a special reward, just for you:",
            f"<strong>{val}% OFF YOUR NEXT PURCHASE</strong>",
        ],
        "Excludes gift cards and clearance items. One voucher per customer.",
        jsonld,
    )
    return subject, text, html


def _render_tacobell(spec: TemplateSpec, offer: dict[str, Any]) -> tuple[str, str, str | None]:
    item = offer["item"] or "Crunchwrap Supreme"
    expiry = _expiry_str(offer["expires_at"])
    subject = f"You've Earned a FREE {item}"
    text = f"""Hey there, Fire Tier member!

Great news - you've earned your reward: a FREE {item}.

Reward: FREE {item}
Code: {offer['code']}
Valid through: {expiry}

Add the code at checkout in the Taco Bell app or show this email in-store.

Live Mas,
Taco Bell Rewards
"""
    return subject, text, None


def _render_ulta(spec: TemplateSpec, offer: dict[str, Any]) -> tuple[str, str, str | None]:
    val = _fmt_num(offer["value"])
    expiry = _expiry_str(offer["expires_at"])
    subject = f"You've Earned {val} Bonus Points"
    text = f"""Hi Beauty Lover,

You've earned {val} bonus points - your Ultamate Rewards balance just got a boost.

Reward: {val} bonus points
Valid through: {expiry}

Points are applied automatically at checkout when you sign in to your
Ultamate Rewards account.

XO,
Ulta Beauty
"""
    return subject, text, None


def _render_pacsun(spec: TemplateSpec, offer: dict[str, Any]) -> tuple[str, str, str | None]:
    item = offer["item"] or "jeans"
    expiry = _expiry_str(offer["expires_at"])
    subject = f"Your Member Reward: BOGO {item.title()}"
    text = f"""What's up,

Your member reward is here: BOGO {item}. Buy one pair, get a second pair on us.

Deal: BOGO - all denim
Use code: {offer['code']}
Valid through: {expiry}

Online and in-store. Second pair must be of equal or lesser value.

PacSun Crew
"""
    return subject, text, None


def _render_aero(spec: TemplateSpec, offer: dict[str, Any]) -> tuple[str, str, str | None]:
    val = _fmt_num(offer["value"])
    expiry = _expiry_str(offer["expires_at"])
    subject = f"{val}% Off Select Styles - Your Exclusive Reward"
    text = f"""Hey,

Your exclusive reward is live: {val}% off select styles, just for you.

{val}% OFF SELECT STYLES
Use code: {offer['code']}
Valid through: {expiry}

Select styles only. Exclusions apply.

Aero Team
"""
    jsonld = _jsonld_discount_offer(
        spec, offer, f"{val}% Off Select Styles", f"{val}% off select styles at Aéropostale"
    )
    html = _marketing_html(
        spec,
        offer,
        f"{val}% Off Select Styles",
        [
            "Hey,",
            f"Your exclusive reward is live: {val}% off select styles, just for you.",
        ],
        "Select styles only. Exclusions apply. Not valid on prior purchases.",
        jsonld,
    )
    return subject, text, html


def _render_target(spec: TemplateSpec, offer: dict[str, Any]) -> tuple[str, str, str | None]:
    val = _fmt_num(offer["value"])
    min_spend = _fmt_num(float(offer["min_spend"])) if offer["min_spend"] else None
    expiry = _expiry_str(offer["expires_at"])
    subject = f"Here's Your ${val} Target Circle Reward"
    spend_line = f" when you spend ${min_spend} or more" if min_spend else ""
    text = f"""Hi,

A little something from Target Circle - here's your ${val} reward.

${val} off{spend_line}
Promo code: {offer['code']}
Valid through: {expiry}

Apply the code in cart or scan your Circle barcode at checkout.

Target Circle
"""
    jsonld = _jsonld_discount_offer(
        spec, offer, f"${val} Off Reward", f"${val} off at Target with Target Circle"
    )
    html = _marketing_html(
        spec,
        offer,
        f"Here's your ${val} reward",
        [
            "Hi,",
            f"A little something from Target Circle - here's your ${val} reward{spend_line}.",
        ],
        "One reward per guest. Some restrictions apply.",
        jsonld,
    )
    return subject, text, html


_RENDERERS = {
    "hollister_10": _render_hollister,
    "tacobell_crunchwrap": _render_tacobell,
    "ulta_points": _render_ulta,
    "pacsun_bogo": _render_pacsun,
    "aero_50": _render_aero,
    "target_5off": _render_target,
}


def render_email(
    template_id: str,
    overrides: dict[str, Any] | None = None,
    recipient: str = DEFAULT_RECIPIENT,
) -> RenderedEmail:
    """Render a template (with presenter overrides) into a RenderedEmail."""
    spec = TEMPLATES_BY_ID.get(template_id)
    if spec is None:
        raise KeyError(f"Unknown template: {template_id}")
    offer = _resolve(spec, overrides or {})
    subject, text, html = _RENDERERS[template_id](spec, offer)

    msg = EmailMessage()
    msg["From"] = f'"{spec.from_name}" <{spec.from_email}>'
    msg["To"] = recipient
    msg["Subject"] = subject
    msg["Date"] = format_datetime(offer["now"])
    message_id = make_msgid(domain=spec.domain)
    msg["Message-ID"] = message_id
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")

    return RenderedEmail(
        template_id=template_id,
        merchant=spec.merchant,
        subject=subject,
        text=text,
        html=html,
        to=recipient,
        from_name=spec.from_name,
        from_email=spec.from_email,
        message_id=message_id.strip("<>"),
        eml_bytes=msg.as_bytes(),
        expires_at=offer["expires_at"],
    )


def render_eml(
    template_id: str,
    overrides: dict[str, Any] | None = None,
    recipient: str = DEFAULT_RECIPIENT,
) -> bytes:
    """Convenience: render a template straight to RFC-822 .eml bytes."""
    return render_email(template_id, overrides, recipient).eml_bytes


def template_payload() -> list[dict[str, Any]]:
    """Template metadata for GET /templates (JSON-safe)."""
    out = []
    for t in TEMPLATES:
        out.append(
            {
                "id": t.id,
                "merchant": t.merchant,
                "summary": t.summary,
                "kind": t.kind,
                "jsonld": t.jsonld,
                "brand": t.brand,
                "from_email": t.from_email,
                "defaults": {
                    "value": t.value,
                    "code": t.code,
                    "expiry_days": t.expiry_days,
                    "min_spend": t.min_spend,
                    "item": t.item,
                },
            }
        )
    return out
