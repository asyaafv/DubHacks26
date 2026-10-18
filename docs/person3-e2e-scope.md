# LAPSE: Person 3 E2E scope

The next testing chat owns verification of Person 3: wallet and encrypted storage,
stacking, semantic lookup, durable SSE, offline sync, and expiration jobs.
A teammate owns integration across Persons 1, 2, and 3 and the production app.

## Start safely

- Use a separate worktree and branch, based on `codex/person3-foundation`.
- Read `docs/person3-contract.md`, `docs/person3-handoff.md`, and feature handoffs.
- Inspect the actual branch tips; do not assume one feature branch contains all
  the other features. Assemble Person 3 commits in the isolated testing branch
  only as needed to exercise them together. Keep lookup's storage dependency.
- Use the current `LAPSE_*` configuration names. Preserve the existing encryption
  key value when changing configuration names; do not rotate it during testing.
- Follow the current absolute worktree paths, not paths in older chat messages.

## In scope

Build an isolated test application that mounts the real Person 3 routers and
lifecycle hooks, using real PostgreSQL with pgvector/pgcrypto, real OR-Tools, and
cached MiniLM weights for semantic tests. This test application can be assembled
inside the test harness without changing production application wiring.

Verify wallet mutations and restart persistence; reward encryption and user
scoping; solver arithmetic and independent enumeration; semantic relevance and
expiration ranking; committed reward writes becoming visible through SSE and
lookup/stack; reconnect/offline sync; rollback; and rerunnable expiration jobs.
Distinguish component tests, combined Person 3 boundary tests, and full product E2E.

The reward persistence interface is the input boundary when intake/extraction is
unavailable. Do not claim that a normalized reward insert proves email delivery,
redaction, extraction, or the complete extension experience.

For the Hollister demo, inspect the seed fixture and card rates rather than forcing
the documented result. The target example is $50 off a $500 cart, a $450 checkout
price, and $22.50 cashback when the eligible owned card truly earns 5%. Existing
fixture item totals and seeded MCC/rate assumptions have known inconsistencies;
report them and use explicit test-only eligibility/rate setup where appropriate.
Do not silently alter shared seeds or call later cashback an immediate discount.

## Team integration boundary

Do not take ownership of intake, extraction, merchant classification, production
router replacement, deployment, or extension implementation. Preserve their
interfaces and provide minimal failing cases and concrete handoff notes for the
teammate. Run complete email-to-extension tests only when the teammate's integrated
application is available; otherwise mark that coverage pending.

Deliver reproducible commands, actual results and skips, interface defects, and a
short Person 3 demo runbook. Do not push, deploy, or merge remotely without user
authorization.
