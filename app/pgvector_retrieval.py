"""Read-only, fail-closed PostgreSQL pgvector retrieval for approved Migration Memory.

Caller supplies a psycopg-compatible connection and a schema with the documented
columns. No network/model calls or schema changes are performed here.
"""
import math
from collections.abc import Sequence

SQL = """SELECT id, tenant_id, domain, target_object, title, resolution, evidence,
       version, supersedes_id, (embedding <=> %s::vector) AS distance
FROM memory_entries
WHERE tenant_id = %s AND domain = %s AND target_object = %s
  AND state = 'approved' AND embedding IS NOT NULL
  AND vector_dims(embedding) = %s
ORDER BY embedding <=> %s::vector, id DESC
LIMIT %s"""


def retrieve_approved(connection, *, tenant_id: str, domain: str,
                      target_object: str, embedding: Sequence[float],
                      limit: int = 10):
    """Return nearest approved rows in one exact tenant/domain/object scope.

    Requires pgvector installed and memory_entries with tenant_id and embedding.
    The caller must authenticate/authorize the supplied tenant scope separately.
    """
    for name, value, maximum in (("tenant_id", tenant_id, 128),
                                 ("domain", domain, 80),
                                 ("target_object", target_object, 100)):
        if not isinstance(value, str) or not value.strip() or len(value) > maximum:
            raise ValueError(f"Invalid {name} scope")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if isinstance(embedding, (str, bytes)) or not isinstance(embedding, Sequence) or not 1 <= len(embedding) <= 4096:
        raise ValueError("embedding dimension out of bounds")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in embedding):
        raise ValueError("embedding must contain finite numbers")
    if not any(v != 0 for v in embedding):
        raise ValueError("zero embedding is not supported")
    vector = "[" + ",".join(format(float(v), ".17g") for v in embedding) + "]"
    with connection.cursor() as cursor:
        cursor.execute(SQL, (vector, tenant_id, domain, target_object, len(embedding), vector, limit))
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
