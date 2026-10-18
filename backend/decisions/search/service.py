"""Free-text reward search: explainable matching, urgency/value ranking.

Pure functions over the user's rewards, the merchant catalog and wallet cards —
no I/O here. Every hit carries the matched term so the UI can show *why*.

Score = value * match * urgency, all in [0, ~2]:
- value: percent_off/100, amount_off/50 (USD), cashback/50, points/500 (capped
  at 1); free_item and bogo get a 0.25 floor so urgency still ranks them.
- match: 1.0 exact merchant name, 0.9 partial name token, 0.85 category word,
  0.75 lexicon MCC group, 0.6 fuzzy (typo) match, semantic encoder similarity
  (optional, capped at 0.9) when nothing lexical hits.
- urgency: 1 + exp(-days_until_expiry / 3); no expiry = 1.0.
"""
from datetime import datetime, timezone
from decimal import Decimal
from difflib import get_close_matches
import math
import re

from backend.app.schemas import (
    Reward, RewardKind, RewardStatus, SearchBestCard, SearchChip, SearchHit,
)
from backend.decisions.common import card_rate, utc
from .lexicon import CHIP_DEFINITIONS, KEYWORD_MCCS

MATCH_MERCHANT = 1.0
MATCH_NAME_TOKEN = 0.9
MATCH_CATEGORY_WORD = 0.85
MATCH_MCC = 0.75
MATCH_FUZZY = 0.6
SEMANTIC_FLOOR = 0.35
SEMANTIC_CAP = 0.9
FUZZY_CUTOFF = 0.8
EXPIRING_SOON_DAYS = 3

# Filler words never carry intent; "stores" alone must not match every store.
STOPWORDS = frozenset({
    'a', 'an', 'and', 'any', 'best', 'coupon', 'coupons', 'deal', 'deals', 'do',
    'for', 'have', 'i', 'in', 'me', 'my', 'near', 'of', 'offer', 'offers', 'on',
    'reward', 'rewards', 'show', 'some', 'store', 'stores', 'the', 'to', 'want',
})


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9&']+", (text or '').casefold())


def _query_terms(query: str) -> tuple[list[str], list[str]]:
    """Meaningful tokens, plus phrase/bigram/token terms for lexicon lookup."""
    tokens = [t for t in tokenize(query) if t not in STOPWORDS]
    terms = []
    if len(tokens) > 2:
        terms.append(' '.join(tokens))
    terms += [' '.join(p) for p in zip(tokens, tokens[1:])] + tokens
    return tokens, terms


def _lexicon_mccs(terms: list[str]) -> dict[str, tuple[str, str]]:
    """mcc -> (matched term, friendly label), first (most specific) term wins."""
    matched: dict[str, tuple[str, str]] = {}
    for term in terms:
        entry = KEYWORD_MCCS.get(term)
        if entry is None and len(term.split()) == 1:
            close = get_close_matches(term, KEYWORD_MCCS.keys(), n=1, cutoff=FUZZY_CUTOFF)
            entry = KEYWORD_MCCS.get(close[0]) if close else None
        if entry:
            label, mccs = entry
            for mcc in mccs:
                matched.setdefault(mcc, (term, label))
    return matched


def eligible(reward: Reward, now: datetime) -> bool:
    return (reward.status == RewardStatus.active
            and (reward.starts_at is None or utc(reward.starts_at) <= now)
            and (reward.expires_at is None or utc(reward.expires_at) > now))


def value_component(reward: Reward) -> float:
    value = reward.value
    if reward.kind == RewardKind.percent_off:
        return float(min(value / Decimal(100), Decimal(1)))
    if reward.kind in (RewardKind.amount_off, RewardKind.cashback) and reward.currency == 'USD':
        return float(min(value / Decimal(50), Decimal(1)))
    if reward.kind == RewardKind.points:
        return float(min(value / Decimal(500), Decimal(1)))
    # free_item / bogo have no native dollar amount; keep them rankable.
    return 0.25


def _match(reward: Reward, merchant, query: str, tokens: list[str],
           mccs: dict[str, tuple[str, str]]) -> tuple[float, str] | None:
    """Best (match_component, reason) for one reward, or None."""
    names = [reward.merchant_name]
    if merchant is not None:
        names.append(merchant.name)
        names += [a for a in merchant.aliases if '.' not in a]
    names = [n for n in names if n]

    text = ' '.join(tokens) or query.casefold()
    for name in names:
        if re.search(r'(?<![\w-])' + re.escape(name.casefold()) + r'(?![\w-])', text):
            return MATCH_MERCHANT, f'Matches your {reward.merchant_name} reward'
    name_tokens = {t for n in names for t in tokenize(n) if len(t) > 2 and t not in STOPWORDS}
    for token in tokens:
        if token in name_tokens:
            return MATCH_NAME_TOKEN, f'"{token}" matches {reward.merchant_name}'

    category_words = {t for t in tokenize(reward.category or '') if t not in STOPWORDS}
    for token in tokens:
        if token in category_words:
            return (MATCH_CATEGORY_WORD,
                    f'{reward.merchant_name} is in {reward.category} — matches "{token}"')

    if reward.mcc in mccs:
        term, label = mccs[reward.mcc]
        return MATCH_MCC, f'{reward.category} fits "{term}" ({label})'

    vocab = name_tokens | category_words
    for token in tokens:
        close = get_close_matches(token, vocab, n=1, cutoff=FUZZY_CUTOFF)
        if close:
            where = reward.merchant_name if close[0] in name_tokens else reward.category
            return MATCH_FUZZY, f'"{token}" is close to "{close[0]}" ({where})'
    return None


def _semantic_match(reward: Reward, merchant, similarity) -> tuple[float, str] | None:
    if similarity is None or similarity < SEMANTIC_FLOOR:
        return None
    score = min(SEMANTIC_CAP, float(similarity))
    return score, f'Semantically similar to {reward.merchant_name}'


def best_card(reward: Reward, cards) -> SearchBestCard | None:
    best, rate = None, Decimal(-1)
    for card in cards:
        candidate = card_rate(card, category=reward.category, mcc=reward.mcc)
        if candidate > rate:
            best, rate = card, candidate
    if best is None:
        return None
    return SearchBestCard(card_id=best.id, name=f'{best.issuer} {best.name}', rate=rate)


def search_rewards(query: str, *, rewards, merchants, cards, now=None, limit=8,
                   similarities: dict | None = None) -> tuple[list[SearchHit], int, int]:
    """Rank the user's eligible rewards against a query.

    `similarities` optionally maps reward.id -> cosine similarity from a
    semantic encoder (e.g. MiniLM via the lookup embeddings adapter); it is
    used only when no lexical rule matched a reward.

    Returns (top hits, total matched before limit, total eligible searched).
    """
    now = utc(now)
    tokens, terms = _query_terms(query)
    mccs = _lexicon_mccs(terms)
    by_id = {m.id: m for m in merchants}

    active = [r for r in rewards if eligible(r, now)]
    hits: list[SearchHit] = []
    for reward in active:
        merchant = by_id.get(reward.merchant_id)
        found = _match(reward, merchant, query, tokens, mccs)
        if found is None and similarities:
            found = _semantic_match(reward, merchant, similarities.get(reward.id))
        if found is None:
            continue
        match, reason = found
        days = ((utc(reward.expires_at) - now).total_seconds() / 86400
                if reward.expires_at else None)
        urgency = 1 + math.exp(-days / 3) if days is not None else 1.0
        value = value_component(reward)
        hits.append(SearchHit(
            reward=reward,
            score=value * match * urgency,
            value_component=value,
            match_component=match,
            urgency_component=urgency,
            days_until_expiry=math.floor(days) if days is not None else None,
            expiring_soon=days is not None and days <= EXPIRING_SOON_DAYS,
            reason=reason,
            best_card=best_card(reward, cards),
        ))
    hits.sort(key=lambda h: (-h.score, -h.match_component,
        utc(h.reward.expires_at) if h.reward.expires_at else datetime.max.replace(tzinfo=timezone.utc),
        str(h.reward.id)))
    return hits[:limit], len(hits), len(active)


def suggest_chips(rewards, now=None) -> list[SearchChip]:
    """Quick-search chips for the category groups actually present in the wallet."""
    now = utc(now)
    active_mccs = [r.mcc for r in rewards if eligible(r, now)]
    chips = []
    for label, query, mccs in CHIP_DEFINITIONS:
        count = sum(1 for mcc in active_mccs if mcc in mccs)
        if count:
            chips.append(SearchChip(label=label, query=query, count=count))
    return chips
