"""Optional local embeddings and tenant-isolated pgvector search.

No network model downloads or database provisioning are performed here. This
module is opt-in and requires an already provisioned PostgreSQL + pgvector
instance and a locally cached embedding model.
"""
import os
import math
from typing import Sequence

VECTOR_DIMENSION = 384
SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS tenant_memory_vectors (
    tenant_id TEXT NOT NULL,
    entry_id BIGINT NOT NULL,
    domain TEXT NOT NULL,
    target_object TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('draft','approved','rejected','superseded')),
    version INTEGER NOT NULL CHECK (version > 0),
    embedding vector(384) NOT NULL,
    PRIMARY KEY (tenant_id, entry_id)
);
CREATE INDEX IF NOT EXISTS tenant_memory_scope_idx
    ON tenant_memory_vectors (tenant_id, domain, target_object, state);
"""
# No ANN index is created by default: exact pgvector distance is predictable
# for small company-scoped corpora. Add tuned HNSW indexes after benchmarking.
SEARCH_SQL = """
SELECT entry_id, version, (embedding <=> %s::vector) AS distance
FROM tenant_memory_vectors
WHERE tenant_id = %s AND domain = %s AND target_object = %s
  AND state = 'approved'
ORDER BY embedding <=> %s::vector ASC, entry_id ASC
LIMIT %s
"""
UPSERT_SQL = """
INSERT INTO tenant_memory_vectors
(tenant_id, entry_id, domain, target_object, state, version, embedding)
VALUES (%s,%s,%s,%s,%s,%s,%s::vector)
ON CONFLICT (tenant_id, entry_id)
DO UPDATE SET domain=EXCLUDED.domain,
target_object=EXCLUDED.target_object, state=EXCLUDED.state,
version=EXCLUDED.version, embedding=EXCLUDED.embedding
"""

class SemanticUnavailable(RuntimeError):
    """Missing optional dependencies or locally cached model."""

def _scope(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError(f"{name} must be a nonempty string of at most 128 characters")
    return value.strip()

def vector_literal(values: Sequence[float]) -> str:
    if len(values) != VECTOR_DIMENSION:
        raise ValueError(f"Expected {VECTOR_DIMENSION} embedding dimensions")
    checked = [float(x) for x in values]
    if not all(math.isfinite(x) for x in checked):
        raise ValueError("Embeddings must contain only finite numbers")
    if not any(x != 0 for x in checked):
        raise ValueError("Zero embeddings cannot be compared using cosine distance")
    return "[" + ",".join(format(x, ".9g") for x in checked) + "]"

def local_encoder(model_path: str):
    """Load an existing on-disk model; never silently fetch from the internet."""
    if not os.path.isdir(model_path):
        raise SemanticUnavailable("Local embedding model directory is missing")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise SemanticUnavailable("Install the optional sentence-transformers package") from exc
    return SentenceTransformer(model_path, local_files_only=True)

def encode_text(model, text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Text must not be empty")
    return vector_literal(model.encode(text, normalize_embeddings=True).tolist())

def search_approved(connection, *, tenant_id: str, domain: str,
                    target_object: str, embedding: Sequence[float],
                    limit: int = 20):
    """Return approved-only scoped IDs; caller must recheck source record state.

    The vectors are a derived index, not an authorization source of truth.
    The caller must authenticate tenant membership and verify each returned
    entry is still approved in its transactional source of truth.
    """
    tenant_id = _scope(tenant_id, "tenant_id")
    domain = _scope(domain, "domain")
    target_object = _scope(target_object, "target_object")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be an integer between 1 and 100")
    vector = vector_literal(embedding)
    with connection.cursor() as cur:
        cur.execute(SEARCH_SQL, (vector, tenant_id, domain, target_object, vector, limit))
        return [{"entry_id": int(row[0]), "version": int(row[1]),
                 "distance": float(row[2])} for row in cur.fetchall()]

def upsert_approved(connection, *, tenant_id: str, entry_id: int, domain: str,
                    target_object: str, version: int, embedding: Sequence[float]):
    """Index an entry after approval, not as part of a draft write."""
    tenant_id = _scope(tenant_id, "tenant_id")
    domain = _scope(domain, "domain")
    target_object = _scope(target_object, "target_object")
    if type(entry_id) is not int or entry_id <= 0:
        raise ValueError("entry_id must be a positive integer")
    if type(version) is not int or version <= 0:
        raise ValueError("version must be a positive integer")
    vector = vector_literal(embedding)
    with connection.cursor() as cur:
        cur.execute(UPSERT_SQL, (tenant_id, entry_id, domain,
                                 target_object, "approved", version, vector))

def retire_entry(connection, *, tenant_id: str, entry_id: int):
    """Remove a superseded/rejected entry from the derived index."""
    tenant_id = _scope(tenant_id, "tenant_id")
    if type(entry_id) is not int or entry_id <= 0:
        raise ValueError("entry_id must be a positive integer")
    with connection.cursor() as cur:
        cur.execute("DELETE FROM tenant_memory_vectors WHERE tenant_id=%s AND entry_id=%s",
                    (tenant_id, entry_id))
