# Audit checklist — API contracts

Scope: `shared/CONTRACTS.md` vs `backend/app/schemas.py` vs live responses from
`uvicorn backend.app.main:app` (in-memory, no `DATABASE_URL`, populated via
`POST /demo/inject`) vs frontend expectations on `cursor/web-dashboard-2556`
(`frontend/web/src/types.ts`, `src/api/*.ts`) and `cursor/lapse-extension-6787`
(`frontend/extension/src/api/*.ts`, `src/core/sse.ts`). Branch audited:
`main` + merge of `cursor/gliner-graceful-degrade-2679` (PR #22).

## Endpoint status

| Endpoint | Status | Evidence | Latency |
|---|---|---|---|
| `GET /health` | Works | `curl localhost:8000/health` → 200, matches `HealthCheck`; `services` values are `"stub"` not `"healthy"` (cosmetic) | <5 ms |
| `POST /inbound` | Works | Minimal Postmark JSON (`From`/`To` only) → 200 `{classification:"reward", rewards_extracted:1, duplicate:false, note:null}`; superset of `InboundResult` (now documented) | ~2 ms |
| `POST /demo/inject` | Works | `{"eml_filename":"hollister_10_percent.eml","force":true}` → 200, 1 reward; `force` bypasses dedupe (now documented) | 4 ms processing |
| `GET /demo/emails` | Works | → `{"emails":[5 .eml files]}`; list matches CONTRACTS' available-emails list; endpoint was undocumented (now documented) | <5 ms |
| `GET /demo/console` | Works | → 307 to console index; was undocumented (now documented) | <5 ms |
| `GET /wallet` | Partial | In-memory mode → **503** `"Database is not configured"`. Documented behavior per Person 3, but means no wallet in a DB-less demo | — |
| `POST /wallet` | Partial | → **503** without DB; with DB, rejects non-product card fields (422), per contract | — |
| `POST /stack` | Works | Hollister $500 → 200, `HCOFALL10`, savings `"50.0000"`, matches `StackResult`; decimal strings have >2 dp; picks first card not best (`solver_status:"stub"`) | <2 ms |
| `POST /lookup` | Works | Hollister domain → 200, matches `LookupResult`; ranking puts a category-match (Gap) above the merchant's own reward — scoring quality, not contract | <2 ms |
| `GET /sync` | Broken (in-memory) | → **503** (wallet bridge needs Postgres). With DB: active-only rewards, `since` ignored, `pending_events` always `[]`, no `X-Event-Cursor` header | — |
| `GET /events` (SSE) | Partial | `curl -N -H 'Accept: text/event-stream'` → `sync_complete` + queued `reward_added` frames. No `id:` lines, `Last-Event-ID` ignored, naive timestamps, plaintext `code` in data, 30 s stub `reward_expiring` | events ≤1 s after inject |
| `POST /classify-merchant` | Works | known → 200 `confidence:0.95,is_new:false`; unknown → `mcc:"5999",is_new:true`; exact contract match | <2 ms |
| `POST /rewards/{id}/redeem` | Missing | → 404 `{"detail":"Not Found"}`; planned (Person 3); web dashboard live mode depends on it | — |
| `GET /savings` | Missing | → 404; planned (Person 3); web Savings page live mode depends on it | — |

Counts: **7 Works, 3 Partial, 2 Missing, 1 Broken** (+1 Works for /demo/console).

## Mismatch list (field-by-field) and who should change

| # | Mismatch | Detail | Least-risk fix |
|---|---|---|---|
| 1 | CORS blocks the web dashboard | `allow_origins=["http://localhost:*"]` is exact-match in Starlette; preflight from `http://localhost:5173` → 400 "Disallowed CORS origin". Extension OK via regex | **Backend** (`backend/app/main.py`): one-line `allow_origin_regex` change (see CONTRACTS "Known gap"). P0 if web runs live |
| 2 | `/sync` + `/wallet` 503 without Postgres | Wallet bridge requires `DATABASE_URL`; no in-memory fallback. Both frontends call `/sync` in live mode | **Backend/demo setup**: run demo with Postgres configured, or restore in-memory wallet fallback in `main.py`. Frontends need no change. P0 for live mode, P2 if demo stays on mocks |
| 3 | `/savings`, `/rewards/{id}/redeem` missing | Web `api/client.ts` calls both; `savings.ts` types match the agreed spec exactly (decimal-dollar strings, `YYYY-MM-DD`, $103.51 seed) | **Backend** implements per `backend/decisions/README.md`; frontend already matches. P1 |
| 4 | SSE event shape vs CONTRACTS | Live stream has no `id:` lines / cursor replay; `reward_added.data` **includes plaintext `code`** (CONTRACTS says never); extension `toastMessage()` *relies* on `code` | **Docs** (fixed in CONTRACTS): documented current stub shape; frontend keeps its no-code fallback for when the durable router lands |
| 5 | Event `timestamp` naive (no `Z`/offset) | `Event.timestamp` default is `datetime.utcnow` (naive) → `"2026-10-18T07:44:04.206305"`; contract examples show `Z`. All other datetimes serialize with `Z` | **Backend** `backend/app/schemas.py`: `default_factory=lambda: datetime.now(timezone.utc)`. Extension only uses it as a dedupe key, so P2 |
| 6 | `/sync` returns active-only, ignores `since` | CONTRACTS full-snapshot/delta semantics describe the unwired delivery router | **Docs** (fixed): stub behavior called out next to the integration note |
| 7 | Error shape not universal | 404 route → `{"detail":"Not Found"}`, 422 → `{"detail":[...]}` instead of `{error,message,details}` | **Docs** (fixed): caveat added; both frontends already fall back to status text |
| 8 | `/inbound` + `/demo/inject` response superset | Live returns extra `duplicate`, `note`; `force` flag undocumented | **Docs** (fixed): documented in CONTRACTS |
| 9 | `X-User-Id` fallback inconsistent | Stub endpoints default missing header to demo user; `/wallet`/`/sync` return 401 without `PERK_ALLOW_DEMO_IDENTITY=true` | **Docs** (fixed): "always send the header" noted; both frontends already always send it |
| 10 | Money precision | `/stack` returns `"50.0000"`, `"4.50000"`, `"10.900"` (unquantized Decimal) vs 2-dp contract examples | No change needed: both frontends parse with `Number()`/`toCents()`. Optional backend polish: quantize to 2 dp. P2 |
| 11 | Undocumented demo endpoints | `GET /demo/emails`, `GET /demo/console` absent from CONTRACTS | **Docs** (fixed) |

No mismatches found in: enum values (RewardKind/RewardSource/RewardStatus/
CardNetwork/EventType/EmailClassification identical across schemas.py,
shared/types.ts, and both frontends), field names/casing (snake_case
everywhere), money units (decimal-dollar strings everywhere, never cents),
non-event date formats (ISO-8601 with `Z`), Reward/Wallet/Stack/Lookup shapes.

## Fixes made (this PR — docs only, my area is `shared/CONTRACTS.md`)

- Documented `/inbound` + `/demo/inject` superset fields (`duplicate`, `note`) and the `force` flag.
- Documented `GET /demo/emails` and `GET /demo/console`.
- Added verified "current stub behavior" callouts to `/sync` and `/events` (503 without DB, no SSE ids, plaintext `code` in events, naive timestamps, stub `reward_expiring`).
- Expanded the Savings & Redemption section with the exact agreed shapes (matches the web branch's `savings.ts`) and marked both endpoints 404-today.
- Documented the CORS localhost gap with the exact one-line fix, and the error-format caveat.
- Added a "Frontend integration notes" section the frontend teammate can act on directly.

## Needs fix elsewhere

1. **P0 (live web demo)** `backend/app/main.py`: CORS — replace `allow_origin_regex=r"chrome-extension://.*"` with `r"chrome-extension://.*|https?://(localhost|127\.0\.0\.1)(:\d+)?"` (and drop the ineffective wildcard `allow_origins` entries).
2. **P0 (live mode) / P2 (mock demo)** `backend/app/main.py` (`get_wallet` bridge): `/sync` 503s without `DATABASE_URL`. Either run the demo with Postgres + seeded wallet, or restore an in-memory wallet fallback when `app.state.database is None`.
3. **P1** `backend/decisions` (Person 3): implement `GET /savings` + `POST /rewards/{id}/redeem` per `backend/decisions/README.md`; seed `shared/seed/seed_redemptions.json` totaling $103.51. Web dashboard is already coded to the exact spec.
4. **P2** `backend/app/schemas.py`: `Event.timestamp` (and other `datetime.utcnow` defaults) → timezone-aware `datetime.now(timezone.utc)` so SSE timestamps serialize with `Z`.
5. **P2** `backend/app/main.py` `/stack`: quantize Decimal outputs to 2 dp to match contract examples.

## Tests

No code changed (docs only), so no new tests. Verification was live-endpoint
probing as recorded in the evidence column; existing test suite untouched.
