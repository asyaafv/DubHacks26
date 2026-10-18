#!/usr/bin/env python3
"""Pre-download and warm every ML model Lapse uses, so container cold start
is fast and the image works with no network access to HuggingFace.

Two modes:

1. In-process (default) — run at Docker build time (after
   scripts/train_classifier.py). Imports the model modules directly so the
   weights are downloaded into HF_HOME and the trained classifier is
   verified. Reuses the existing warmup helpers where they exist
   (backend.extraction.gliner_extract.warmup) instead of duplicating them.

   Models warmed:
     1. GLiNER2  fastino/gliner2-base-v1 (~834MB)  — gliner_extract.warmup()
     2. MiniLM   sentence-transformers/all-MiniLM-L6-v2 — merchants.py embeddings
     3. SetFit   trained email classifier (backend/extraction/models/...)
     4. spaCy    en_core_web_sm + presidio analyzer (PII redaction; soft-fail
                 while the redact module's deps are optional)

   Exits non-zero if any of the hard-required models (1-3) fail, so a broken
   image fails at build time rather than at demo time.

2. HTTP (--http) — run at container START (the Dockerfile CMD launches this
   in the background when WARM_MODELS=1). Models load lazily per-process, so
   warming must happen INSIDE the serving uvicorn worker: this mode polls
   /health until the API is up, then replays a plaintext seed email through
   POST /demo/inject (force=true, routed to a throwaway warmup user so the
   demo user's data is untouched). That one request loads SetFit + GLiNER2 +
   MiniLM in the server process, so the first real demo email takes ~0.4s
   instead of ~5s. Stdlib-only — also usable against a remote deploy:

       python3 scripts/warm_models.py --http --base-url https://lapse-api.onrender.com
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

FAILURES: list[str] = []


def _step(name: str, fn, required: bool = True) -> None:
    start = time.perf_counter()
    try:
        fn()
        print(f"[warm] OK   {name} ({time.perf_counter() - start:.1f}s)")
    except Exception as exc:  # noqa: BLE001 - report every failure uniformly
        level = "FAIL" if required else "WARN"
        print(f"[warm] {level} {name}: {exc}")
        if required:
            FAILURES.append(name)


def warm_gliner() -> None:
    from backend.extraction.gliner_extract import warmup

    warmup()  # loads fastino/gliner2-base-v1 and runs one extraction


def warm_minilm() -> None:
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
    model.encode(["warmup sentence"])


def warm_setfit_classifier() -> None:
    from backend.extraction.classify import classify_email, get_model_info

    info = get_model_info()
    label, conf = classify_email(
        "Your 10% off voucher", "Use code SAVE10 on your next purchase. Expires soon."
    )
    print(f"[warm]      classifier={info['model_type']} sample=({label}, {conf:.2f})")
    if info["model_type"] != "setfit":
        raise RuntimeError(
            "SetFit model not found — run scripts/train_classifier.py first "
            f"(info={info})"
        )


def warm_presidio_spacy() -> None:
    import spacy

    spacy.load("en_core_web_sm")

    from presidio_analyzer import AnalyzerEngine

    analyzer = AnalyzerEngine()
    analyzer.analyze(text="Call 555-123-4567", language="en")


# =============================================================================
# HTTP warm mode (--http): warm the RUNNING server process via /demo/inject
# =============================================================================

# Plaintext seed email (no JSON-LD) so the pipeline takes the GLiNER2 path.
WARM_EML = "chipotle_plaintext.eml"
# Throwaway user: rewards/events from warmup never touch the demo user.
WARM_USER_ID = "00000000-0000-0000-0000-00000000f00d"


def _http_json(url: str, payload: dict | None, timeout: float) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method="POST" if data is not None else "GET",
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode() or "{}")


def warm_http(base_url: str, wait_secs: float, timeout: float) -> int:
    base = base_url.rstrip("/")

    deadline = time.monotonic() + wait_secs
    while True:
        try:
            status, _ = _http_json(f"{base}/health", None, timeout=5)
            if status == 200:
                break
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            pass
        if time.monotonic() >= deadline:
            print(f"[warm] FAIL server at {base} not healthy after {wait_secs:.0f}s",
                  file=sys.stderr)
            return 1
        time.sleep(0.5)

    start = time.perf_counter()
    try:
        status, body = _http_json(
            f"{base}/demo/inject",
            {"eml_filename": WARM_EML, "force": True, "user_id": WARM_USER_ID},
            timeout=timeout,
        )
    except (urllib.error.URLError, OSError) as exc:
        print(f"[warm] FAIL warm inject: {exc}", file=sys.stderr)
        return 1
    elapsed = time.perf_counter() - start
    if status != 200:
        print(f"[warm] FAIL warm inject HTTP {status}: {body}", file=sys.stderr)
        return 1
    print(
        f"[warm] OK   server warm in {elapsed:.1f}s "
        f"(classification={body.get('classification')} "
        f"rewards={body.get('rewards_extracted')} "
        f"pipeline={body.get('processing_time_ms')}ms) — "
        f"first demo email will now be fast"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Warm the Lapse ML models")
    parser.add_argument("--http", action="store_true",
                        help="Warm a RUNNING server via /demo/inject instead of in-process")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000",
                        help="API base URL for --http (default: http://127.0.0.1:8000)")
    parser.add_argument("--wait-secs", type=float, default=120.0,
                        help="--http: how long to wait for /health (default: 120)")
    parser.add_argument("--timeout", type=float, default=180.0,
                        help="--http: warm request timeout (first GLiNER load is slow)")
    args = parser.parse_args()

    if args.http:
        return warm_http(args.base_url, args.wait_secs, args.timeout)

    total = time.perf_counter()
    _step("GLiNER2 fastino/gliner2-base-v1", warm_gliner, required=True)
    _step("MiniLM all-MiniLM-L6-v2", warm_minilm, required=True)
    _step("SetFit email classifier", warm_setfit_classifier, required=True)
    _step("presidio + spaCy en_core_web_sm", warm_presidio_spacy, required=False)
    print(f"[warm] done in {time.perf_counter() - total:.1f}s")
    if FAILURES:
        print(f"[warm] FAILED: {', '.join(FAILURES)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
