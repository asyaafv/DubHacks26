"""Pre-download and warm the GLiNER2 model (run at deploy/build time).

Usage:
    python -m backend.extraction.scripts.warm_gliner
"""
from __future__ import annotations

import logging
import sys
import time

from backend.extraction.gliner_extract import MODEL_ID, _get_model, extract_fields


def main() -> int:
    logging.basicConfig(level=logging.INFO)
    print(f"Warming GLiNER2 model {MODEL_ID} (CPU)...")
    start = time.perf_counter()
    model = _get_model()
    load_s = time.perf_counter() - start
    if model is None:
        print("FAILED: model could not be loaded (see warnings above).")
        return 1
    print(f"Model loaded in {load_s:.1f}s")

    start = time.perf_counter()
    extract_fields("Get 10% off with code SAVE10. Expires Oct 31. Min spend $50.")
    print(f"Warm inference done in {time.perf_counter() - start:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
