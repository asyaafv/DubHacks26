# Lookup storage dependency for foundation/integration review

This change is isolated from the lookup feature commit so the foundation owner can
review and accept the repository interface independently. No application wiring,
schema migrations, dependency manifests, generated contracts or seeds change.

The lookup feature requires these additive scoped `Repository` methods:

- `lookup_merchants() -> list[Merchant]`: shared catalog for exact entity resolution.
- `count_lookup_rewards(now=None) -> int`: all eligible rewards for this user.
- `lookup_rewards(*, embedding=None, merchant_id=None, now=None,
  min_similarity=0.35) -> list[tuple[Reward, float]]`: exact merchant filtering or
  exhaustive cosine similarity over stored reward/merchant vectors. Returns
  redacted rewards and match components; no result cutoff before utility ranking.

Reward reads always include transaction `user_id` and query-time eligibility
(active; start absent or <= now; expiry absent or > now). MATERIALIZED CTEs keep
owned, eligible rows ahead of vector scoring; relevance is filtered in SQL before
ranking. Exact merchant filtering does not require embeddings. This uses the
existing pgvector schema and foundation vector validation, without new indexes.

`docs/lookup-storage.patch` preserves the recovered repository change separately.
It applies with an offset against the newer foundation base; reverse-checking it
against this worktree verifies that the recovered change is present. Prefer the
storage commit for cherry-picking; apply the patch only as an alternative, not in
addition to that commit. Integrate storage before the lookup feature. If the
foundation owner supplies equivalent methods, reconcile that implementation
rather than applying a second copy.

Embedding backfill remains Person 2/foundation work: seed import leaves vectors
null, and insert-only save methods do not update existing rows. A scoped update
interface or owner-run backfill command is required before a semantic demo. The
lookup README describes compatible text, model/revision and offline caching.
