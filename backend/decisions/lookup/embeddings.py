"""Query-only embedding adapter; instantiate once during application lifespan."""
from threading import Lock
from typing import Protocol

from backend.decisions.common import EMBEDDING_MODEL, EMBEDDING_DIMENSION, vector_literal

# Pin weights for reproducible cache/backfill. Coordinate changes with Person 2.
MODEL_REVISION = 'c9745ed1d9f207416be6d2e6f8de32d1f16199bf'


class QueryEncoder(Protocol):
    model_name: str

    def encode_query(self, text: str) -> list[float]: ...


class MiniLMQueryEncoder:
    model_name = EMBEDDING_MODEL

    def __init__(self, *, cache_folder=None, offline=True):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(
            EMBEDDING_MODEL, revision=MODEL_REVISION, cache_folder=cache_folder,
            local_files_only=offline, device='cpu', trust_remote_code=False)
        if self._model.get_sentence_embedding_dimension() != EMBEDDING_DIMENSION:
            raise ValueError('Expected MiniLM 384-dimensional encoder')
        self._lock = Lock()
        self.encode_query('warmup')

    def encode_query(self, text):
        with self._lock:
            vector = self._model.encode(text, normalize_embeddings=True).tolist()
        vector_literal(vector)
        return vector
