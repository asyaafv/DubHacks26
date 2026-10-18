You own Person 3's end-to-end verification and demo checks for LAPSE.

Use the existing LOCAL repository. The DUBHACKS parent folder is only a container;
the Git repository is at:
/Users/asuya/Documents/ChatGPT/DUBHACKS/lapse-foundation

Do not clone GitHub or assume main has the completed features: some commits are
local. Create your own isolated worktree and branch before editing. For example:

git -C /Users/asuya/Documents/ChatGPT/DUBHACKS/lapse-foundation worktree add -b codex/person3-e2e /Users/asuya/Documents/ChatGPT/DUBHACKS/lapse-e2e codex/person3-foundation

If that branch or worktree already exists, inspect and reuse it safely instead of
resetting or overwriting it. Perform all subsequent work in your testing worktree.

Read README.md, backend/app/schemas.py, shared/CONTRACTS.md,
docs/person3-contract.md, docs/person3-handoff.md, docs/person3-e2e-scope.md,
docs/lapse-rename-verification.md, and the component handoffs.

The local feature branches are:
- codex/person3-foundation: encrypted storage, wallet, and shared interfaces.
- codex/person3-stacking: OR-Tools stacking and independent exhaustive evaluator.
- codex/person3-lookup: lookup storage additions, semantic search, and ranking.
- codex/person3-delivery: SSE, sync, and expiration job.

Inspect their current tips and assemble the Person 3 changes only in your isolated
testing branch as needed. Keep lookup's separate storage dependency. Preserve all
LAPSE branding/configuration updates; component branches also contain those updates.
Do not modify the owners' working copies or repeat a patch already in history.

A teammate owns integration across Persons 1, 2, and 3 and the production app.
Your scope is Person 3 testing. Mount its actual routers and lifecycle hooks in an
isolated test application; do not take ownership of production main.py wiring,
intake, extraction, merchant classification, deployment, or extension development.

Use real Postgres with pgvector/pgcrypto, real CP-SAT, and cached real MiniLM weights.
Use current LAPSE_* environment names and retain the existing encryption key value.
Keep tests isolated in disposable databases/schemas. Check the environment before
installing dependencies. Report actual skipped/blocked coverage honestly.

Verify:
1. Fresh migrations and repeatable seeds; persistent wallet mutations and restart.
2. Code encryption, user scoping, conflicting identities, and transaction rollback.
3. Complete stacking arithmetic, restrictions, best-card choice, exact explanation,
   and agreement with the independent exhaustive evaluator.
4. Real semantic Nike/shoes/sneakers retrieval and expiration-aware ranking.
5. A new normalized reward committed through the supported persistence boundary
   becoming available via SSE, lookup, and stacking, with the reward absent first.
6. Actual HTTP streaming, reconnect replay, multi-client delivery, and offline sync
   of used/expired rewards and wallet removals.
7. Daily expiration processing, boundary times, overlap, and rerun deduplication.

Inspect the Hollister fixture's item-total and MCC/card-rate inconsistencies.
The target example is $50 off a $500 cart, $450 at checkout, and $22.50 cashback
only when an eligible card actually earns 5%. Use explicit test-only terms when
needed; do not force this result by silently changing shared seed data. Cashback
is not an immediate checkout discount.

Do not claim a normalized reward insert tests email redaction/extraction or the
complete extension. Exercise the full product only after the teammate's integrated
application is available; otherwise mark that part pending and provide boundary
tests and concrete handoff notes.

Own backend/tests/e2e/, the isolated test harness, and test/demo documentation.
Fix defects within that ownership. For component or team integration defects,
provide a minimal failing case and precise handoff rather than rebuilding another
owner's component. Preserve existing tests and do not weaken assertions to pass.

Deliver reproducible setup/test commands, actual results, blockers, and a short
Person 3 demo runbook. Do not push, deploy, or merge remotely without authorization.
