"""
Sentence-transformers embedder for semantic similarity scoring.

The all-MiniLM-L6-v2 model is downloaded once (~90 MB) and then runs fully
offline. Model load is amortised by a module-level singleton, so the first
request after server start pays the cold-start cost and every subsequent
call hits an in-memory cache.

The FastAPI server pre-warms the model in a background thread at startup
(see main.py lifespan), so the first user-facing request is already fast.
"""
import threading
from typing import List, Optional
import numpy as np

from config import AI_MODEL_NAME


# ── Module-level singleton ────────────────────────────────────────────────────
_MODEL_CACHE = None
_MODEL_LOCK  = threading.Lock()


def load_model():
    """Instantiate a SentenceTransformer. Called at most once per process."""
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(AI_MODEL_NAME)
    except ImportError:
        raise RuntimeError(
            "sentence-transformers not installed. "
            "Run: pip install sentence-transformers"
        )


def get_model():
    """
    Return the cached model instance.

    Thread-safe: a double-checked lock ensures the model is loaded exactly
    once even if two requests arrive simultaneously during cold-start.
    """
    global _MODEL_CACHE

    # Fast path — already loaded, no lock needed
    if _MODEL_CACHE is not None:
        return _MODEL_CACHE

    with _MODEL_LOCK:
        # Re-check inside the lock in case another thread populated the
        # cache while we were waiting
        if _MODEL_CACHE is None:
            _MODEL_CACHE = load_model()
    return _MODEL_CACHE


def encode(text: str) -> Optional[np.ndarray]:
    """Return L2-normalised embedding vector for a single text string."""
    if not text or not text.strip():
        return None
    model = get_model()
    return model.encode(text, convert_to_numpy=True, normalize_embeddings=True)


def encode_batch(texts: List[str]) -> List[Optional[np.ndarray]]:
    """Encode a batch of texts. Returns list aligned with input."""
    if not texts:
        return []
    model = get_model()
    non_empty = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
    results: List[Optional[np.ndarray]] = [None] * len(texts)
    if non_empty:
        idxs, valid_texts = zip(*non_empty)
        embeddings = model.encode(
            list(valid_texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
        )
        for idx, emb in zip(idxs, embeddings):
            results[idx] = emb
    return results


def is_model_ready() -> bool:
    try:
        get_model()
        return True
    except Exception:
        return False
