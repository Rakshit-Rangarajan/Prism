"""Opt-in, offline-only neural embeddings for synthetic Migration Memory.

No model downloads or network requests are performed. Administrators must
pre-provision a local sentence-transformers model directory.
"""
from functools import lru_cache
from pathlib import Path
import math
import os


class LocalEmbeddingUnavailable(RuntimeError):
    """The configured offline embedding model cannot be used safely."""


def model_directory() -> Path:
    configured = os.environ.get("PRISM_LOCAL_EMBEDDING_MODEL", "").strip()
    if not configured:
        raise LocalEmbeddingUnavailable("PRISM_LOCAL_EMBEDDING_MODEL is not configured")
    path = Path(configured).expanduser().resolve()
    if not path.is_dir():
        raise LocalEmbeddingUnavailable("Local embedding model directory does not exist")
    return path


@lru_cache(maxsize=2)
def _load_model(directory: str):
    try:
        from sentence_transformers import SentenceTransformer
        return SentenceTransformer(directory, local_files_only=True, trust_remote_code=False)
    except (ImportError, OSError, ValueError, RuntimeError) as exc:
        raise LocalEmbeddingUnavailable("Offline embedding model could not be loaded") from exc


def embed_local(text: str, *, expected_dimensions: int | None = None) -> list[float]:
    if not isinstance(text, str) or not text.strip() or len(text) > 8000:
        raise ValueError("Embedding text must be 1–8000 nonblank characters")
    if expected_dimensions is not None and not 1 <= expected_dimensions <= 4096:
        raise ValueError("Invalid embedding dimension constraint")
    model = _load_model(str(model_directory()))
    vector = model.encode([text], normalize_embeddings=True)[0]
    values = [float(x) for x in vector]
    if not values or len(values) > 4096 or not all(math.isfinite(x) for x in values):
        raise LocalEmbeddingUnavailable("Model returned an invalid embedding")
    if expected_dimensions is not None and len(values) != expected_dimensions:
        raise LocalEmbeddingUnavailable("Embedding dimension mismatch")
    if math.sqrt(sum(x*x for x in values)) < 1e-12:
        raise LocalEmbeddingUnavailable("Model returned a zero embedding")
    return values
