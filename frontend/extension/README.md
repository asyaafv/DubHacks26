# Lapse browser extension

Chrome MV3 extension (WXT, React, TypeScript, Tailwind) for the Lapse checkout flow.

Demo user: `aamir@lapse.app` (`00000000-0000-0000-0000-000000000001`).

## Scripts

```bash
cd frontend/extension
npm install
npm test
npm run build
```

`npm run dev` rebuilds on change. Load the unpacked folder printed by WXT (`.output/chrome-mv3-dev` while dev is running, `.output/chrome-mv3` after `npm run build`).

## Load unpacked

1. Open `chrome://extensions`.
2. Turn on **Developer mode**.
3. Click **Load unpacked**.
4. Choose `frontend/extension/.output/chrome-mv3`.
5. Visit a cart, for example `https://hollisterco.com/cart`.
6. Open the Lapse toolbar icon. Enter `500` and choose **Find best stack**.

In the default build, mock mode is on (`VITE_USE_MOCKS=true`). Hollister's cart shows the 10% code `HCOFALL10` and the seed fixture savings. No backend is required.

Load unpacked from the `chrome://extensions` page. Current Google Chrome builds ignore the `--load-extension` command-line flag; the extensions page still accepts this folder.

`npm run verify` loads the built extension in Chrome for Testing, opens a Hollister `/cart` page, enters a $500 cart, and checks the code, red expiry, and savings.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `VITE_API_BASE` | `http://localhost:8000` | API origin. Every request sends `X-User-Id`. |
| `VITE_USE_MOCKS` | `true` (also when unset) | `false` calls the API. Anything else reads `shared/seed`. |
| `VITE_DASHBOARD_URL` | `http://localhost:5173/dashboard` | **Open dashboard** target. |

Vite inlines these at build time. Change `.env.production` and run `npm run build` again.

Mock lookup, stack, and sync read `shared/seed/*.json`, including `shared/seed/fixtures/hollister_500_cart.json` for a $500 Hollister cart.
