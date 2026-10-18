"""Savings/redemption models (contract: decisions README "NEW: Savings tracking").

These belong in backend/app/schemas.py followed by scripts/gen_contracts.py so
shared/types.ts and openapi.json pick them up; that file is owned by integration,
so they live here until the one-line move happens.
"""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RedeemRequest(BaseModel):
    """Body for POST /rewards/{id}/redeem; saved falls back to face value."""
    saved: Decimal | None = Field(None, description="Realized savings in USD")


class Redemption(BaseModel):
    """One recorded redemption; money is a 2-decimal string in JSON."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    reward_id: UUID
    merchant_name: str | None = None
    description: str | None = None
    saved: Decimal
    redeemed_at: datetime


class SavingsPoint(BaseModel):
    """Cumulative savings as of one day that had a redemption."""
    date: date
    cumulative: Decimal


class SavingsSummary(BaseModel):
    """GET /savings: total, itemized (newest first), cumulative daily series."""
    total: Decimal
    items: list[Redemption]
    series: list[SavingsPoint]
