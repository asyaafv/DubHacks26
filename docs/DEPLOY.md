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

| Var | Required | Notes |
|---|---|---|
| `PORT` | no (default 8000) | Render/Heroku-style; uvicorn binds to it |
| `DATABASE_URL` | no | Postgres DSN. Without it the app runs fully in-memory (fine for the demo) |
| `POSTMARK_SERVER_TOKEN` | for sending | Postmark server API token (demo console / outbound) |
| `POSTMARK_INBOUND_ADDRESS` | for inbound | e.g. `abc123...@inbound.postmarkapp.com` (see docs/POSTMARK_SETUP.md) |
| `DEMO_FROM_EMAIL` | for sending | Verified sender signature in Postmark |

CORS: `chrome-extension://*` and localhost origins are already allowed in code
(`backend/app/main.py`) — nothing to configure.

## Local build & smoke test

```bash
docker build -t lapse-api .          # ~15-25 min first time (trains SetFit, downloads weights)
docker run -d --name lapse -p 8000:8000 lapse-api

curl -s http://localhost:8000/health | python3 -m json.tool

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
   `DATABASE_URL` can be left unset for the demo.
4. First deploy takes 15-25 min (model training + downloads happen in the
   image build). Watch for `[warm] done` in the build logs.
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
  -e POSTMARK_SERVER_TOKEN='<your-postmark-server-token>' \
  -e POSTMARK_INBOUND_ADDRESS='<hash>@inbound.postmarkapp.com' \
  -e DEMO_FROM_EMAIL='demo@yourdomain.com' \
  # -e DATABASE_URL='postgresql://user:pass@host:5432/lapse' \  # optional
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
