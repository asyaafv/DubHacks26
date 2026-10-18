# Reward lookup handoff

Worktree: `/Users/asuya/Documents/ChatGPT/DUBHACKS/perk-lookup`.
Branch: `codex/person3-lookup`. All final verification and commits run here;
the shared `perk-foundation` checkout is not used or modified.

## Commit dependency and integration order

The lookup feature commit **depends on storage commit `535dc80`** (or an accepted
equivalent implementation of its three repository methods). Storage changes are
separate for foundation/integration review, not bundled into the feature commit.
See [storage coordination notes](../../../docs/lookup-storage.md) and the preserved
[storage patch](../../../docs/lookup-storage.patch). Cherry-pick the storage commit
first, then the lookup feature commit; the patch is an alternative to the storage
commit and must not be applied a second time. Foundation acceptance is still an
integration dependency, not something this branch assumes has happened.

Integration must then replace the existing stub route, install the optional ML
dependency through its manifest owner, initialize the shared/adapted query encoder
at startup, and arrange Person 2/foundation embedding backfill before the demo.

Exports `router` from `backend.decisions.lookup.router` (also package root).
Integration owns removing the stub `/lookup` handler in `backend/app/main.py` and
including this router; simply adding it after the stub leaves the stub reachable.
Public Pydantic models and generated contracts are unchanged.

`LookupService(encoder, clock)` is independently callable with a foundation scoped
repository. `clock` returns an aware UTC datetime; one instant controls SQL counts,
eligibility and ranking. The router uses `app.state.lookup_clock` if supplied.
`resolve_user` enforces header/body agreement. Codes remain redacted like foundation
searches. Missing semantic encoder yields 503, never a lexical/vector substitute.
Exact merchant lookups require no ML encoder and work before backfill.

## Retrieval and matching

The small dataset uses exhaustive SQL cosine distance (`<=>`) over stored
`rewards.embedding` and `merchants.embedding`. A MATERIALIZED eligible CTE applies
user_id, active status, starts_at <= now and expires_at > now **before** scoring.
The cosine match is max(reward similarity, merchant similarity), ignoring missing
vectors. A reward with neither vector cannot enter semantic results. Similarity
must be >= 0.35 **before** utility ranking; no arbitrary nearest-100 truncation
can hide a valuable/urgent relevant reward. No approximate index is added; the CTE
scan deliberately avoids reliance on the historical IVFFlat indexes.

Exact ID, normalized domain, catalog name or alias in a query is a hard merchant
constraint (match=1). Name boundaries prevent Nike matching Nikeshoes or
nike.com.evil. Multiple/conflicting merchants return 400. Explicit unknown IDs,
domains and named questions such as `Do I have UnknownBrand rewards?` return empty
results. General free text (`shoes`, `sneakers`) uses MiniLM, not keyword matching.
Semantic category results retain their actual retailer; similarity does not imply
cross-retailer redemption. URL hosts use IDNA, lowercase, www/trailing-dot removal;
userinfo, unsupported schemes, invalid host labels and unexpected ports are rejected.
No suffix/substring domain matching or merchant classification occurs.

0.35 is a fixed conservative demo relevance threshold, not a calibrated probability.
It is verified by the semantic tests for this curated catalog; broader catalogs
need labeled relevance evaluation. Natural language entity detection is limited to
exact catalog aliases and the documented named-question forms. Add known merchant
aliases through Person 2 rather than inventing a second classifier.

`total_available` means **all eligible rewards owned by the user**, independent of
query relevance, vector coverage and returned limit, matching the public model's
"Total rewards available for user" description. It is not the match count. Default
limit is 3, allowed range 1..10. No lookup recommender includes future, used,
expired, or needs_review records. Expiry equal to now is expired; start equal to
now is eligible. Offers still carry min_spend, caps and exclusions for later cart
validation; lookup has no cart and does not promise checkout applicability.

## Ranking policy

`score = value_component * match_component * (1 + exp(-days_left / 3))`

`days_left` uses fractional UTC days, not truncated days. No expiry gives urgency
1. The public integer `days_until_expiry` is the floor for display only.
`value_component` is a dimensionless native-unit utility heuristic, clipped to 1:

- percent_off: percentage points / 100 (20% -> 0.2).
- amount_off in USD: native USD face value / 50 ($20 -> 0.4).
- points, free_item, bogo: 0 (no redemption value is known).
- cashback: 0 (the schema does not specify whether its native value is a rate or
  fixed amount); non-USD amount_off: 0 (no FX assumptions).

Zero-utility relevant offers remain discoverable; they follow quantified offers.
These scales are a product ranking convention, **not comparable dollar savings**.
There is no reference-cart estimate. Original Reward.kind, value, currency and
terms are preserved. Never render `score` or a percent_off value as dollar savings.
Match is 1 for exact merchant; otherwise the accepted cosine similarity in [0,1].
Tie order: score descending, match descending, expiry ascending (null last), UUID
ascending. For example $15 expiring in one hour outranks $20 expiring in 30 days,
but a $50 offer with no expiry outranks both. Changing scales requires product
agreement; the inconsistent `/50` percentage conversion and invented $5 defaults
in the old prose/stub do not apply to this implementation.

## Model acquisition, cache and offline demo

Required optional package for the dependency owner: `sentence-transformers>=3,<4`
(tested with 3.4.1). Foundation already provides asyncpg; no pgvector Python codec
is needed because parameters use validated vector literals. No manifest changed.
Model: [sentence-transformers/all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2),
384 dimensions, cosine, pinned revision in `embeddings.MODEL_REVISION`.
See [SentenceTransformer constructor documentation](https://www.sbert.net/docs/package_reference/sentence_transformer/model.html)
for cache/local-files-only options. Weights are loaded on CPU once, never in a
request dependency or module import. Encoding runs in a worker thread with a lock.

With network available, before the demo:

```sh
python -m pip install 'sentence-transformers>=3,<4'
export PERK_MODEL_CACHE=/absolute/path/to/persistent/perk-model-cache
python -c 'import os; from backend.decisions.lookup.embeddings import MiniLMQueryEncoder; MiniLMQueryEncoder(cache_folder=os.environ["PERK_MODEL_CACHE"], offline=False)'
```

Keep that entire cache directory available on the demo machine. During application
lifespan, integration should initialize (or adapt the already-loaded P2 encoder):

```python
app.state.query_encoder = await asyncio.to_thread(
    MiniLMQueryEncoder, cache_folder=os.environ['PERK_MODEL_CACHE'], offline=True)
```

Set `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` for the demo. Offline cache misses fail
at initialization; no downloading/model construction occurs in a lookup request.
Do not commit weights. One instance per worker consumes separate memory.

## Person 2 / foundation dependencies

No extraction code exists in this checkout beyond its README, so the query adapter
implements `QueryEncoder`: `model_name` must be the agreed full model ID and
`encode_query(text) -> list[float]` must return finite, nonzero 384D vectors from
that model. Reuse Person 2's loaded instance through an adapter when available;
`MiniLMQueryEncoder` is a query-only implementation, not an extraction pipeline.
Coordinate the same revision and pooling/normalization. Never mix models in one
column; the current schema has no embedding provenance field.

The foundation Repository has three additive public methods in this branch:
`lookup_merchants`, `count_lookup_rewards`, `lookup_rewards`. They keep SQL and raw
connections inside storage; feature services use only the scoped repository.
No migrations, seeds, manifests or application wiring changed.

Seed import currently supplies **no embeddings**. Person 2/foundation must backfill
existing merchant/reward rows before semantic demo, including after seed import:
encode catalog text `merchant.name + ' ' + merchant.category`, and normalized
reward merchant/category text (plus verified positive product scope if available).
Never embed codes, exclusions as affirmative products, PII or encrypted fields.
Write `vector(384)` via validated `vector_literal`; merchant updates use exact
catalog IDs, reward updates require BOTH user_id and reward ID. The current
insert-only save methods will NOT update existing embeddings: foundation must
supply explicit scoped embedding-update methods or an owner-run backfill command.
No schema migration is needed. Null reward vectors can use a populated merchant
vector, but null/null pairs are deliberately omitted. This branch does not claim
seed embeddings have been persisted or deploy an extraction/backfill pipeline.

## Tests

```sh
python -m pytest backend/tests/test_lookup_ranking.py -q
# Real PostgreSQL with vector/pgcrypto/uuid-ossp; disposable test DB only:
export TEST_DATABASE_URL=postgresql://.../perk_test
export RUN_SEMANTIC_TESTS=1
export PERK_MODEL_CACHE=/absolute/path/to/persistent/perk-model-cache
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -m pytest backend/tests/test_lookup_semantic.py -v
```

Fast tests do not verify semantic search. Semantic tests use actual MiniLM vectors,
actual pgvector operators and isolated schemas (created and dropped per test).
Missing TEST_DATABASE_URL or RUN_SEMANTIC_TESTS explicitly skips them; once enabled,
missing models/DB/extension errors fail rather than silently using mocks.

Validation performed for this implementation: **28 passed**, comprising 14 fast
lookup component tests, 3 real MiniLM/pgvector integration tests and 11 foundation
storage regressions. Ran with both offline flags enabled after downloading the
pinned model, sentence-transformers 3.4.1, Python 3.10.11 and local PostgreSQL 17.11
with pgvector; one unrelated Starlette/AnyIO deprecation warning. The semantic
checks include the complete shared seed catalog and a 106-candidate retrieval
case. The existing application contract suite was not used to claim router
integration: main.py registration remains owned by integration.


Final verification after worktree recovery: **30 passed**, consisting of 14 lookup
component tests, 3 actual MiniLM/pgvector semantic integration tests, and 13 current
foundation storage tests. Ran entirely from `perk-lookup` with its own `.venv`,
the cached pinned MiniLM revision, both offline flags set, and a disposable local
PostgreSQL database. One Starlette/AnyIO deprecation warning remains. The earlier
28-test result above records the previous foundation base; this relocated run is
the final result. Application registration/contract tests remain integration work.
