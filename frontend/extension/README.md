# Lapse browser extension

Chrome MV3 extension (WXT, React, TypeScript, Tailwind) for the Lapse checkout flow.

Demo user: `aamir@lapse.app` (`00000000-0000-0000-0000-000000000001`). Every API
request sends `X-User-Id: 00000000-0000-0000-0000-000000000001` per
`shared/CONTRACTS.md`.

## Quick start (local backend)

```bash
# 1. Backend (repo root) — in-memory mode, no Postgres needed
pip install -r requirements.txt
uvicorn backend.app.main:app --port 8000

# 2. Extension
cd frontend/extension
npm install
npm test
npm run build        # outputs .output/chrome-mv3
```

## Load unpacked

1. Open `chrome://extensions`.
2. Turn on **Developer mode** (top right).
3. Click **Load unpacked**.
4. Choose `frontend/extension/.output/chrome-mv3`.
5. Visit a cart page, for example `https://www.hollisterco.com/shop/us/bag`
   (any URL containing `/cart`, `/checkout`, `/bag`, or `/basket` counts as checkout).
6. Click the Lapse toolbar icon. Enter the cart total (e.g. `500`) and press
   **Find best stack** — the panel shows the CP-SAT result from `POST /stack`
   (final price, savings, recommended card, explanation, copyable codes, and a
   **Mark used** button that calls `POST /rewards/{id}/redeem`).

Current Google Chrome ignores the `--load-extension` command-line flag; the
`chrome://extensions` page still accepts this folder.

### Demo flow

With the backend running, open `http://localhost:8000/demo/console`, pick the
Hollister template, mode **Instant**, and send. The extension shows a live toast
(from `GET /events` SSE) within ~2s, the popup lists the new reward, and
`GET /savings` grows after **Mark used**.

## Point at a deployed backend

The API origin is baked in at build time (both into the bundle and into the
manifest `host_permissions`):

```bash
cd frontend/extension
VITE_API_BASE=https://lapse-api.onrender.com npm run build
```

(or edit `VITE_API_BASE` in `.env.production` and run `npm run build`). Then
re-load the unpacked folder (`chrome://extensions` → reload icon on the Lapse
card). CORS for `chrome-extension://` origins is already allowed by the backend
(`allow_origin_regex` in `backend/app/main.py`).

## Live mode vs mocks

- **Default (`VITE_USE_MOCKS=false`)**: every screen calls the real API
  (`/lookup`, `/stack`, `/sync`, `/events`, `/rewards/{id}/redeem`). If the
  backend is **unreachable** (network error — not an HTTP error), the client
  automatically serves `shared/seed` mock data instead and logs
  `[Lapse] backend unreachable at <base> — serving MOCK <endpoint>` to the
  service-worker console so you can tell.
- **`VITE_USE_MOCKS=true`**: forces mock data; never touches the network.

## Verify end to end

```bash
npm run build
npm run verify     # loads the built extension in Chrome, drives the full flow
```

With the backend running on `http://localhost:8000`, `npm run verify` injects
the Hollister email via `/demo/inject`, waits for the SSE toast, checks the
popup reward, runs the $500 stack ($50 HCOFALL10 + $22.50 US Bank Cash+ =
$72.50), copies the code, clicks **Mark used**, and asserts `GET /savings`
increased. Without a backend it verifies the mock fallback path instead.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE` | `http://localhost:8000` | API origin (bundle + manifest `host_permissions`). |
| `VITE_USE_MOCKS` | `false` (also when unset) | `true` forces `shared/seed` mocks. |
| `VITE_DASHBOARD_URL` | `http://localhost:5173/dashboard` | **Open dashboard** target. |

Vite inlines these at build time; rebuild after changing them.
