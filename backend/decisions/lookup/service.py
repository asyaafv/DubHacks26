"""Lookup orchestration over the foundation's scoped repository."""
import asyncio
import re
from backend.app.schemas import LookupResult
from backend.decisions.common import EMBEDDING_MODEL, utc, vector_literal
from .matching import safe_domain, exact_merchants
from .ranking import rank_rewards

MIN_SIMILARITY = 0.35


class EncoderUnavailable(RuntimeError):
    pass


class LookupService:
    def __init__(self, encoder=None, clock=utc):
        self.encoder, self.clock = encoder, clock

    async def lookup(self, repo, request):
        now = utc(self.clock())
        # Counts all eligible user rewards, independent of relevance/limit/cache coverage.
        total = await repo.count_lookup_rewards(now=now)
        catalog = await repo.lookup_merchants()
        merchant = None
        explicit = request.merchant_id is not None or request.domain is not None
        if explicit:
            domain = safe_domain(request.domain) if request.domain is not None else None
            by_id = next((m for m in catalog if m.id == request.merchant_id), None)
            domain_matches = [m for m in catalog if domain is not None and domain in
                [safe_domain(m.domain), *[safe_domain(a) for a in m.aliases if '.' in a and ' ' not in a]]]
            if len(domain_matches) > 1:
                raise ValueError('Ambiguous merchant domain')
            by_domain = domain_matches[0] if domain_matches else None
            if request.merchant_id and domain is not None and (not by_id or not by_domain or by_id.id != by_domain.id):
                raise ValueError('Merchant ID and domain disagree')
            merchant = by_id if request.merchant_id else by_domain
            if merchant is None:
                return LookupResult(merchant=None, rewards=[], total_available=total)
        query = (request.query or '').strip()
        if query:
            matches = exact_merchants(query, catalog)
            if len(matches) > 1 or (merchant and matches and matches[0].id != merchant.id):
                raise ValueError('Ambiguous or conflicting query merchants')
            if matches:
                merchant = matches[0]
            # A named-merchant question with no exact catalog entity is unknown,
            # not permission to suggest another retailer with a similar category.
            merchant_question = re.fullmatch(
                r'(?:do i have|any|show(?: me)?(?: my)?)\s+(.+?)\s+(?:rewards?|offers?|coupons?)\??',
                query, re.I)
            if not merchant and merchant_question:
                return LookupResult(merchant=None, rewards=[], total_available=total)
            # Unknown domains must not fall through into category recommendations.
            if not merchant and re.search(r'\b[\w-]+\.[a-z]{2,}\b', query, re.I):
                return LookupResult(merchant=None, rewards=[], total_available=total)
        if not merchant and not query:
            raise ValueError('Supply merchant_id, domain or a nonempty query')
        embedding = None
        if not merchant:
            if self.encoder is None or self.encoder.model_name != EMBEDDING_MODEL:
                raise EncoderUnavailable('MiniLM query encoder is not configured')
            try:
                embedding = await asyncio.to_thread(self.encoder.encode_query, query)
                vector_literal(embedding)
            except Exception as exc:
                raise EncoderUnavailable('MiniLM query encoding failed') from exc
        candidates = await repo.lookup_rewards(embedding=embedding,
            merchant_id=merchant.id if merchant else None, now=now, min_similarity=MIN_SIMILARITY)
        return LookupResult(merchant=merchant, rewards=rank_rewards(candidates, now=now, limit=request.limit),
                            total_available=total)
