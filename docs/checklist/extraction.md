# Audit checklist — extraction

Audited on branch `cursor/audit-extraction-544d` (main + PR #22 merge) with the FULL ML stack
installed: torch 2.9.1+cpu, setfit 1.2.0, gliner2 2.1.0, sentence-transformers 6.1.0, extruct,
dateparser, price-parser, tldextract, rapidfuzz. SetFit trained via `python scripts/train_classifier.py`
(73 examples, 100% holdout accuracy on 15-sample test split, 10 ms/email). `pipeline.FALLBACKS_ACTIVE == []`
(every real module loaded; no built-in fallbacks).

Evidence harness: `python -m backend.tests.extraction.audit_run` — runs all 5 seed emails,
all 6 demo console templates (rendered via `backend/intake/console/emails.py`, read-only), and
5 extra synthetic emails (Sephora points, Starbucks BOGO, Old Navy $10-off-$50, non-reward
newsletter, shipping notification) through `run_pipeline` twice (cold, then warm). Full JSON
written to `/tmp/audit_extraction_results.json`.

## Feature checklist

| Feature | Status | Evidence |
| --- | --- | --- |
| SetFit classifies reward/receipt/promo/other | Works | `scripts/train_classifier.py`: 100% holdout acc; harness: amazon_receipt→receipt 0.80, shipping→receipt 0.69, chipotle→reward 0.81 |
| JSON-LD extraction (DiscountOffer) via extruct | Works | hollister/nike/target seeds + hollister_10/aero_50/target_5off console all `source=email_jsonld`, conf 0.99, exact value/code/min_spend/expiry |
| GLiNER2 NER (fastino/gliner2-base-v1) | Works | starbucks_bogo, oldnavy_10_off_50, sephora_points all `source=gliner` with correct fields; warmup 17.6 s cold-download |
| Dates parsed relative to email Date | Works | every console `expiry_days` offset lands on the exact calendar day (e.g. ulta +14 → 2026-11-01T23:59:59) |
| Prices parsed with currency | Works | min_spend $10/$25/$50 and $5/$10 amount_off all exact, currency USD |
| Regex fallback | Works | chipotle + tacobell free_item rewards carried entirely by `source=regex` (code, min_spend, expiry, stackable) |
| Per-field confidence | Works | e.g. chipotle: value 0.70, code 0.9997, min_spend 0.998, merchant 0.99 → overall 0.807 |
| `needs_review` for low confidence | Works (see note) | pacsun_bogo & aero_50 correctly flagged needs_review (unknown merchant, overall 0.62/0.72). Note: pipeline threshold is 0.6; extraction README says 0.7 — doc drift, behavior is the 0.6 in pipeline.py |
| `POST /classify-merchant` known + unknown domains | Works | wired in `backend/app/main.py:692` and `backend/extraction/router.py`; domain hit → conf 0.99 w/ merchant_id, unknown → inferred name, conf 0.1, `is_new=true` |
| Classifier rejects non-rewards | Partial | receipts/shipping rejected outright (pipeline skips extraction). Low-confidence non-rewards (newsletter: raw SetFit = promo 0.42) are deliberately flipped to "reward" by `classify.py`'s <0.5 lean; extraction then yields 0 rewards, so net behavior is correct but the logged label is misleading |
| Points rewards (Ulta console template, Sephora) | Broken → FIXED | before: `console/ulta_points` produced 0 rewards (GLiNER's "500 bonus points" unparseable; junk "2026" expiry outranked regex's "November 1"). After fix: points 500, expires 2026-11-01, active, conf 0.713 |

Counts: 9 Works, 1 Partial, 1 Broken (fixed in this PR), 0 Missing.

## Per-case results (warm pass, after fixes)

| Case | Class (conf) | Kind | Value | Code | Min | Expiry ok | Merchant | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| seed/amazon_receipt | receipt (0.80) | — skipped | | | | | | |
| seed/chipotle_plaintext | reward (0.81) | free_item | 1 | FREEGUAC | 10 | ✓ Oct 31 | Chipotle | active |
| seed/hollister_10_percent | reward (0.82) | percent_off | 10 | HCOFALL10 | 50 | ✓ Oct 20 | Hollister | active |
| seed/nike_promo | reward (0.46)* | percent_off | 20 | NIKE20FALL | 100 | ✓ Oct 19 | Nike | active |
| seed/target_jsonld_offer | reward (0.83) | amount_off | 5 | TARGET5 | 25 | ✓ Oct 19 | Target | active |
| console/hollister_10 | reward (0.84) | percent_off | 10 | HCOFALL10 | 50 | ✓ +3d | Hollister | active |
| console/tacobell_crunchwrap | reward (0.85) | free_item | 1 | CRUNCHTIME | — | ✓ +7d | Taco Bell | active |
| console/ulta_points | reward (0.75) | points | 500 | — | — | ✓ +14d | Ulta Beauty | active |
| console/pacsun_bogo | reward (0.85) | bogo | 1 | PACBOGO | — | ✓ +5d | "BOGO" (!) | needs_review |
| console/aero_50 | reward (0.82) | percent_off | 50 | AERO50 | — | ✓ +4d | Aéropostale (no id) | needs_review |
| console/target_5off | reward (0.86) | amount_off | 5 | CIRCLE5 | 25 | ✓ +10d | Target | active |
| custom/sephora_points | reward (0.66) | points | 250 | — | — | ✓ +30d | Sephora | active |
| custom/starbucks_bogo | reward (0.85) | bogo | 1 | SIPSHARE | — | ✓ +3d | Starbucks | active |
| custom/oldnavy_10_off_50 | reward (0.84) | amount_off | 10 | NAVY10 | 50 | ✓ +7d | Old Navy | active |
| custom/newsletter_non_reward | reward (0.41)* | — 0 rewards | | | | | | |
| custom/shipping_notification | receipt (0.69) | — skipped | | | | | | |

\* raw SetFit label was promo; `classify.py` leans sub-0.5 predictions to "reward" by design so
extraction still runs. Extraction produced 0 rewards for the newsletter, so nothing bogus persists.

## Latency (per stage, ms; 16-case cold pass then warm pass, CPU-only)

| Stage | Cold max (first call) | Warm min/med/max |
| --- | --- | --- |
| clean | 0.5 | 0.0 / 0.1 / 0.4 |
| classify (SetFit) | 3817 (model load) | 12.5 / 16.3 / 26.4 |
| markup (extruct path) | 0.4 | 0.0 / 0.0 / 0.5 |
| gliner (GLiNER2) | 3610 (model load; 17.6 s if downloading) | 148 / 155 / 237 |
| regex | 0.2 | 0.1 / 0.1 / 0.2 |
| normalize (dateparser) | 957 (first parse) | 0.0 / 2.6 / 14.9 |
| merchant (MiniLM embed path) | 2181 (model load) | 0.0 / 0.1 / 6.5 |
| **total** | **4604 (first reward email)** | **13.8 / 165 / 274** |

Warm totals split by path: JSON-LD-complete emails 14–31 ms; GLiNER-path emails 150–274 ms.
First email in a fresh process pays ~4–5 s (SetFit + GLiNER2 loads); `scripts/warm_models.py`
at container start eliminates this — keep it in the Docker start path (it is already in the Dockerfile).

## Fixes made (this PR)

1. `backend/extraction/normalize.py` — points pattern now accepts qualifier words
   ("500 **bonus** points", "250 **extra** points"). Without this, the Ulta console template —
   a P1 demo path — produced **zero** rewards.
2. `backend/extraction/normalize.py` — `merge_candidates` skips bare-4-digit-year
   expiry/starts candidates (GLiNER sometimes emits "2026", which out-prioritized the regex
   extractor's correct "November 1" and made the reward expire "today").
3. `backend/tests/extraction/test_normalize.py` — 3 regression tests for the above.

Tests: 234 passed (231 pre-existing + 3 new), 0 failed, full ML stack active.

## Needs fix elsewhere

- **P1 — `shared/seed/seed_merchants.json`: add PacSun and Aéropostale.** Both are demo console
  templates and both appear in the decisions demo-redemptions list, but neither is in the seed
  merchants file. Result: `console/pacsun_bogo` lands with merchant_name "BOGO" (GLiNER mislabel,
  nothing to correct it) and `console/aero_50` with `merchant_id=null`; both get `needs_review`
  instead of `active`. Suggested rows: `{"name": "PacSun", "domain": "pacsun.com", "mcc": "5651", ...}`,
  `{"name": "Aéropostale", "domain": "aeropostale.com", "mcc": "5651", ...}` with fresh UUIDs.
- **P2 — doc drift:** `backend/extraction/README.md` says needs_review threshold 0.7;
  `pipeline.py` implements 0.6 ("per the task spec"). Align the README (or the spec) — do not
  change the runtime threshold this close to demo, since 0.7 would flip chipotle/tacobell
  (overall 0.807) safe, but anything GLiNER-sourced near 0.6–0.7 would start flagging.

## FLAG (do not change): free_item value convention

- `backend/extraction/normalize.py` emits `value=1` for `free_item` (and `bogo`).
- `shared/seed/seed_rewards.json` seeds free_item rewards with `value=0.00` (Chipotle FREEGUAC,
  McDonald's FREEFRIES).
- `backend/decisions/README.md` says: on redeem without a cart, "use the reward's face value" as
  the saved amount — so an *extracted* free-item reward would record $1.00 saved while a *seeded*
  one records $0.00 for the same kind of reward. (The ranking guidance separately hardcodes
  `value_usd = 5.0` for free items/BOGO/points, ignoring `value` entirely.)
- Inconsistent but intentional-looking on both sides; left unchanged per audit instructions.
  Recommendation for later: pick one convention (0 seems safer — "face value" of a free item is
  not $1) and have savings/ranking special-case `free_item`/`bogo` explicitly.
