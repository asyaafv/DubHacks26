# Delivery integration

This module owns `GET /events`, `GET /sync` and the one-shot expiration command.
It consumes foundation commit `ff19234717b5187b23f6d73bfc69632ab408f8f9` or later.
No public Pydantic models, migrations, manifests or main.py were changed here.
The foundation owner supplied the requested internal database-clock, event-watermark,
timestamp-event-replay and bounded scheduler scan interfaces. Shared-contract docs
were requested to clarify inactive reward deltas, replacement wallet semantics and
the corrected browser example. The existing public model already supports them.

## Application wiring (integration owner)

Remove the existing `/events` and `/sync` stub registrations before including this
router; registering duplicate routes leaves the first stub handling requests.

```python
from backend.decisions.delivery import router, startup, shutdown

app.include_router(router)

# In your existing lifespan, after creating app.state.database:
await startup(app)
try:
    yield
finally:
    await shutdown(app)
    await app.state.database.close()
```

The hooks reuse the existing database and start no scheduler, queues or background
polling tasks. Settings can be passed to `startup(app, Settings(...))` from
`backend.decisions.delivery.service`. Configure your ASGI server's graceful shutdown
deadline (e.g. Uvicorn `--timeout-graceful-shutdown 10`), since servers may wait for
open responses before invoking lifespan shutdown. Streams also rotate after ten
minutes, retaining their cursor across reconnects.

Deploy behind a proxy with response buffering disabled and idle timeout above 15
seconds. SSE responses have `Content-Type: text/event-stream`,
`Cache-Control: no-cache, no-transform` and `X-Accel-Buffering: no`. No Content-Length
is set; hop-by-hop Connection headers are left to the ASGI server for HTTP/1 vs HTTP/2.
Allow the actual extension origin and local development origins through CORS,
allow request headers `X-User-Id`, `Last-Event-ID`, `Accept`, and expose response
header `X-Event-Cursor`. Existing literal `http://localhost:*` entries are not CORS
wildcards: integration should use actual origins or an appropriate origin regex.
The extension requires host permissions for the backend origin.

## Identity and browser consumption

Both endpoints resolve the existing `X-User-Id: <uuid>` convention through
`resolve_user`. No identity yields 401 unless `PERK_ALLOW_DEMO_IDENTITY=true`;
invalid UUID yields 400. This preserves demo identity and does not introduce a new
authentication scheme. Every replay query is scoped through `transaction(user)`.

Native EventSource accepts only `withCredentials`, not arbitrary headers:
https://developer.mozilla.org/en-US/docs/Web/API/EventSource/EventSource
Fetch supports request headers and incremental response-body reads:
https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch

Use the tested [fetch-events.mjs](fetch-events.mjs) module in the extension's
background script. Its LF SSE parser matches this server's framing, handles split
UTF-8/chunks, ignores comments/retry frames, limits frames to 1 MiB, aborts cleanly,
and reconnects network failures with bounded exponential backoff. Application
errors stop consumption so failed state application cannot be checkpointed away.

```javascript
import {connectEvents} from './fetch-events.mjs';

const controller = new AbortController();
await connectEvents({
  url: 'http://127.0.0.1:8000/events',
  userId,
  lastEventId: savedCursor, // scoped to this backend/user, or '' to replay all
  signal: controller.signal,
  apply: async (event, id) => {
    // Apply idempotently and persist the checkpoint in the same local transaction.
    // On reward events fetch /sync?since=<saved last_sync> to obtain current models.
    // sync_complete is a catch-up marker, not a new reward mutation.
    await applyAndCheckpoint(event, id);
  },
});
// Call controller.abort() when disconnecting or changing users.
```

Chrome MV3 workers can suspend or restart. Persist cursors/state in extension
storage, reconnect on worker activation and periodically call /sync to reconcile
wallet changes. Do not depend on a permanently live extension worker or stream.

## SSE ordering, replay and capacity

The durable `events` table is the only event source. Each connection polls at most
once per second while caught up, reads up to 100 rows per page and drains full pages
without sleeping. Foundation serializes writers before sequence allocation using
the user row lock, so a later committed sequence cannot overtake an earlier write
for that user. Stream reads acquire the same lock and release the transaction before
yielding any bytes. A rollback is invisible. No notifications are necessary for
correctness and no event's legacy `delivered` flag is read or changed.

IDs are `<user UUID>:<durable sequence>`. A new connection without Last-Event-ID
replays the retained history from sequence zero. A reconnect supplies the last
successfully applied ID and receives strictly greater sequences. IDs malformed,
belonging to another user, or ahead of that user's current history yield 400.
Sequence gaps from rolled-back transactions or other users are normal. Only use
server-issued IDs. Each client owns its own checkpoint; multiple clients see the
same events. Retention/pruning requires a future explicit reset protocol; do not
prune this outbox while clients may need replay.

Catch-up and live delivery use exactly the same query and cursor. After the first
short page the server emits the existing `sync_complete` Event with the current
cursor, then continues querying after it. Writes between a page read, that marker
and the next read are recovered on the next poll; no subscribe/catch-up race exists.
The marker does not promise that no writes committed after the page read.
Disconnects can replay a frame whose application/checkpoint was interrupted:
delivery is at least once, requiring idempotent local upserts/checkpoints. Public
Event payloads/types are preserved and contain only foundation's safe status/expiry
metadata, never codes or membership identifiers.

Comment heartbeats are emitted at approximately 15 seconds while caught up (active
event traffic also keeps the transport live). Defaults bound connections to 128
per worker, eight per user per worker, ten minutes lifetime and five seconds per
database query. Polling retains at most one 100-event page per client, no client
queues or permanent DB leases. Slow readers apply transport backpressure. Capacity
rejection is 429 with Retry-After. Initial DB failure/timeout is retryable 503;
midstream failure closes the stream for replay. Disconnect/cancellation releases
capacity in finally; shutdown wakes waiting streams. Limits are per worker and
deployment should also bound total workers and ingress concurrency.

## Offline sync semantics

`GET /sync?since=<last_sync>` uses the existing datetime parameter and SyncResponse.
An omitted since returns a complete reward snapshot (all statuses), full wallet,
no historical pending_events, and a database UTC `last_sync`. Replace the local
reward set on a full snapshot. For incremental sync, upsert rewards by ID and use
their status to remove used/expired/review rewards from active UI. Never append
wallet arrays: every wallet is authoritative replacement, including empty arrays
after card/membership removal. Rewards must remain tombstones in storage rather
than being physically deleted.

Within one user transaction the service captures DB clock time **after** acquiring
the owner lock, reads the event watermark, rewards, events and wallet, commits, then
returns. Cooperating writers cannot interleave those reads. Changes are selected
inclusively (`updated_at >= since`, event `created_at >= since`), and every reward
referenced by a selected event is hydrated even if its supplied updated_at is old.
The next client watermark is the returned `last_sync`, never its local wall clock.
Equal timestamps may repeat an upsert/event; deduplicate by reward ID and event
identity/content. A timestamp is not an exclusive sequence cursor. Database UTC
time is assumed nondecreasing; use the sequence feed for durable event replay.
Future since values return 400. Legacy naive datetimes are interpreted as UTC.

Time-only expirations crossing since are included and projected as status expired
even before the daily job changes storage. Wallet counts also use query-time
eligibility. The recommendation owners must use foundation `list_rewards`/
`search_rewards` default eligibility (`expires_at > now`), never active status alone.

`X-Event-Cursor` captures the snapshot's sequence. After applying a full snapshot,
connect SSE with this Last-Event-ID to receive changes committed afterward. Save
the snapshot and cursor together. Snapshot recovery plus replay overlap is safe
with idempotent state updates; wallet changes remain discoverable through /sync.
Incremental pending_events are bounded at 10,000: a larger backlog returns 409
instructing a full snapshot, never a truncated success. Full snapshot size follows
the existing unpaginated public response contract; large-wallet pagination requires
a coordinated future contract change. The default five-second sync deadline bounds
transaction duration and returns 503 if exceeded.

## Daily expiration command (Person 1 schedules)

Run from the repository root in the installed backend environment:

```sh
python -m backend.decisions.jobs.expire --window-hours 24 --batch-size 100
```

Provide `DATABASE_URL` and `PERK_ENCRYPTION_KEY` using deployment secrets and apply
foundation migrations first. The command connects, runs once, prints JSON counts
(`users`, `expired`, `alerts`), closes the pool, and exits nonzero on failure. Schedule
it daily at 00:00 UTC, e.g. managed scheduler cron `0 0 * * *` with timezone UTC.
No API worker starts a scheduler. Configure working directory, Python environment,
secrets, failure monitoring and retries in Person 1's deployment system.

`run_expiration(database, clock=utc, window=timedelta(hours=24), batch_size=100)`
accepts an injectable clock and captures one aware UTC instant for the run. It
pages users and candidate rewards by UUID, at most batch_size rows at a time.
Expired means active and `expires_at <= now`, including the exact boundary; each
transition and its `reward_updated` event commit atomically. Upcoming alerts mean
active, started, and `now < expires_at <= now + window`. Future-starting offers do
not alert yet. The default window is 24 hours; --window-hours accepts a positive
decimal up to 8760. A daily schedule can alert up to 24 hours before expiry;
offers arriving after a day's scan may expire before the next scan. Schedule more
frequently if the product requires a tighter alert opportunity.

The stable dedupe key is `expiring:<reward UUID>:<UTC expiry ISO>:<window microseconds>`.
Re-running or overlapping runs cannot duplicate that user/reward/expiry/window
alert: foundation's user lock plus unique per-user event key protects the atomic
read/change/event transaction. Changing the configured window intentionally permits
a separate alert, as does changing expiration. Expired/used statuses never alert.
A failed batch rolls back both changes and events; earlier committed batches can
be safely retried. UUIDs inserted behind a running scan's cursor wait for the next
run. Query-time eligibility excludes expired rewards immediately regardless of
job timing or failure.

## Verification

Run the real database and HTTP tests, using a disposable test database:

```sh
TEST_DATABASE_URL=postgresql://... python -m pytest \
  backend/tests/test_delivery.py backend/tests/test_storage_wallet.py -v -s
```

For the optional real-browser test also set `NODE_BINARY` to a Node executable and
`PLAYWRIGHT_NODE_MODULE` to the installed Playwright module directory, with its
Chromium browser installed. No Python/Node manifests are changed by this component.
The browser test imports the actual fetch example, proves native EventSource
ignores headers, then verifies fetch replay and a newly committed live event.

Tests exercise real Postgres/pgcrypto/pgvector and Uvicorn TCP streaming, including
commit/rollback visibility, two clients, user isolation, Last-Event-ID replay,
catch-up/live boundary writes, heartbeat/cleanup/capacity, offline status and wallet
removal, old/equal timestamps, concurrent snapshots, time-only expiration, exact
expiration/window boundaries, alert deduplication, overlapping/paged jobs and job
rollback. See delivery/TEST_RESULTS.md for measured results from this branch.
