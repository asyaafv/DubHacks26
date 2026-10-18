# Lapse demo runbook (DubHacks 2026, judging 11:30 AM PT)

Everything here was smoke-tested against the Docker image built from main.
Base URLs below: `$BASE` is wherever the backend runs
(`http://localhost:8000` locally, `https://lapse-api.onrender.com` or
`https://api.lapse.app` deployed). Demo user:
`00000000-0000-0000-0000-000000000001` (MailboxHash `aamir` or `demo`).

---

## 1. Start the backend

### A. Locally (laptop, full stack with Postgres — recommended rehearsal setup)

From the repo root (image must already be built — `docker build -t lapse-api .`
takes 15-25 min, do NOT leave this for demo morning):

```bash
# One-time secrets for this shell (keep them for every later run —
# changing PERK_ENCRYPTION_KEY makes old encrypted codes unreadable):
export POSTGRES_PASSWORD="$(openssl rand -hex 24)"
export PERK_ENCRYPTION_KEY="$(openssl rand -hex 32)"

# 1. Postgres (compose.yaml binds it to 127.0.0.1:5432, data in a volume)
docker compose up -d --wait

# 2. API container, on the compose network so it can reach "postgres" by name
docker run -d --name lapse \
  --network "$(basename "$PWD")_default" \
  -p 8000:8000 \
  -e DATABASE_URL="postgresql://perk:${POSTGRES_PASSWORD}@postgres:5432/perk" \
  -e PERK_ENCRYPTION_KEY="$PERK_ENCRYPTION_KEY" \
  -e PERK_ALLOW_DEMO_IDENTITY=true \
  -e WARM_MODELS=1 \
  lapse-api

# 3. Migrate + seed (one-time per fresh database; idempotent to re-run)
docker exec lapse python -m backend.decisions.storage migrate
docker exec lapse python -m backend.decisions.storage seed

# 4. Verify
curl -s http://localhost:8000/health | python3 -m json.tool
```

To also exercise real Postmark email locally, add to the `docker run`:
`-e POSTMARK_SERVER_TOKEN=... -e POSTMARK_INBOUND_ADDRESS=... -e DEMO_FROM_EMAIL=...`
(values per docs/POSTMARK_SETUP.md). Note: Postmark's inbound webhook cannot
reach a laptop — with a local backend use the console's **instant mode**
(section 4) or a tunnel (`ngrok http 8000`) if you must show real email.

No-database variant (intake/extraction/SSE/console all work; `/wallet` and
`/sync` return 503):

```bash
docker run -d --name lapse -p 8000:8000 \
  -e PERK_ALLOW_DEMO_IDENTITY=true -e WARM_MODELS=1 lapse-api
```

### B. Render (primary deployed path)

Already described in docs/DEPLOY.md Option A. Short version: push to GitHub,
Render Dashboard → New → Blueprint → pick the repo (`render.yaml` sets the
Docker runtime, standard 2GB plan, `WARM_MODELS=1`,
`PERK_ALLOW_DEMO_IDENTITY=true`), fill the secret env vars when prompted.
First build is 15-25 min — **deploy the night before, not demo morning.**
A code push triggers a rebuild; don't push to main within an hour of judging.

```bash
curl -s https://lapse-api.onrender.com/health
```

### C. Linode (fallback deployed path)

Copy-paste commands in docs/DEPLOY.md Option B. If the box is already
provisioned, a restart is just:

```bash
ssh root@<linode-ip>
docker restart lapse-api && docker logs -f lapse-api   # wait for "[warm] OK"
```

---

## 2. Pre-demo warmup (do this ~10 min before judging)

Models load lazily per-process. With `WARM_MODELS=1` (set in `render.yaml`
and in the commands above) the container warms itself at startup — look for
this in the logs:

```
[warm] OK   server warm in 12.7s (classification=reward rewards=1 ...) — first demo email will now be fast
```

(12.7s measured on the audit box; expect ~5-6s on the deploy hardware.)

Belt-and-suspenders: warm it again manually right before walking up (safe to
run any number of times; it uses a throwaway user, never the demo user):

```bash
python3 scripts/warm_models.py --http --base-url $BASE
```

Then confirm end-to-end speed — this should report `processing_time_ms`
under ~1000 (warm ≈ 400ms):

```bash
python3 scripts/postmark_smoke.py --base-url $BASE --demo-inject
```

If the container was restarted for any reason, re-run both commands.
RAM after warmup is ~1.4GB RSS — expected, do not "fix" it mid-demo.

---

## 3. Demo sequence

Open ahead of time, in tabs:

1. **Merchant console** — `$BASE/demo/console` (the fake "merchant marketing"
   tool)
2. **Dashboard / extension** — browser with the Lapse extension loaded and a
   shopping site, dashboard page if shown
3. A terminal with `$BASE` exported, for the fallback commands

The story: *a store emails you a reward → Lapse catches it, extracts it, and
spends it for you at checkout.*

| Step | What to do | What the judges see |
|---|---|---|
| 1. Console send | In `$BASE/demo/console` pick a template (e.g. Hollister 10%), mode **Email** (or **Instant** — see fallbacks), click send | "Merchant" sends a real reward email to `…+aamir@inbound.postmarkapp.com` |
| 2. Extension toast | Wait 2-5s (email mode) / instant | Toast via `/events` SSE: "New reward: 10% off at Hollister" — the reward arrived with no user action |
| 3. Dashboard | Open the wallet/dashboard view (`/sync`, `/wallet`) | The reward card with merchant, value, code, expiry |
| 4. Checkout stack | Go to the store's cart page with the extension active (`POST /stack`) | Optimal stack: promo code + best card cashback, "You save $X" |
| 5. Redeem | Apply the code at checkout (`POST /rewards/{id}/redeem`) | Reward flips to used; code auto-filled |
| 6. Savings | Open the savings view (`GET /savings`) | Running total ($103.51 across the demo redemptions) and the series chart |

CLI equivalents (if a UI piece dies, narrate over curl):

```bash
# step 1-2 without the console UI:
python3 scripts/postmark_smoke.py --base-url $BASE --mailbox-hash demo
# watch the SSE stream (step 2):
curl -N $BASE/events -H 'X-User-Id: 00000000-0000-0000-0000-000000000001'
# step 3:
curl -s $BASE/sync -H 'X-User-Id: 00000000-0000-0000-0000-000000000001'
curl -s $BASE/wallet -H 'X-User-Id: 00000000-0000-0000-0000-000000000001'
# step 4 (user_id is required in the BODY for /stack):
curl -s -X POST $BASE/stack -H 'Content-Type: application/json' \
  -d '{"user_id": "00000000-0000-0000-0000-000000000001",
       "cart_total": "120.00", "domain": "hollisterco.com"}'
```

> **Status as of the deploy audit (2026-10-18):** `POST /rewards/{id}/redeem`
> and `GET /savings` are not implemented in the backend yet (decisions area —
> see docs/checklist/deploy.md). If they haven't landed by demo time, end the
> flow at step 4's "You save $X" moment and show the savings number in the
> dashboard UI instead of calling the endpoint live.

---

## 4. Fallback plans

### Postmark fails (send quota, approval mode, webhook flaky)

Use **instant mode** — identical extraction pipeline, no network email leg:

- In the merchant console, flip the mode toggle to **Instant** and send. The
  email is rendered and processed in-process; the toast/dashboard flow is
  unchanged. (This is the default console mode for a reason — consider
  demoing instant and *mentioning* the real-email path.)
- Or from the terminal:

```bash
curl -s -X POST $BASE/demo/inject -H 'Content-Type: application/json' \
  -d '{"eml_filename": "hollister_10_percent.eml", "force": true}'
```

(`"force": true` bypasses dedupe so the same email can be replayed endlessly.
Available seeds: `curl -s $BASE/demo/emails`.)

Narration line: "Normally this email travels through Postmark to our inbox —
we're injecting it directly so you don't watch mail servers for 10 seconds."

### Venue Wi-Fi fails (deployed backend unreachable)

Run everything on the laptop — this is why the rehearsal setup in section 1A
exists:

1. Start local backend (section 1A; have the image pre-built and the
   Postgres volume pre-seeded **before** demo day).
2. Point the extension/dashboard at `http://localhost:8000` (localhost CORS
   is already allowed in the backend).
3. Use **instant mode** for sending (real email needs internet anyway).
4. Warm: `python3 scripts/warm_models.py --http --base-url http://localhost:8000`.

Phone hotspot is plan C for reaching the deployed backend; local-everything
needs zero network.

### Backend process dies mid-demo

```bash
docker restart lapse            # local   (lapse-api on Linode)
# Render: Dashboard → lapse-api → Manual Deploy → "Restart service"
```

Models reload lazily; run the warmup command (section 2) while talking, first
request is ~5s otherwise.

### Pre-demo checklist (morning of)

- [ ] `curl $BASE/health` → 200
- [ ] Logs show `[warm] OK   server warm`
- [ ] `postmark_smoke.py --demo-inject` → `rewards_extracted=1`, <1s
- [ ] Console loads at `$BASE/demo/console`, templates render
- [ ] Extension toast fires on an instant send
- [ ] Laptop fallback: local image built, compose volume seeded, extension
      can switch base URL
- [ ] Do NOT push to main / trigger a Render deploy after this point
