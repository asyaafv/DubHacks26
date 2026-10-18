"""Shared extraction types. Do not edit without updating every extraction module."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class FieldValue:
    value: str
    confidence: float  # 0.0-1.0
    source: str  # "email_jsonld" | "gliner" | "regex"


@dataclass
class FieldCandidates:
    merchant: Optional[FieldValue] = None
    discount_value: Optional[FieldValue] = None  # raw, e.g. "10% off", "$10 off"
    min_spend: Optional[FieldValue] = None
    max_discount: Optional[FieldValue] = None
    expiry: Optional[FieldValue] = None  # raw date text, e.g. "Sunday", "Oct 31"
    starts: Optional[FieldValue] = None
    code: Optional[FieldValue] = None
    stackable: Optional[FieldValue] = None  # "true" / "false"
    exclusions: list[FieldValue] = field(default_factory=list)


@dataclass
class CleanedEmail:
    subject: str
    text: str
    html: Optional[str]
    sender: str
    sender_domain: str
    received_at: datetime
