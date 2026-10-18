"""Shared identity, UTC, domain, money and card-rate semantics."""
from datetime import datetime, timezone
from decimal import Decimal
import math
import os
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import HTTPException

DEMO_USER_ID = UUID('00000000-0000-0000-0000-000000000001')
EMBEDDING_MODEL = 'sentence-transformers/all-MiniLM-L6-v2'
EMBEDDING_DIMENSION = 384


def utc(value=None):
    value = value or datetime.now(timezone.utc)
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def resolve_user(header=None, body_user_id=None):
    try:
        head = UUID(str(header)) if header is not None else None
        body = UUID(str(body_user_id)) if body_user_id is not None else None
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(400, 'Invalid user ID') from None
    if head and body and head != body:
        raise HTTPException(400, 'Conflicting body and header user IDs')
    if head or body:
        return head or body
    if os.getenv('LAPSE_ALLOW_DEMO_IDENTITY', '').lower() == 'true':
        return DEMO_USER_ID
    raise HTTPException(401, 'User identity required')


def canonical_domain(value):
    parsed = urlsplit(value if '://' in value else '//' + value)
    host = (parsed.hostname or '').lower().rstrip('.')
    if host.startswith('www.'):
        host = host[4:]
    if not host or ' ' in host:
        raise ValueError('Invalid merchant domain')
    return host.encode('idna').decode('ascii')


def vector_literal(values):
    if len(values) != EMBEDDING_DIMENSION or not all(math.isfinite(v) for v in values) or not any(values):
        raise ValueError('Embedding must be a finite, nonzero 384-dimensional MiniLM vector')
    return '[' + ','.join(str(float(v)) for v in values) + ']'


def exact_number(value, places, *, maximum=None):
    value = Decimal(str(value))
    if not value.is_finite() or value < 0 or value != value.quantize(Decimal(1).scaleb(-places)):
        raise ValueError('Invalid numeric precision or negative value')
    if maximum is not None and value > maximum:
        raise ValueError('Rate exceeds 100 percent')
    return value


def card_rate(card, category=None, mcc=None):
    """MCC lists constrain applicability; rates do not add together."""
    rates = [card.base_rate]
    for bonus in card.category_rates:
        if bonus.mcc_codes:
            matches = mcc is not None and mcc in bonus.mcc_codes
        else:
            matches = bool(category and bonus.category and category.strip().casefold() == bonus.category.strip().casefold())
        if matches:
            rates.append(bonus.rate)
    return max(rates)
