# Person 3 verification and demo handoff

## Publication candidate — October 18, 2026

This section supersedes earlier assembly/runtime results below. The publishable
stack begins at latest fetched main **`b263e935fb22276a0d81f094efffdec4481606b2`**,
which already contains foundation PR #12 and delivery PR #15. Those implementation
commits are not cherry-picked again. Only missing files/configuration changes are
published; no duplicate component or historical rename commits are added.
Latest main also includes intake/redaction/deployment/console PRs #17–21; those
are preserved. Savings commit `5279322` regenerates OpenAPI against that real
application, including its new intake models and console routes.
All work uses new isolated `lapse-review-*` worktrees; owner branches/checkouts and
the original `lapse-e2e` remain untouched.

GitHub initially rejected publication under GH007 (protected private author
email). Only new, unpublished review commit metadata was rewritten to the
account's GitHub noreply address. Every rewritten commit's tree was verified
identical to its pre-rewrite tree. Original owner branches, commit identities,
remote history and account privacy settings were not changed. Revisions below
are the public identities, with the combined suite rerun before publication.

Merge order (each PR is based on the preceding branch; after its predecessor is
merged, retarget the next PR to `main` before merging):

1. [PR #28 — lookup/storage](https://github.com/asyaafv/DubHacks26/pull/28),
   `codex/person3-lookup-review`, tested head
   **`8532b2157be95a391d305cd0a6348756916c746e`**: lookup plus its separate storage
   additions, current lookup LAPSE names, and declared MiniLM dependency.
2. [PR #29 — stacking](https://github.com/asyaafv/DubHacks26/pull/29),
   `codex/person3-stacking-review`, tested head
   **`1d4e7dadf7b97ec1cc3b22afe36f9ff7cf1ff5b0`**: stacking plus core OR-Tools
   dependency. Based on the lookup head above.
3. [PR #30 — savings](https://github.com/asyaafv/DubHacks26/pull/30),
   `codex/person3-savings-review`, tested head
   **`52793224260b9b9c7696cb12a5104e9b2a852425`**: savings implementation from
   `codex/savings-tracking` (`704c145`), migration/contracts/startup history.
   Contract-doc conflict resolved preserving main and savings semantics.
4. [PR #31 — E2E/LAPSE](https://github.com/asyaafv/DubHacks26/pull/31),
   `codex/person3-e2e-review`, combined tested implementation
   **`47e74d8a884e6ca1a7ce37b1a1bc0b503d33905d`**: E2E harness/tests/report and
   remaining LAPSE config/documentation updates. Subsequent report commits change
   documentation only; this is the exact code and manifest snapshot tested.

Person 3 feature implementations and all existing test assertions match the
previously verified `8265c00` assembly. The new manifests and latest upstream
intake/console contract generation are included. `backend/extraction/` and
`backend/intake/` match latest main exactly; main.py differs from main only by
the existing savings additions. The strict contract
test remains unchanged. `python scripts/gen_contracts.py` produces zero diff.

### Clean dependency verification

Created a new environment at `/private/tmp/lapse-publish-venv` using downloaded
CPython **3.11.14**, without system site packages. No owner's venv was modified.
Added `ortools==9.15.6755` to core `requirements.txt`; activated
`sentence-transformers>=3,<4` in optional `requirements-ml.txt`. Existing core and
extraction constraints were preserved. The latter intersects merchants' existing
`sentence-transformers>=2.3.0`; the tested resolved version is 3.4.1.

Resolved both root manifests together with **every** extraction manifest,
including `gliner2[local]==2.1.0`, using `uv pip compile` on fresh Python 3.11.
Resolution succeeded, and was repeated successfully with all new intake manifests
(including Presidio 2.2.364 and spaCy >=3.7,<4). Optional Presidio/spaCy models are
not installed or exercised; upstream intake uses its regex fallback here.
Installed core, ML and all extraction manifests except
`gliner_extract.txt`, constrained to that full resolution. This deliberately keeps
GLiNER2/model provisioning separate from the Person 3 verification; it is not
reported as installed or working. `uv pip check` reports **all 102 installed
packages compatible**. Real tests then exercise the actual solver and encoder.

Relevant resolved versions: OR-Tools 9.15.6755, sentence-transformers 3.4.1,
transformers 4.57.6, torch 2.14.1, numpy 2.4.6, protobuf 6.33.6, Pydantic 2.14.1,
FastAPI 0.119.1, SetFit 1.2.0, asyncpg 0.32.0. These satisfy the existing constraints;
no protobuf/transformers/Pydantic constraint was relaxed. A successful resolver is
not a claim that GLiNER2 model loading was exercised.

### Latest results and reproduction

- Final combined candidate: **116 passed, 0 failed, 0 skipped**, 16.32 seconds
  on the final latest-main/public-identity rerun, five deprecation
  warnings. Uses native Postgres 17.11, real pgvector/pgcrypto, actual CP-SAT,
  pinned cached offline MiniLM, TCP SSE and real Chromium. Includes actual server
  restart, repeatable $103.51 history and unchanged strict contract regeneration.
- Separately, unchanged real application contract suite: **42 passed**, five
  warnings, 3.50 seconds. Latest main's intake service installs its own GLiNER2
  unavailable guard and uses regex/markup fallback; these passes verify that
  upstream behavior, not actual GLiNER2 extraction. We introduced no mocks, stub
  routes, guards or assertion bypasses. Direct real `gliner_extract.warmup()`
  still fails with `ExtractionUnavailable` from `ModuleNotFoundError: gliner2`.
  The two earlier inbound failures are therefore superseded by upstream fallback
  behavior, not a repaired ML dependency. GLiNER2 model loading and complete
  extraction/extension flow remain explicitly unverified.
- Redemption JavaScript helper: **2 passed**. `git diff --check` passes.
- Each feature PR head was also tested independently in the fresh environment:
  lookup plus storage **30 passed** (4.98s), stacking plus storage **69 passed**
  (1.60s), savings plus storage **23 passed** (2.17s). The latter includes real
  delivery streaming. These overlapping suites are not additional unique tests.
- Raw run evidence: `/private/tmp/lapse-person3-latest-tests.txt`,
  `/private/tmp/lapse-person3-latest-inbound.txt`,
  `/private/tmp/lapse-person3-latest-resolve.log`,
  `/private/tmp/lapse-person3-latest-all-resolved.txt`,
  `/private/tmp/lapse-person3-fresh-install.log`,
  `/private/tmp/lapse-person3-latest-gliner.txt` (expected direct dependency failure).

Run the following from `lapse-review-e2e` after starting the dedicated disposable
Postgres cluster as documented below. The existing model cache/browser paths in
the earlier commands apply. These commands do not require any existing key to be
changed. Tests use fresh schemas and disposable in-memory keys.

```sh
export UV_CACHE_DIR=/private/tmp/lapse-publish-uv-cache
uv venv --python 3.11 /private/tmp/lapse-publish-venv
uv pip compile --python /private/tmp/lapse-publish-venv/bin/python \
  requirements.txt requirements-ml.txt backend/extraction/requirements/*.txt backend/intake/requirements/*.txt \
  -o /private/tmp/lapse-person3-all-resolved.txt
uv pip install --python /private/tmp/lapse-publish-venv/bin/python \
  -r requirements.txt -r requirements-ml.txt \
  -r backend/extraction/requirements/classify.txt \
  -r backend/extraction/requirements/clean.txt \
  -r backend/extraction/requirements/markup.txt \
  -r backend/extraction/requirements/merchants.txt \
  -r backend/extraction/requirements/pipeline.txt \
  -r backend/extraction/requirements/regex_normalize.txt \
  --constraint /private/tmp/lapse-person3-all-resolved.txt
uv pip check --python /private/tmp/lapse-publish-venv/bin/python
export PYTHON=/private/tmp/lapse-publish-venv/bin/python
sh backend/tests/e2e/run.sh
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "$PYTHON" -m backend.tests.e2e.legacy_contracts
# Current upstream intake fallback: 42 contracts pass, but GLiNER2 is not verified.
"$PYTHON" -c 'from backend.extraction.gliner_extract import warmup; warmup()'
# Direct GLiNER2 probe above exits 1: package absent.
"$PYTHON" scripts/gen_contracts.py
node --test frontend/api/redemptions.test.mjs
git diff --check
```

Remaining blockers are scoped to integration: provision GLiNER2 and its model,
replace production lookup/stack/delivery stubs, bridge actual extraction's
in-memory writes to the transactional Postgres boundary, backfill seed embeddings,
and connect the extension/scheduler. The four PRs contain the missing dependency
manifest changes and preserve current encryption-key values; no dependency fix is
left for someone to copy from an unpushed working tree. Shared Hollister seeds
remain unchanged; test-only rate/remainder corrections are explicitly identified.

## Earlier verification history

Verified October 17, 2026, America/Los_Angeles. All new work is in
`/Users/asuya/Documents/ChatGPT/DUBHACKS/lapse-e2e`, branch `codex/person3-e2e`.
This is a Person 3 boundary suite, not complete email-to-extension product E2E.
No dependencies were installed, existing keys rotated, owner checkouts edited,
remote branches merged/pushed, or deployments performed.

## Assembly and ownership

Inspected local tips: foundation `440bada`, stacking `6155d8c`, lookup `b43f014`,
delivery `e33c019`, savings `704c145`. Created this worktree from foundation.
Applied feature commits `a5c0e52`, `535dc80`, `8b8d661`, `d66c246`, `704c145`
once each. Lookup storage `535dc80` remains a separate commit; its alternative
patch was not reapplied. Preserved component LAPSE configuration and handoff
updates from the final lookup/delivery tips. Common branding/configuration was
already inherited from foundation. Subsequently fetched origin and merged the
latest `origin/main`; see the exact tested revisions below. No clone was used.

## Post-main merge verification

Fetched `origin/main` at **`8b4830700f6b6d7a63473343d63b6d82034af355`** and
merged locally as **`a28650c8622988c2f42051158ed31ffaef8e663e`**. Its parents are
`b8d60be6f4974d607549c4f6dc01ed21befe271c` (the prior E2E branch) and that fetched
main commit. Git's automatic merge completed without conflicts. `origin/main` is
now an ancestor. No remote merge, push, or owner-checkout changes were made.

The real `backend/extraction/` directory is byte-for-byte identical to fetched
main. Compared with main, `backend/app/main.py` contains only the savings owner's
router and startup-history additions. Its real `/inbound` and `/demo/inject`
implementations are preserved. The original and new Person 3 tests, assertions,
test harness and application contract tests are unchanged from `b8d60be`.

Ran `python scripts/gen_contracts.py` against the merged application: **zero
generated diff**. The previously mismatched descriptions now match because the
actual extraction implementation is present. No descriptions or assertions were
weakened to achieve that result. Strict regeneration into temporary files also
passes inside the unchanged test suite.

The exact feature commits represented in this tested merge are:

- Foundation tip: `440bada53946e38f70f70ab30d343cbc2750063d`.
- Stacking: `a5c0e523a0189818bc38bcd7a91890f8d780f90a`; inspected owner tip
  `6155d8cabce14617e9adf6b463f2fee938b75cbb`.
- Separate lookup storage dependency: `535dc8076a8610a1ffda198a854fe1a3827eba0c`.
- Lookup: `8b8d66197c9352cd57d9e49c5dada2d67fac5670`; inspected owner tip
  `b43f014cecfe7fc603ed56127bec29f7dd07241b`.
- Delivery: `d66c246fdefd4d7c11984f42eb8d5d47f081a22a`; inspected owner tip
  `e33c01926794bace44bc0ebd9a508b9b0a024157`.
- Savings: `704c1456d1cf26d345b4c07371534dc781589422`.
- E2E assembly's component LAPSE updates:
  `83ffa1bc83c1a3e8eef9e8eecfb44ba19c4732a5`; new tests/harness:
  `b8d60be6f4974d607549c4f6dc01ed21befe271c`.

No feature implementation fix was needed for the post-main Person 3 rerun.
The final documentation-only follow-up changes this report, not tested code.

The savings commit includes its owner's existing main.py additions. Testing added
no production wiring. `backend/tests/e2e/harness.py` mounts the actual wallet,
stacking, lookup, delivery, and savings routers exactly once, runs Uvicorn over
TCP, and invokes delivery startup/shutdown and demo-history startup in lifespan.
Fixtures own disposable schema/pool lifecycle; production owns its own lifecycle.

## Actual results

- Post-main Person 3 run on `a28650c`: **116 passed, 0 failed, 0 skipped**,
  16.37 seconds, five dependency/lifecycle deprecation warnings. All eight new
  boundary checks pass, including the formerly failing OpenAPI assertion.
- Real Chromium fetch-stream test passed with the installed browser. This tests
  the delivery client module, not the Chrome extension or MV3 lifecycle.
- Separately ran the unchanged application contract suite through the merged
  real routes, using a separate disposable migrated/seeded schema: **40 passed,
  2 failed**, 0.49 seconds, four deprecation warnings. Specifically,
  `TestInboundEndpoint::test_inbound_returns_200` and
  `TestInboundEndpoint::test_inbound_valid_schema` reach
  `main._run_extraction -> pipeline.run_pipeline -> gliner_extract._load_model`
  and raise `ExtractionUnavailable` from `ModuleNotFoundError: gliner2`.
  Those two inbound checks are dependency-blocked, not passed or skipped.
  The earlier 42-pass stub result is superseded and is not inbound evidence.
- Redemption JavaScript helper: **2 passed** using `node --test`.
- 40 generated JSON schemas, TypeScript and OpenAPI match committed artifacts
  exactly; Wallet includes rewards and reward expiration data. The generator was
  also run normally on the merged application and produced no Git diff.
- Actual Postgres server process restart preserved decrypted reward contents,
  wallet mutation, demo redemption records and the durable event cursor, with
  the same disposable encryption key before and after restart.

Coverage includes fresh/repeated migrations and seeds, $103.51/eight-record demo
history stable over startup/reseed, wallet removal/addition over application
restart, pgcrypto ciphertext and wrong-key behavior, user scoping and conflicting
identities, rollback of email/reward/outbox and redemption/status/ledger/outbox,
six concurrent HTTP redemption requests plus changed-amount retry producing one
ledger row/event, UTC daily grouping, exact money and cumulative totals.

Real CP-SAT and independent exhaustive replay agree on full arithmetic, terms,
restrictions, card choices and ties. Combined HTTP checks also assert the exact
explanation. Real offline MiniLM and pgvector cover Nike/shoes/sneakers, relevant
merchant isolation, eligibility and urgency ranking. A normalized reward is absent
from sync/lookup/stack first, then becomes available after the supported
`repo.save_reward` transaction commits. Two HTTP SSE clients receive the same
event; redemption emits one safe `reward_used`, replays on reconnect and removes
the reward from wallet, lookup and stack. Offline sync reconciles used/expired
rewards and removed wallet entries. Daily expiration covers exact now/window
boundaries, future starts, paging, overlap, rollback, reruns and alert dedupe.

## Environment and isolation

Native PostgreSQL 17.11, pgvector 0.8.7, pgcrypto 1.3; dedicated cluster
`/private/tmp/lapse-person3-e2e-pg`, localhost 55493, database `lapse_person3_e2e`.
Each test creates/drops its own schema. The restart opt-in targets only a directory
under `/private/tmp` named `lapse-person3-e2e-*`; run tests serially while enabled.
The cluster is stopped after verification; files remain for reproducibility.

Used existing Python 3.10.11 environment at
`/Users/asuya/Documents/ChatGPT/DUBHACKS/lapse-foundation/.venv/bin/python`:
FastAPI 0.119.1, Pydantic 2.14.1, asyncpg 0.32.0, OR-Tools 9.15.6755,
sentence-transformers 3.4.1, torch 2.14.1, pytest 8.4.2, pytest-asyncio 0.26.0,
Uvicorn 0.39.0, httpx 0.28.1. Repository deployment target remains Python 3.11+;
that runtime was not verified. Cached pinned MiniLM revision is
`c9745ed1d9f207416be6d2e6f8de32d1f16199bf` at `/private/tmp/lapse-minilm-cache`.

No existing `LAPSE_ENCRYPTION_KEY` was configured in the shell. Fresh disposable
schemas use generated in-memory test keys; no existing encrypted database or key
was touched. The legacy wrapper preserves a configured key if present. Real
deployment/seed commands must retain the existing key; do not copy test keys into
an existing database. Only current `LAPSE_*` configuration names are used.

## Concrete integration handoff

1. **OpenAPI mismatch resolved by actual main integration:** run
   `python -m pytest backend/tests/e2e/test_persistence_contracts.py::test_generated_openapi_matches_committed_production_contract -q`.
   This now passes unchanged. Feature PRs must retain the real extraction source
   from main. Regenerate contracts again when production Person 3 routers are
   wired; this test app deliberately does not replace production stubs.
2. **GLiNER2 absent, failures reproduced on the real routes:** dependency owner
   must provision `backend/extraction/requirements/gliner_extract.txt`, which
   declares `gliner2[local]==2.1.0`, and the `fastino/gliner2-base-v1` model, then
   rerun the two tests above unchanged. The failure occurs at package import;
   model availability/loading has not been verified. No installation, mock,
   bypass, fallback patch or extraction modification was attempted.
3. Production main.py still has lookup/stack/delivery stubs. Integration must
   replace those handlers, mount real routers once, initialize the query encoder,
   invoke delivery lifecycle hooks, and set browser CORS/host permissions as
   documented in component handoffs. Tests supply those boundaries in isolation.
4. Lookup's separate storage dependency still needs foundation acceptance.
   Shared seed imports have no semantic embeddings. The tests create vectors
   through supported writes; production embedding backfill remains owner work.
   Structured reward terms also lack a persistence adapter; HTTP uses conservative
   defaults. Do not claim test-only terms are already supported through HTTP.
5. **Runtime dependency fixes must accompany the feature PRs:** stacking needs
   actual `ortools==9.15.6755`; lookup needs `sentence-transformers>=3,<4` plus
   the pinned cache/model contract. Root requirements still only comment these
   out; clean installs cannot rely on this machine's pre-existing environment.
   Manifest changes belong to the dependency owner. Preserve LAPSE names from
   owner rename tips (or assembly commit `83ffa1b`) and the existing key value.
   Retain lookup storage commit `535dc80` exactly once, savings migration 003,
   savings schemas/generated files, and its startup-history additions. No test
   assertion fix is required. The Hollister shared fixture is still inconsistent;
   its eligibility/rate correction must be explicit in any live-demo setup.
6. **Extraction-to-storage bridge still pending:** real main's `_run_extraction`
   extends `get_rewards()` in memory; it does not call the supported Postgres
   `repo.save_reward` boundary. Integrator must bridge those writes atomically
   before claiming inbound offers reach durable SSE/lookup/stack. This test branch
   preserves that implementation rather than rebuilding another owner's work.
7. Full Postmark/email redaction/extraction/merchant-classification-to-extension
   flow, production scheduler deployment, proxy behavior, authenticated identity,
   and MV3 restart persistence remain **pending** the teammate's integrated app.
   A normalized reward insert proves none of those upstream/downstream stages.

## Reproducible setup and tests

Use the existing worktree, not a clone. Check dependencies/cache before installing
anything. PostgreSQL must provide vector/pgcrypto/uuid-ossp. On this host:

```sh
cd /Users/asuya/Documents/ChatGPT/DUBHACKS/lapse-e2e
export PYTHON=/Users/asuya/Documents/ChatGPT/DUBHACKS/lapse-foundation/.venv/bin/python
# Only if the dedicated directory does not already exist:
# initdb -D /private/tmp/lapse-person3-e2e-pg -A trust -U asuya
pg_ctl -D /private/tmp/lapse-person3-e2e-pg -l /private/tmp/lapse-person3-e2e-pg.log \
  -o '-h 127.0.0.1 -p 55493 -k /private/tmp' start
# Only if this disposable database does not already exist:
# createdb -h 127.0.0.1 -p 55493 lapse_person3_e2e
export TEST_DATABASE_URL=postgresql://asuya@127.0.0.1:55493/lapse_person3_e2e
export LAPSE_MODEL_CACHE=/private/tmp/lapse-minilm-cache
export LAPSE_E2E_ALLOW_PG_RESTART=1
export LAPSE_E2E_PGDATA=/private/tmp/lapse-person3-e2e-pg
export NODE_BINARY=/usr/local/bin/node
export PLAYWRIGHT_NODE_MODULE=/Users/asuya/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright
sh backend/tests/e2e/run.sh
# Expected on tested merged code: 116 passed, no failures/skips.
# Despite the historical wrapper name, this invokes the real merged app routes
# without patching them. Expected: 40 passed, 2 GLiNER2-dependent inbound failures.
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 "$PYTHON" -m backend.tests.e2e.legacy_contracts
node --test frontend/api/redemptions.test.mjs
git diff --check
pg_ctl -D /private/tmp/lapse-person3-e2e-pg -m fast stop
```

Without restart opt-in that one test explicitly skips. Without browser variables
the Chromium component explicitly skips. Without semantic opt-in/cache, standalone
semantic tests skip; `run.sh` enables them and a cache failure fails the run.
Post-main logs are `/private/tmp/lapse-person3-after-main.txt` and
`/private/tmp/lapse-person3-real-app-contracts.txt`; logs contain only synthetic
test data. Previous-run logs retain their old filenames and historical results.

## Short Person 3 demo runbook

1. Start the disposable cluster and export the variables above. Run
   `sh backend/tests/e2e/run.sh -k 'fresh_migrations_seed_and_application_restart'`.
   Show $103.51, eight historical items/days, unchanged dates after restart and
   wallet mutations surviving reseed. History does not spend the live voucher.
2. Run `sh backend/tests/e2e/run.sh -k 'absent_commit_discover_stack' -s`.
   Show absent-first normalized offer, commit, two live clients, real Nike/shoes/
   sneakers lookup, $100 minus $15 = $85 checkout, $4.25 later card cashback,
   concurrent redemption, $15 reward ledger and reconnect replay.
3. Run `sh backend/tests/e2e/run.sh -k 'hollister' -s`.
   Unchanged shared fixture: listed items total $479.65, leaving $20.35 unknown.
   Cash+ 5% bonus permits MCC 5311, while Hollister is MCC 5651. Honest persisted
   result: $47.97 immediate discount, $452.03 checkout, $6.78 later cashback from
   Freedom Unlimited, $54.75 total. The separate explicit test-only scenario
   allows the remainder and adds MCC 5651 to a copied demo card: $50 off, $450
   checkout, $22.50 cashback, $72.50 total. Shared seeds are unchanged. Cashback
   never reduces checkout price and is not silently added to the reward ledger.
4. Run `sh backend/tests/e2e/run.sh -k 'http_expiry_ranking or job_boundaries' -s`
   for urgency order, exact boundary expiry, overlapping jobs and rerun dedupe.
   Close by identifying the pending complete email-to-extension integration.
