#!/usr/bin/env python3
"""Pre-download and warm every ML model Lapse uses, so container cold start
is fast and the image works with no network access to HuggingFace.

Run at Docker build time (after scripts/train_classifier.py) and optionally
at container start. Reuses the existing warmup helpers where they exist
(backend.extraction.gliner_extract.warmup) instead of duplicating them.

Models warmed:
  1. GLiNER2  fastino/gliner2-base-v1 (~834MB)  — gliner_extract.warmup()
  2. MiniLM   sentence-transformers/all-MiniLM-L6-v2 — merchants.py embeddings
  3. SetFit   trained email classifier (backend/extraction/models/...)
  4. spaCy    en_core_web_sm + presidio analyzer (PII redaction; soft-fail
              while the redact module's deps are optional)

Exits non-zero if any of the hard-required models (1-3) fail, so a broken
image fails at build time rather than at demo time.
"""
from __future__ import annotations

import sys
import time
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


def main() -> int:
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
