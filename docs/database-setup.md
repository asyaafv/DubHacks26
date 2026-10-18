# Local Postgres

Use Python 3.11+ and Docker Compose. In your shell (not a committed file):

```sh
export POSTGRES_PASSWORD="$(openssl rand -hex 24)"
export PERK_ENCRYPTION_KEY="$(openssl rand -hex 32)"
export DATABASE_URL="postgresql://perk:${POSTGRES_PASSWORD}@localhost:5432/perk"
export PERK_ALLOW_DEMO_IDENTITY=true
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
docker compose up -d --wait
python -m backend.decisions.storage migrate
python -m backend.decisions.storage seed
uvicorn backend.app.main:app --reload --port 8000
```

Keep the password and encryption key in your shell/secret manager for future runs.
Changing the encryption key makes existing ciphertext unreadable; rotation requires
an explicit decrypt/re-encrypt migration. Do not pass the encryption key to the
Postgres container, SQL migration files or logs. Disable SQL parameter logging in
any managed Postgres deployment as well. TLS is required for remote DB connections.
Compose binds Postgres to localhost and retains data in a named volume; ordinary
`docker compose down` preserves it. Never use `down -v` against data you need.

The pinned pgvector image supplies vector; migrations enable vector, pgcrypto and
uuid-ossp. They are ordered, atomic and repeatable. Run migrations before starting
the app; DDL needs an extension-capable role. The runtime role needs normal table
and identity-sequence privileges; it does not need extension/DDL permission.
001 is an immutable snapshot of the original docs/schema.sql. Do not separately
run docs/schema.sql on a fresh migrated database. For a manually initialized old
DB: back up, verify it matches 001, create schema_migrations(version text primary
key, applied_at timestamptz not null default now()), insert '001_initial.sql', then
run migrate. Do not mark unrelated schemas as migrated.

Seed is explicit, atomic and uses the same repository/pgcrypto path as normal
writes. The import ledger means a rerun does not restore removed wallet records or
reset status changes. Existing reward timestamps are preserved, so eligible reward
counts naturally change with actual time. Seed cards discard demo last_four values;
no card-number data is collected or persisted by the wallet API.

Tests:

```sh
# Use a separate disposable database; never a production DB.
export TEST_DATABASE_URL='postgresql://perk:...@localhost:5432/perk_test'
pytest backend/tests/test_storage_wallet.py -v
# Seed a development DB first for the original HTTP contract tests:
DATABASE_URL="$DATABASE_URL" pytest backend/tests/test_contracts.py -v
```

Database tests isolate each test in its own schema and drop only that schema.
They skip explicitly if TEST_DATABASE_URL is absent. Extensions must be available
in the test database (the tests create them). API lifespan is exercised in contract
tests. Wallet has no fake persistence mode: a missing database returns 503. Remaining
stack/lookup/delivery/intake/classification routes are still owned by other chats.
