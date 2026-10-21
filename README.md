<div align="center">
  <img src="frontend/extension/public/icon/icon.svg" alt="Lapse logo" width="200" />

# Lapse

**Every reward you've already earned — found, stacked, and spent before it lapses.**

<p>
  <img src="https://img.shields.io/badge/VISA%20REIMAGINE%20SHOPPING-WINNER%20(%245%2C000)-1434CB?style=for-the-badge&labelColor=555555" alt="Visa Reimagine Shopping — Winner ($5,000)" />
</p>
<p>
  <img src="https://img.shields.io/badge/SIDE%20SHIFT%20BEST%20STARTUP-3RD%20PLACE-FF5B1A?style=for-the-badge&labelColor=555555" alt="Side Shift Best Startup — 3rd Place" />
</p>
<p>
  <a href="https://dubhacks-2026.devpost.com/"><img src="https://img.shields.io/badge/DUBHACKS-2026-111111?style=for-the-badge&labelColor=555555" alt="DubHacks 2026" /></a>
  <a href="https://devpost.com/software/vouch-ld4voh"><img src="https://img.shields.io/badge/READ%20THE%20STORY-DEVPOST-6C5CE7?style=for-the-badge&labelColor=555555" alt="Read the story on Devpost" /></a>
</p>

**Awards:** 🏆 Visa "Reimagine Shopping" Main Track — **Winner ($5,000)** · 🥉 Side Shift Best Startup Track — **3rd Place**

Built at DubHacks 2026 by Aamir, Selina, Asya & Adem

</div>

---

## The Problem

We live in a **REWARDS world** — and most of it goes unused. Visa research across 22,000+ consumers found the average American is in **17.4 loyalty programs but actively uses only 8.8**, and just **1.14 for restaurants**. Antavo estimates Americans miss up to **$10 billion** in loyalty savings a year.

Those rewards aren't lost. They're buried in promo emails, forgotten at checkout, and expired by the weekend. If you're not maximizing, you're leaving money on the table.

Lapse closes that gap: forward reward emails to your private Lapse inbox, and at checkout a Chrome extension surfaces everything you've earned — stacked optimally with the best card in your wallet — before any of it lapses.

## Innovation

Agentic shopping is inevitable. The real question is what the agent is allowed to touch. Lapse is **the trusted layer** on Visa's rails: AI reads your inbox, deterministic math spends your money. AI is here to stay, as a partner and not something to fear — so we gave it exactly one job (reading) and kept every financial decision in auditable code.

- **Lapse Sense** — the extension recognizes known merchant sites and shows your matching rewards right away, before you've typed anything (`frontend/extension/src/entrypoints/content.ts`).
- **Use it before you lose it** — a reward expiring within 7 days is ranked ahead of a higher-value one that lasts at least 14 days longer; the second shows as *save for later*, and the stacker withholds it so it isn't burned early (`backend/decisions/use_first.py`).
- **Stacking as optimization, not heuristics** — checkout is a constraint-satisfaction problem, and we solve it as one (see Technical Execution).

## User Experience

Nobody wants another app to manage. Lapse meets you where you already are: your inbox and your checkout page.

- Forward a reward email once; it appears in your wallet in seconds via a live toast — no manual entry, ever.
- At checkout, the popup shows the optimal stack: final price, total savings, the recommended card, a copyable promo code, and a one-click **Mark used**.
- Search your rewards in plain words ("sushi", "streetwear") with **no LLM**: a nearest-match ranking scores match × value × urgency, helped by merchant tags. It returns the top 3 — 2 specific hits plus 1 under an "Also in …" divider — and every hit says *why* it matched.
- A React dashboard with savings and calendar views tracks what you've redeemed and what's about to expire; updates stream in over server-sent events (`/events`).
- A merchant console (`/demo/console`) shows a side-by-side preview of the raw email and the extracted reward, so anyone can verify the pipeline live.

## Technical Execution

Honest framing up front: **we trained our own reward classifier and built a custom extraction cascade and decision engine around pretrained models.**

| Layer | What runs |
|---|---|
| Intake | Postmark Inbound gives each user a private inbox (MailboxHash routing). Dedupe by Message-ID *and* normalized content hash. Presidio redacts cards, phones, emails, and street addresses before anything is stored (`backend/intake/`). |
| Classification | A SetFit classifier we trained ourselves (`scripts/train_classifier.py`), with a rule-based fallback so the pipeline never dies. |
| Extraction | A cascade: JSON-LD structured markup, then regex, then pretrained GLiNER NER — merged with per-field confidence; low-confidence rewards land in a needs-review queue instead of your wallet (`backend/extraction/pipeline.py`). |
| Merchant resolution | Exact domain → registrable domain → fuzzy name → MiniLM embeddings → inference from the domain (`backend/extraction/merchants.py`). |
| Stacking | Google OR-Tools **CP-SAT** enforces one promo code, min spend, exclusions, and non-combinable rules, and picks the best Visa card for the remainder — with a greedy fallback at 200 ms so `/stack` always answers (`backend/decisions/stacking/engine.py`). |
| App | FastAPI backend (Postgres + pgvector, or zero-setup in-memory mode). WXT/React Chrome MV3 extension. React/Vite dashboard, savings, and calendar. Live updates over SSE. |

```
maximize:   sum(savings_i · x_i) + card_cashback
subject to: one promo code · min spend · exclusions · non-combinable pairs
```

**494 backend tests pass** (`pytest backend/tests/`); 35 more are skipped without a live Postgres, downloaded model weights, or Chromium.

## Commerce Impact

Up to $10 billion a year is sitting on the table. Lapse moves it back into transactions — for everyone in the loop:

- **Shoppers** redeem what they already earned, automatically, at the moment it matters.
- **Merchants** finally see their promos convert instead of expiring unread.
- **The network** captures purchases that discounts were supposed to drive, with the best card chosen per cart.

Nothing about this is US-only or big-retailer-only: any merchant that can send an email is on-ramped, and unknown merchants are classified on the fly — no integration work required from anyone.

## Trust & Responsibility

- **AI only reads emails; every money decision is deterministic.** Ranking is arithmetic, stacking is a constraint solver — so a prompt injection hidden in a promo email has nothing to hijack.
- PII is redacted before storage; promo codes survive, card and phone numbers don't.
- Each user's inbox is private, and dedupe is per-user — your emails never touch another account.
- When extraction confidence is low, the reward goes to a needs-review queue rather than silently guessing.
- No scraping, no credential sharing: users forward only the emails they choose.

## Run it locally

Runs fully locally for **$0** — no accounts, no API keys.

```bash
# Backend (in-memory mode, no database needed) — must be on port 8000
pip install -r requirements.txt
PERK_ALLOW_DEMO_IDENTITY=true python3 -m uvicorn backend.app.main:app --port 8000
```

API docs land at http://127.0.0.1:8000/docs. For the full ML pipeline, also `pip install -r requirements-ml.txt`, then optionally train the classifier with `python3 scripts/train_classifier.py` (a keyword fallback covers you if you skip it). Send yourself demo reward emails — no real mail involved — from the console at http://127.0.0.1:8000/demo/console using **Instant** mode.

```bash
# Chrome extension
cd frontend/extension
npm install
VITE_API_BASE=http://127.0.0.1:8000 npx wxt build
```

Then open `chrome://extensions`, enable Developer mode, and **Load unpacked** from `frontend/extension/.output/chrome-mv3` (the backend must be running on port 8000).

```bash
# Web dashboard (optional)
cd frontend/web && npm install && npm run dev

# Tests
python3 -m pytest backend/tests/
```

Demo user: `00000000-0000-0000-0000-000000000001` (sent as the `X-User-Id` header). Seed data ships in `shared/seed/` — 33 rewards, 5 demo Visa cards, 5 memberships, 52 merchants, and 5 sample emails.

---

MIT License · DubHacks 2026
