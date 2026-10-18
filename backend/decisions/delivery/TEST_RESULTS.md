# Verified delivery results

Run on October 17, 2026 (America/Los_Angeles), branch `codex/person3-delivery`,
against isolated local PostgreSQL 17.11 with pgcrypto/pgvector and real Uvicorn TCP
responses. Python 3.10.11, pytest 8.4.2, Chromium 151.0.7922.34. The implementation
also uses the repository's documented Python 3.11+ compatible syntax.

Actual result: **25 passed in 8.09 seconds**, no skipped tests or failures. This
includes 12 delivery/job/browser tests and 13 foundation storage/wallet tests.
Three dependency deprecation warnings came from websockets and Starlette/anyio.

```sh
TEST_DATABASE_URL=postgresql://asuya@127.0.0.1:55439/postgres \
NODE_BINARY=<bundled Node executable> \
PLAYWRIGHT_NODE_MODULE=<bundled playwright directory> \
python -m pytest backend/tests/test_delivery.py backend/tests/test_storage_wallet.py \
  -v -s --junitxml=/private/tmp/perk-delivery-results.xml -o junit_family=legacy
```

Measured transaction-commit return to parsed `reward_added` arrival through HTTP,
using **production default one-second polling**: median **1.0013 seconds**, maximum
**1.0020 seconds**, three independent committed inserts on one open stream. This
is a local component measurement, not a deployment/proxy/load latency guarantee.

Chromium imported the actual `fetch-events.mjs` example and verified:

- Native EventSource ignored the `headers` option, omitted X-User-Id and failed 401.
- Fetch sent X-User-Id and Last-Event-ID and received the expected retained replay.
- After its catch-up marker, an additional committed insert arrived on the same
  stream; three frames were observed (replay, sync_complete, live reward).
- The browser aborted consumption cleanly.

The actual scheduling command was invoked as a separate Python process twice
against the disposable schema. The first run expired one reward; the second run
expired zero and emitted zero alerts, then exited successfully.

Covered behavior: uncommitted/rolled-back writes; per-user commit ordering;
multi-client fan-out and isolation; reconnect replay and writes during catch-up;
heartbeat, disconnect, shutdown, stream capacity, query timeout and stream lifetime;
offline used/expired state and removed cards/memberships; old reward timestamps and
equal event timestamps; serialized sync snapshots and database watermarks; time-only
expiration; exact expiration/window endpoints; UUID job pagination; repeat/overlap
deduplication; configurable windows; and rollback when event persistence fails.

This branch exports routes/hooks only. Production main.py stub replacement, CORS
configuration, proxy settings and the external UTC job schedule remain integration
requirements described in README.md. No production deployment or scheduler was run.
