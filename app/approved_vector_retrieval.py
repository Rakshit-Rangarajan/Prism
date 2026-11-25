"""Offline approved-vector ranking core. No model calls, SQL or writes."""
import math

def _unit_vector(values, dimensions):
    if not isinstance(values, (list, tuple)) or len(values) != dimensions:
        raise ValueError("Embedding dimension mismatch")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
        raise ValueError("Embedding contains invalid values")
    norm = math.sqrt(sum(float(v) * float(v) for v in values))
    if norm <= 0 or not math.isfinite(norm):
        raise ValueError("Embedding must have finite nonzero magnitude")
    return tuple(float(v) / norm for v in values)

def retrieve_approved(query_vector, records, *, tenant_id, domain, target_object, dimensions=384, limit=10):
    """Rank approved current records in exact scope; caller must enforce DB RLS."""
    if not isinstance(tenant_id, str) or not tenant_id.strip():
        raise ValueError("Verified tenant identity is required")
    if not isinstance(domain, str) or not domain.strip() or not isinstance(target_object, str) or not target_object.strip():
        raise ValueError("Exact domain and target object are required")
    if not isinstance(dimensions, int) or isinstance(dimensions, bool) or not 1 <= dimensions <= 4096:
        raise ValueError("Invalid embedding dimensions")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ValueError("Invalid result limit")
    query = _unit_vector(query_vector, dimensions)
    ranked = []
    for record in records:
        if (record.get("tenant_id") != tenant_id or record.get("domain") != domain
                or record.get("target_object") != target_object
                or record.get("state") != "approved" or record.get("superseded") is not False):
            continue
        vector = _unit_vector(record["vector"], dimensions)
        score = sum(a * b for a, b in zip(query, vector))
        ranked.append({"id": record["id"], "cosine_similarity": round(max(-1., min(1., score)), 8)})
    ranked.sort(key=lambda r: (-r["cosine_similarity"], str(r["id"])))
    return ranked[:limit]
