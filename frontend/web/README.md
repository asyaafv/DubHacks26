# Lapse web

Dashboard, savings, and calendar for the Lapse rewards inbox. Landing and onboarding are placeholders.

## Run

```bash
# 1. Backend (in-memory demo mode, from the repo root)
pip install -r requirements.txt
PERK_ALLOW_DEMO_IDENTITY=true python3 -m uvicorn backend.app.main:app --port 8000

# 2. Web app
cd frontend/web
npm install
npm run dev
```

Open http://localhost:5173/ — both `/` and `/?demo=1` go straight to the demo
user's dashboard (`00000000-0000-0000-0000-000000000001`, `aamir@lapse.app`).
The placeholder landing and onboarding pages are kept at `/landing` and
`/onboarding`.

## API

- Base URL: `VITE_API_BASE`, default `http://localhost:8000`
- Every request sends `X-User-Id`
- The live backend is the default. If it is unreachable (network error), the
  app automatically falls back to the built-in mock data for the rest of the
  session. Set `VITE_USE_MOCKS=true` to force mock mode. See `.env.example`.
- Live updates stream from `GET /events` (SSE) via the fetch-based client in
  `src/api/events.ts` (vendored from `backend/decisions/delivery/fetch-events.mjs`);
  a `reward_added`/`reward_updated`/`reward_used` event triggers a refetch of
  `/sync` and `/savings`, so an email injected through `POST /demo/inject` or
  `/demo/console` shows up on the dashboard without a reload.

Mock fallback loads rewards, merchants, cards, and memberships from `shared/seed`. Sketch rewards that are not in the seed (McDonald's 500 points, H&M 2,000 points, PacSun BOGO jeans, Aéropostale 50% off select items, Ulta 500 points, Ulta card 10% cashback, Amex flight rewards) live in `src/api/extras.ts`.

The savings contract is implemented by the backend (`GET /savings`, `POST /rewards/{id}/redeem`) and mirrored by the mock:

- `GET /savings` → `{ total, items: [{ reward_id, merchant_name, description, saved, redeemed_at }], series: [{ date, cumulative }] }`
- `POST /rewards/{id}/redeem` body `{ saved }` → `Reward` with `status: "used"`

The demo history is 8 redemptions over the past six weeks totaling `$103.51`. Marking a reward as used appends a redemption and updates the total and burn-up series for the session.
