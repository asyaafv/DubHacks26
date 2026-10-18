"""POST /search + GET /search/suggestions, in-memory and Postgres modes.

Results always come from the caller's own rewards. The optional semantic layer
(app.state.query_encoder, the MiniLM adapter from decisions.lookup.embeddings)
is best-effort: search degrades to lexical/MCC matching without it.
"""
from fastapi import APIRouter, Header, HTTPException, Request

from backend.app.schemas import SearchRequest, SearchResponse, SearchSuggestions
from backend.decisions.common import DEMO_USER_ID, resolve_user, utc
from backend.decisions.memory import in_memory_mode
from .service import SEMANTIC_FLOOR, search_rewards, suggest_chips

router = APIRouter(tags=['Search'])

# Merchant profile vectors for in-memory semantic search, keyed by
# (encoder model, merchant id). The seed catalog is static per process.
_profile_cache: dict = {}


def _user(x_user_id, body_user_id=None):
    # The stub app defaults identity to the demo user (matches /lookup, /stack).
    if x_user_id is None and body_user_id is None:
        return DEMO_USER_ID
    return resolve_user(x_user_id, body_user_id)


def _memory_data(user_id):
    from backend.app import main
    rewards = [r for r in main.get_rewards() if r.user_id == user_id]
    cards = [c for c in main.get_cards() if c.user_id == user_id]
    return rewards, main.get_merchants(), cards


def _memory_similarities(app, query, rewards, merchants):
    encoder = getattr(app.state, 'query_encoder', None)
    if encoder is None:
        return None
    try:
        query_vector = encoder.encode_query(query)
        vectors = {}
        for merchant in merchants:
            key = (encoder.model_name, merchant.id)
            if key not in _profile_cache:
                _profile_cache[key] = encoder.encode_query(f'{merchant.name} {merchant.category}')
            vectors[merchant.id] = _profile_cache[key]
        # Encoder output is normalized, so the dot product is cosine similarity.
        return {r.id: sum(a * b for a, b in zip(query_vector, vectors[r.merchant_id]))
                for r in rewards if r.merchant_id in vectors}
    except Exception:  # noqa: BLE001 - semantic layer must never break search
        return None


async def _db_similarities(app, repo, query, now):
    encoder = getattr(app.state, 'query_encoder', None)
    if encoder is None:
        return None
    try:
        vector = encoder.encode_query(query)
        scored = await repo.lookup_rewards(embedding=vector, now=now,
                                           min_similarity=SEMANTIC_FLOOR)
        return {reward.id: similarity for reward, similarity in scored}
    except Exception:  # noqa: BLE001
        return None


@router.post('/search', response_model=SearchResponse)
async def search(body: SearchRequest, request: Request,
                 x_user_id: str | None = Header(None, alias='X-User-Id')):
    """Search the user's rewards by merchant, category keyword or MCC group."""
    user_id = _user(x_user_id, body.user_id)
    query = body.query.strip()
    if not query:
        raise HTTPException(400, 'Query must not be empty')
    now = utc()
    app = request.app
    if in_memory_mode(app):
        rewards, merchants, cards = _memory_data(user_id)
        similarities = _memory_similarities(app, query, rewards, merchants)
        hits, matched, active = search_rewards(
            query, rewards=rewards, merchants=merchants, cards=cards,
            now=now, limit=body.limit, similarities=similarities)
    else:
        database = getattr(app.state, 'database', None)
        if database is None:
            raise HTTPException(503, 'Database is not configured')
        async with database.transaction(user_id) as repo:
            rewards = await repo.list_rewards(now=now)
            merchants = await repo.lookup_merchants()
            cards = (await repo.get_wallet(now=now)).cards
            similarities = await _db_similarities(app, repo, query, now)
            hits, matched, active = search_rewards(
                query, rewards=rewards, merchants=merchants, cards=cards,
                now=now, limit=body.limit, similarities=similarities)
            # Codes are encrypted at rest and NULL in list queries; reveal them
            # only for the page actually returned to the owner.
            for hit in hits:
                hit.reward = await repo.get_reward(hit.reward.id, reveal_code=True)
    return SearchResponse(query=query, results=hits, total_matched=matched,
                          total_active=active)


@router.get('/search/suggestions', response_model=SearchSuggestions)
async def suggestions(request: Request,
                      x_user_id: str | None = Header(None, alias='X-User-Id')):
    """Quick-search chips for category groups present in the user's wallet."""
    user_id = _user(x_user_id)
    now = utc()
    app = request.app
    if in_memory_mode(app):
        rewards, _, _ = _memory_data(user_id)
    else:
        database = getattr(app.state, 'database', None)
        if database is None:
            raise HTTPException(503, 'Database is not configured')
        async with database.transaction(user_id) as repo:
            rewards = await repo.list_rewards(now=now)
    return SearchSuggestions(chips=suggest_chips(rewards, now=now))
