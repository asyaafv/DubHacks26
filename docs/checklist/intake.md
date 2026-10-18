# Audit checklist: intake + live demo path

Audited on branch `cursor/audit-intake-66a2` (main @ b263e93 + merge of
`origin/cursor/gliner-graceful-degrade-2679`, PR #22). Verified live with
`python3 -m uvicorn backend.app.main:app --port 8000` + curl, no Postgres
(in-memory dedupe/reward stores). Deps: root `requirements.txt` +
`backend/intake/requirements/*.txt` + `presidio-anonymizer` +
`en_core_web_sm` (spaCy small model).

## Checklist

| Feature | Status | Evidence | Latency |
|---|---|---|---|
| `GET /health` | Works | `curl /health` -> 200 `{"status":"healthy",...}` | 2 ms |
| `POST /inbound` Postmark payload, MailboxHash `aamir` | Works | 200 `{"classification":"reward","rewards_extracted":1,...}`; reward persisted with code `SAVE20`, value 20%, expiry parsed | 796 ms first call (Presidio lazy-load), ~100 ms warm |
| `/inbound` unknown recipient -> 200 note | Works | MailboxHash/To `stranger` -> 200 `{"rewards_extracted":0,"note":"unknown_recipient"}` (never 4xx, so Postmark won't retry) | 1 ms |
| `/inbound` malformed body -> 400 | Works | `-d 'this is not json'` -> 400 `Request body must be JSON`; `-d '[1,2]'` -> 400 `must be a JSON object` | 1 ms |
| Dedupe by MessageID | Works | Re-POST same payload -> 200 `{"duplicate":true,"note":"duplicate","rewards_extracted":0}` | 1 ms |
| Dedupe by content hash | Works | Same body, new `MessageID` -> 200 `duplicate:true` (sha256 of sender domain + subject + normalized body, tracking params stripped) | 1 ms |
| `POST /demo/inject` | Works | `hollister_10_percent.eml` -> 1 reward; repeat w/o force -> `duplicate:true`; `"force":true` -> re-extracts; missing file -> 404 | 95–115 ms |
| `GET /demo/emails` | Works | Lists all 5 seed `.eml` files | 2 ms |
| `GET /demo/console/` page | Works | 200, 16.4 KB HTML (inline CSS/JS) | 1 ms |
| Console: 6 templates, instant mode -> reward card | Works (1 cosmetic issue) | `POST /demo/console/send` for all of `hollister_10`, `tacobell_crunchwrap`, `ulta_points`, `pacsun_bogo`, `aero_50`, `target_5off` -> `rewards_extracted=1` + 1 card each, correct kind/code. Cosmetic: bogo/free_item cards show `value=0` when GLiNER isn't installed (see Needs fix elsewhere) | 10–106 ms |
| `GET /events` SSE emits `reward_added` | Works | Connected listener + `/demo/inject` force -> `event: reward_added` received **96 ms** after inject (generator polls every 1 s, so worst case ~1 s) | ≤ 1 s |
| Presidio redaction active | Works | `redact.warm_up()` -> `True` (real Presidio engine, not regex fallback); `(206) 555-0143` -> `<PHONE>`, Visa test PAN -> `<CARD>`, third-party email -> `<EMAIL>`, `123 Main St, Apt 4` -> `<ADDRESS>` | ~1 s one-time engine load |
| Promo codes survive redaction | Works | `SAVE20` in a body alongside phone/card/email PII -> extracted reward has `code":"SAVE20"`; store names (Hollister) untouched | — |
| CORS: `chrome-extension://` origins | Works | Preflight `Origin: chrome-extension://abcdefgh` -> 200, `access-control-allow-origin` echoed | 1 ms |
| CORS: localhost dashboard origins | **Fixed this audit** (was Broken) | Was 400: `allow_origins=["http://localhost:*"]` is matched literally by Starlette (no globbing) and the regex only covered extensions. Fixed `allow_origin_regex` in `backend/app/main.py`; now `http://localhost:3000` / `http://127.0.0.1:5173` -> 200 echoed, `https://evil.com` still rejected. Test: `backend/tests/intake/test_cors.py` | 1 ms |

Counts: 13 Works, 0 Partial, 0 Missing, 1 Broken (CORS localhost — fixed in this PR).

## Fixes made (this PR)

1. **CORS localhost origins rejected** (`backend/app/main.py`): replaced the
   ineffective literal wildcard entries with
   `allow_origin_regex=r"chrome-extension://.*|https?://(localhost|127\.0\.0\.1)(:\d+)?"`.
   New test `backend/tests/intake/test_cors.py` (7 tests) pins extension +
   localhost preflight and rejects unknown origins.

## Needs fix elsewhere

1. **P1 (visible in demo)** — `backend/extraction/pipeline.py` lines 447–452:
   the fields-merge path sets `value = Decimal("0")` for `bogo` and
   `free_item`, while `backend/extraction/normalize.py:128-131` uses
   `Decimal("1")` for the same kinds. With GLiNER not installed (regex path),
   console cards for `pacsun_bogo` / `tacobell_crunchwrap` show value 0 and 3
   intake console tests fail. Suggested change: use `Decimal("1")` in both
   branches of pipeline.py to match normalize.py. (Cards still render; kind
   and code are correct.)

No P0s remaining in this area.

## Test counts

`python3 -m pytest backend/tests/intake` — **138 passed, 3 failed** (the 3
failures are the bogo/free_item value=0 extraction issue above, asserting on
`run_pipeline` output; they pass where GLiNER2 is installed, e.g. the Docker
image with baked models). Before this audit: 131 passed, 3 failed; +7 new
CORS tests.

## Notes

- First `/inbound` call pays ~700 ms Presidio lazy-load; consider calling
  `backend.intake.redact.warm_up()` at startup if first-request latency
  matters for the demo.
- Console email mode correctly reports disabled (no `POSTMARK_SERVER_TOKEN`
  / `DEMO_FROM_EMAIL` in this environment); instant mode fully works.
- `intake_status()` reports all three stages (routing, dedupe, redact)
  running real modules, no fallbacks.
