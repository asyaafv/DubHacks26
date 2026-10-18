# Lapse web

Dashboard, savings, and calendar for the Lapse rewards inbox. Landing and onboarding are placeholders.

## Run

```bash
cd frontend/web
npm install
npm run dev
```

Open http://localhost:5173/?demo=1

That signs in the demo user (`00000000-0000-0000-0000-000000000001`, `aamir@lapse.app`) and opens the dashboard. A small **Demo** link on `/` and `/onboarding` does the same thing.

## API

- Base URL: `VITE_API_BASE`, default `http://localhost:8000`
- Every request sends `X-User-Id`
- `VITE_USE_MOCKS` defaults to on. Set `VITE_USE_MOCKS=false` to call the live API. See `.env.example`.

Mock mode loads rewards, merchants, cards, and memberships from `shared/seed`. Sketch rewards that are not in the seed (McDonald's 500 points, H&M 2,000 points, PacSun BOGO jeans, Aéropostale 50% off select items, Ulta 500 points, Ulta card 10% cashback, Amex flight rewards) live in `src/api/extras.ts`.

Savings history is not in the shared contract yet. The mock implements:

- `GET /savings` → `{ total, items: [{ reward_id, merchant_name, description, saved, redeemed_at }], series: [{ date, cumulative }] }`
- `POST /rewards/{id}/redeem` body `{ saved }` → `Reward` with `status: "used"`

The demo history is 8 redemptions over the past six weeks totaling `$103.51`. Marking a reward as used appends a redemption and updates the total and burn-up series for the session.
