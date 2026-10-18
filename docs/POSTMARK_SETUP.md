# Postmark inbound email setup (human checklist)

Goal: emails sent to a Lapse inbox address land on `POST https://<host>/inbound`
as JSON, where routing picks the user from the `MailboxHash` / recipient
address. Total time: ~10 minutes with the default inbound address.

## 1. Create the Postmark server

1. Sign up / log in at <https://account.postmarkapp.com>.
2. **Servers → Create Server**, name it `lapse` (any name works).
3. A server has message streams. You need two:
   - **Inbound** stream (exists by default) — receives the reward emails.
   - **Transactional** stream (default) — used by the demo console to *send*
     test emails. Grab the **Server API Token** from the server's
     **API Tokens** tab → this is `POSTMARK_SERVER_TOKEN`.

> New Postmark accounts are in "approval mode": you can only *send* to
> addresses on your own domain until approved. **Inbound is not restricted**,
> so the webhook demo works immediately.

## 2. Use the default inbound address first (no DNS needed)

1. Open the server → **Message Streams → Default Inbound Stream → Settings**.
2. Copy the **server's inbound email address** — it looks like
   `a1b2c3d4e5f6...@inbound.postmarkapp.com`. This is
   `POSTMARK_INBOUND_ADDRESS`.
3. **Per-user routing with MailboxHash:** Postmark supports plus-addressing on
   the inbound address. Mail sent to
   `a1b2c3d4...+aamir@inbound.postmarkapp.com` arrives with
   `"MailboxHash": "aamir"` in the JSON payload, which
   `backend/intake/routing.py` maps to a user (`aamir` and `demo` both map to
   the demo user `00000000-0000-0000-0000-000000000001`).
4. Hand out addresses like `<inbound-address-local-part>+<username>@inbound.postmarkapp.com`
   when signing up for store loyalty programs.

## 3. Point the inbound webhook at the API

1. In the same **Inbound stream → Settings** page, set **Webhook** to:

   ```
   https://<your-host>/inbound
   ```

   e.g. `https://lapse-api.onrender.com/inbound` or `https://api.lapse.app/inbound`.
   It must be **HTTPS with a valid cert** (Render gives you this for free;
   on Linode use Caddy/nginx — see docs/DEPLOY.md).
2. Leave "Include raw email content in JSON payload" off (not needed).
3. Click **Check** next to the webhook URL — Postmark sends a test POST and
   shows the response code. A `200` means you're live. (Postmark's test
   payload is a generic email; a `422` from FastAPI validation can appear with
   very old test payloads — a real email will still process fine, verify with
   step 4.)

## 4. Send a test

Three ways, in increasing realism:

1. **No email at all** — replay a stored payload against the deployed host:

   ```bash
   python3 scripts/postmark_smoke.py --base-url https://<your-host> --mailbox-hash demo
   ```

2. **Real email, default address:** from any mail client send a message to
   `<inbound-address>+demo@inbound.postmarkapp.com` with subject
   `Your 10% off voucher` and body
   `Use code SAVE10 for 10% off your next purchase. Expires October 31, 2026.`
3. **End-to-end:** forward a real store reward email to that same address.

Then check the extracted reward:

```bash
curl -s https://<your-host>/sync -H 'X-User-Id: 00000000-0000-0000-0000-000000000001'
```

## 5. (Optional, only if done by 3 AM) custom domain `lapse.app`

Skippable for the demo — the default address works fine. For pretty addresses
like `aamir@lapse.app`:

1. Postmark server → **Inbound stream → Settings → Inbound domain**: enter
   `lapse.app`.
2. At your DNS provider add an **MX record**:

   | Host | Type | Priority | Value |
   |---|---|---|---|
   | `lapse.app` (or `@`) | MX | 10 | `inbound.postmarkapp.com` |

   (If `lapse.app` already receives normal mail, use a subdomain instead, e.g.
   `in.lapse.app`, and hand out `aamir@in.lapse.app`.)
3. Wait for DNS propagation (minutes to an hour). Verify:

   ```bash
   dig +short MX lapse.app   # expect: 10 inbound.postmarkapp.com.
   ```

4. Mail to `anything@lapse.app` now hits the same webhook;
   `backend/intake/routing.py` routes by the local part (`aamir@lapse.app` →
   user `aamir`), with `+hash` still supported.

## 6. When something fails: read the inbound activity log

Postmark keeps a full log of every inbound message and webhook attempt:

1. Server → **Message Streams → Inbound → Activity**.
2. Click a message. You get:
   - the parsed JSON payload (exactly what was/will be POSTed to you),
   - **Webhook delivery attempts** with timestamp, your server's HTTP status
     code and response body, and retry schedule.
3. Common failures and fixes:
   - **No message in Activity at all** → the email never reached Postmark:
     wrong inbound address, or (custom domain) MX record missing/not
     propagated.
   - **Message present, webhook `error` / timeout** → your host is down or
     unreachable: check `curl https://<host>/health`, container logs
     (`docker logs lapse-api`), and that the URL is HTTPS with a valid cert.
   - **Webhook `422`** → payload failed FastAPI validation; compare the logged
     JSON against `InboundEmail` in `backend/app/schemas.py`.
   - **Webhook `500`** → check app logs; the extraction stack traces there.
   - Postmark **retries failed webhooks** (10 attempts over ~8 hours) and you
     can click **"Retry"** on a message manually after fixing the server.
4. Inbound messages can also be inspected via the API:
   `GET https://api.postmarkapp.com/messages/inbound` with header
   `X-Postmark-Server-Token: $POSTMARK_SERVER_TOKEN`.

## Env var recap (set these on the host — see docs/DEPLOY.md)

| Var | Value |
|---|---|
| `POSTMARK_SERVER_TOKEN` | Server → API Tokens |
| `POSTMARK_INBOUND_ADDRESS` | `<hash>@inbound.postmarkapp.com` (step 2) |
| `DEMO_FROM_EMAIL` | a Sender Signature you verified in Postmark (for outbound demo emails) |
