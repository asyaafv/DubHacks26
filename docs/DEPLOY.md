# Deploying the Lapse API

One Docker image runs everything: FastAPI (`backend.app.main:app`) plus the
full ML extraction stack (CPU torch, SetFit classifier trained at build time,
GLiNER2 `fastino/gliner2-base-v1`, MiniLM embeddings, presidio + spaCy
`en_core_web_sm`). All model weights are baked into the image, so cold start
is seconds and no HuggingFace access is needed at runtime.

## Measured footprint (local build, 2026-10-18)

| Metric | Measured |
|---|---|
| Image size | 3.91GB (torch CPU + GLiNER2 ~834MB + MiniLM + SetFit + spaCy baked in) |
| Cold start (docker run → /health 200) | 0.85s (models load lazily) |
| RAM at idle | ~37MB |
| RAM after first email (SetFit classify, JSON-LD path) | ~460MB |
| RAM after one GLiNER extraction | ~1.45GB (steady state) |
| First extraction incl. lazy model load | ~5.5s (from baked cache — verified working with `--network none`) |
| Warm extraction | ~0.4s per email |

**Sizing rule: 512MB is not enough, 1GB will OOM on the GLiNER path
(~1.45GB working set). 2GB is the floor; 4GB is comfortable.**

## Environment variables

Every variable the backend reads (`grep -rn "os.environ\|getenv" backend/`):

| Var | Required | Notes |
|---|---|---|
| `PORT` | no (default 8000) | Render/Heroku-style; uvicorn binds to it |
| `DATABASE_URL` | no* | Postgres DSN. Without it intake/extraction/`/inbound`/`/demo/*`/`/events` run in-memory, but **`/wallet` and `/sync` return 503** (wallet has no in-memory mode). Set it (with the compose Postgres) if the demo shows the wallet. |
| `PERK_ENCRYPTION_KEY` | **yes, if `DATABASE_URL` is set** | ≥32 chars (`openssl rand -hex 32`). The app **refuses to start** without it when `DATABASE_URL` is set (pgcrypto key for reward codes). |
| `PERK_ALLOW_DEMO_IDENTITY` | no | `true` → requests without `X-User-Id` resolve to the demo user on `/wallet` (otherwise 401). Convenient for curl demos; the extension sends the header anyway. |
| `WARM_MODELS` | no | `1` → at container start, a background helper replays one plaintext seed email through `/demo/inject` (throwaway user) once `/health` is up, loading SetFit + GLiNER2 + MiniLM into the serving process. First demo email ~0.4s instead of ~5s; RSS goes to ~1.4GB immediately. |
| `POSTMARK_SERVER_TOKEN` | for sending | Postmark server API token (demo console / outbound) |
| `POSTMARK_INBOUND_ADDRESS` | for inbound | e.g. `abc123...@inbound.postmarkapp.com` (see docs/POSTMARK_SETUP.md) |
| `DEMO_FROM_EMAIL` | for sending | Verified sender signature in Postmark |
| `CORS_EXTRA_ORIGINS` | no | Comma-separated **exact** extra origins (`scheme://host[:port]`) allowed by CORS, e.g. `https://dash.172-234-249-8.sslip.io`. Set it when a deployed dashboard is served from a different origin than the API. |
| `CORS_EXTRA_ORIGIN_REGEX` | no | One extra regex OR'd into the allowed-origin pattern, for origins with variable parts, e.g. `https://([a-z0-9-]+\.)*172-234-249-8\.sslip\.io`. |

(Test-only, never set in deploys: `TEST_DATABASE_URL`, `NODE_BINARY`,
`PLAYWRIGHT_NODE_MODULE`.)

CORS: `chrome-extension://*` and localhost origins (any port) are always
allowed in code (`backend/app/main.py`) — nothing to configure for the
extension or local dev. For a deployed dashboard on its own origin, set
`CORS_EXTRA_ORIGINS` (and/or `CORS_EXTRA_ORIGIN_REGEX`) on the API container,
e.g. for the Linode deploy serving the dashboard at
`https://dash.172-234-249-8.sslip.io`:

```bash
-e CORS_EXTRA_ORIGINS='https://dash.172-234-249-8.sslip.io'
```

## Local build & smoke test

```bash
docker build -t lapse-api .          # ~15-25 min first time (trains SetFit, downloads weights)
docker run -d --name lapse -p 8000:8000 -e WARM_MODELS=1 lapse-api

curl -s http://localhost:8000/health | python3 -m json.tool
docker logs lapse 2>&1 | grep '\[warm\]'   # wait for "[warm] OK server warm"

# Webhook smoke test without real email (stdlib-only script):
python3 scripts/postmark_smoke.py --base-url http://localhost:8000

# Or replay a stored .eml server-side:
curl -s -X POST http://localhost:8000/demo/inject \
  -H 'Content-Type: application/json' \
  -d '{"eml_filename": "hollister_10_percent.eml"}' | python3 -m json.tool
```

---

## Option A — Render (fastest to get HTTPS, ~$25/mo Standard)

Render's **free and Starter (512MB) plans will be OOM-killed** by
torch + GLiNER. Use **Standard (2GB RAM)** — the cheapest plan that fits.
Render terminates TLS for you, so the Postmark webhook URL works immediately.

1. Push this repo (with `render.yaml` at the root) to GitHub.
2. Render Dashboard → **New → Blueprint** → select the repo. Render reads
   `render.yaml` and creates the `lapse-api` web service on the Docker runtime.
3. When prompted, fill the secret env vars (`POSTMARK_SERVER_TOKEN`, etc.).
   `DATABASE_URL` can be left unset if the demo skips `/wallet` + `/sync`;
   if you set it, `PERK_ENCRYPTION_KEY` (≥32 chars) is mandatory.
   `WARM_MODELS=1` and `PERK_ALLOW_DEMO_IDENTITY=true` are preset in
   `render.yaml`.
4. First deploy takes 15-25 min (model training + downloads happen in the
   image build). Watch for `[warm] done` in the build logs, then
   `[warm] OK   server warm` in the runtime logs (startup warmup).
5. Your base URL is `https://lapse-api.onrender.com` (or similar). Verify:

```bash
curl -s https://lapse-api.onrender.com/health
python3 scripts/postmark_smoke.py --base-url https://lapse-api.onrender.com
```

6. Point the Postmark inbound webhook at `https://<your-host>/inbound`
   (docs/POSTMARK_SETUP.md).

Tip: if the Render build ever times out, build the image locally / in CI, push
to a registry, and use Render's "Deploy an existing image" flow instead.

---

## Option B — Linode/Akamai shared 4GB (~$24/mo, more headroom + full control)

A Linode Shared 4GB (2 vCPU) runs the container with room to spare. You bring
your own TLS — use Caddy (2 lines of config, automatic Let's Encrypt) so
Postmark's HTTPS webhook works.

### 1. Provision

- Create a **Linode 4GB** (Shared CPU) with Ubuntu 24.04 LTS.
- Point a DNS A record at it, e.g. `api.lapse.app → <linode-ip>`
  (any hostname works; Postmark just needs valid HTTPS).

### 2. Install Docker + Caddy

```bash
ssh root@<linode-ip>

# Docker
curl -fsSL https://get.docker.com | sh

# Caddy (automatic HTTPS)
apt-get update && apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
apt-get update && apt-get install -y caddy
```

### 3. Build (or pull) and run the API container

Either build on the box (needs ~10GB free disk):

```bash
git clone https://github.com/asyaafv/DubHacks26.git && cd DubHacks26
docker build -t lapse-api .
```

…or build locally, `docker push` to Docker Hub/GHCR, and `docker pull` here.

Run with a restart policy and the env vars:

```bash
docker run -d \
  --name lapse-api \
  --restart unless-stopped \
  -p 127.0.0.1:8000:8000 \
  -e PORT=8000 \
  -e WARM_MODELS=1 \
  -e PERK_ALLOW_DEMO_IDENTITY=true \
  -e POSTMARK_SERVER_TOKEN='<your-postmark-server-token>' \
  -e POSTMARK_INBOUND_ADDRESS='<hash>@inbound.postmarkapp.com' \
  -e DEMO_FROM_EMAIL='demo@yourdomain.com' \
  # If the dashboard is served from its own origin (e.g. dash.<ip>.sslip.io):
  # -e CORS_EXTRA_ORIGINS='https://dash.172-234-249-8.sslip.io' \
  # Optional Postgres (needed for /wallet and /sync; see env var table):
  # -e DATABASE_URL='postgresql://user:pass@host:5432/lapse' \
  # -e PERK_ENCRYPTION_KEY='<openssl rand -hex 32>' \
  lapse-api
```

(`-p 127.0.0.1:8000:8000` keeps the plain-HTTP port off the public internet;
only Caddy can reach it.)

### 4. HTTPS with Caddy

```bash
cat > /etc/caddy/Caddyfile <<'EOF'
api.lapse.app {
    reverse_proxy 127.0.0.1:8000
}
EOF
systemctl reload caddy
```

That's it — Caddy obtains and renews the Let's Encrypt cert automatically.

<details>
<summary>nginx alternative (if you prefer it)</summary>

```bash
apt-get install -y nginx certbot python3-certbot-nginx
cat > /etc/nginx/sites-available/lapse <<'EOF'
server {
    server_name api.lapse.app;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;   # first GLiNER call can be slow
    }
}
EOF
ln -s /etc/nginx/sites-available/lapse /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d api.lapse.app
```
</details>

### 5. Verify

```bash
curl -s https://api.lapse.app/health
python3 scripts/postmark_smoke.py --base-url https://api.lapse.app
```

Then set the Postmark inbound webhook to `https://api.lapse.app/inbound`
(docs/POSTMARK_SETUP.md).

### Ops crib sheet

```bash
docker logs -f lapse-api          # tail app logs
docker restart lapse-api          # restart (models reload lazily, ~10-30s first request)
docker stats lapse-api --no-stream # live RAM/CPU
docker pull <registry>/lapse-api && docker rm -f lapse-api && <docker run ...>  # redeploy
```

---

## Recommendation

- **Tonight's demo, least moving parts:** Render Standard (2GB, ~$25/mo) via
  `render.yaml` — HTTPS and deploys are fully managed.
- **Cheapest workable with headroom:** Linode Shared 4GB (~$24/mo) + Caddy —
  same price as Render Standard but double the RAM and full box access; a few
  more manual steps (above, copy-pasteable).
- **Do not attempt** 512MB plans (Render free/Starter, small Fly VMs): torch +
  GLiNER working set exceeds them and the OOM killer will take the service
  down mid-demo.
