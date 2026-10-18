# LAPSE rename verification

Verified October 17, 2026 (America/Los_Angeles). Current source, configuration,
documentation, and local worktree folder names use LAPSE/Lapse/lapse consistently.
Git history and original feature commit identities are preserved.

## Current local working copies

All paths are under `/Users/asuya/Documents/ChatGPT/DUBHACKS/`:

- `lapse-foundation`: `codex/person3-stacking` (the primary Git working copy).
- `lapse-foundation-delivery`: `codex/person3-foundation`.
- `lapse-lookup`: `codex/person3-lookup`.
- `lapse-delivery`: `codex/person3-delivery`.

Git worktree links were repaired after the folder moves. Virtual-environment
entry points were updated to their relocated paths. These directories remain
separate; a feature branch does not contain every other feature automatically.

## Configuration

Use `LAPSE_ENCRYPTION_KEY`, `LAPSE_ALLOW_DEMO_IDENTITY`, and `LAPSE_MODEL_CACHE`.
Keep the same encryption key value for existing encrypted records. The Compose
example now uses database/user `lapse` and volume `lapse_postgres`. No existing
database records or encryption keys were changed by the source/config rename.

## Regression checks after renaming

Executed against an isolated native PostgreSQL 17 cluster on localhost port 55491,
with actual pgcrypto/pgvector. The temporary server was used only for these checks.

- Foundation storage/wallet: **13 passed**.
- Stacking plus its branch's storage/wallet tests: **67 passed**.
- Lookup components, real offline MiniLM/pgvector tests, and storage: **30 passed**.
- Delivery, expiration CLI, real HTTP SSE, Chromium, and storage: **25 passed**.

Counts describe separate suites and include repeated storage checks; they are not
a total of unique tests. Existing dependency deprecation warnings remain.
These checks do not establish complete email-to-extension product integration.

All four renamed worktrees were checked for source naming remnants and clean Git
state. The rename commits are local; publishing them is a separate action.
