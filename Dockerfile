# Lapse API — FastAPI backend with the full ML extraction stack baked in.
#
# Build:   docker build -t lapse-api .
# Run:     docker run -p 8000:8000 -e PORT=8000 lapse-api
#
# The image is intentionally "fat": the SetFit classifier is trained at build
# time and the GLiNER2 / MiniLM / spaCy weights are pre-downloaded into the
# image so cold start is seconds, not minutes. See docs/DEPLOY.md.

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # All HuggingFace downloads (SetFit base, GLiNER2, MiniLM) cache here,
    # inside the image, and are reused at runtime.
    HF_HOME=/opt/hf-cache \
    HF_HUB_DISABLE_TELEMETRY=1 \
    TOKENIZERS_PARALLELISM=false \
    OMP_NUM_THREADS=2

WORKDIR /app

# --- CPU-only torch first ---------------------------------------------------
# Installing torch from the PyTorch CPU wheel index BEFORE anything else keeps
# transitive deps (setfit, sentence-transformers, gliner2) from pulling the
# multi-GB CUDA build off PyPI. Everything downstream sees torch as satisfied.
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.0,<3.0"

# --- Python dependencies ----------------------------------------------------
# Copy only requirements files first so this (slow) layer is cached across
# code-only rebuilds. The globs below pick up any NEW per-module requirements
# files other agents add under backend/{extraction,intake}/requirements/.
COPY requirements.txt requirements-ml.txt ./
COPY backend/extraction/requirements/ backend/extraction/requirements/
COPY backend/intake/requirements/ backend/intake/requirements/
RUN set -eux; \
    reqs="-r requirements.txt -r requirements-ml.txt"; \
    for f in backend/extraction/requirements/*.txt backend/intake/requirements/*.txt; do \
        reqs="$reqs -r $f"; \
    done; \
    pip install $reqs

# PII redaction stack for backend/intake/redact.py (presidio + spaCy model).
RUN pip install "presidio-analyzer>=2.2,<3" "presidio-anonymizer>=2.2,<3" && \
    python -m spacy download en_core_web_sm

# --- Application code -------------------------------------------------------
COPY backend/ backend/
COPY shared/ shared/
COPY scripts/ scripts/

# --- Bake the models into the image -----------------------------------------
# 1. Train the SetFit email classifier (also downloads the MiniLM base model
#    into HF_HOME). Output: backend/extraction/models/email_classifier/
RUN python scripts/train_classifier.py

# 2. Pre-download + warm GLiNER2 (fastino/gliner2-base-v1, ~834MB), the MiniLM
#    sentence-transformer used by merchants.py, the trained classifier and the
#    spaCy/presidio stack, so the first request doesn't hit the network.
RUN python scripts/warm_models.py

# --- Runtime -----------------------------------------------------------------
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import os,urllib.request,sys; \
        url=f\"http://127.0.0.1:{os.environ.get('PORT','8000')}/health\"; \
        sys.exit(0 if urllib.request.urlopen(url, timeout=4).status == 200 else 1)"

# Single worker: the ML models are loaded per-process; 2 workers would double
# RAM. Scale with bigger instances or more containers, not --workers.
CMD ["sh", "-c", "exec uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
