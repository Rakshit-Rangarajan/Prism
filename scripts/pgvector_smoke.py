"""Opt-in, read-only pgvector capability smoke test.

Uses two synthetic 384-dimensional vectors; no enterprise records, table writes,
embedding downloads, or schema changes. Not a semantic quality or tenant test.
"""
import argparse
import json
import os

DIMENSIONS = 384

def synthetic_vector(position):
    if not 0 <= position < DIMENSIONS:
        raise ValueError("Invalid synthetic vector position")
    return "[" + ",".join("1" if i == position else "0" for i in range(DIMENSIONS)) + "]"

def inspect_vector_connection(conn):
    """Run all probes inside an explicit read-only transaction."""
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        installed = conn.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_extension WHERE extname='vector')"
        ).fetchone()[0]
        if not installed:
            return {"status":"blocked", "reason":"pgvector_not_installed",
                    "vector_dimensions":DIMENSIONS, "read_only":True,
                    "semantic_retrieval_ready":False}
        left=synthetic_vector(0)
        same=synthetic_vector(0)
        different=synthetic_vector(1)
        query="SELECT %s::vector(384) <=> %s::vector(384)"
        identical=float(conn.execute(query,(left,same)).fetchone()[0])
        orthogonal=float(conn.execute(query,(left,different)).fetchone()[0])
        valid=abs(identical)<1e-6 and abs(orthogonal-1.0)<1e-6
        return {"status":"passed" if valid else "failed",
                "vector_dimensions":DIMENSIONS, "read_only":True,
                "identical_cosine_distance":identical,
                "orthogonal_cosine_distance":orthogonal,
                "semantic_retrieval_ready":False,
                "limitations":"Synthetic vector operator check only; no model, tenant isolation, index, approvals or persistence tested."}

def inspect_postgres(dsn):
    if not dsn:
        raise ValueError("PRISM_POSTGRES_DSN must be set")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Optional psycopg v3 dependency required") from exc
    with psycopg.connect(dsn,options="-c default_transaction_read_only=on",connect_timeout=5) as conn:
        return inspect_vector_connection(conn)

def main(argv=None):
    parser=argparse.ArgumentParser(description="Read-only synthetic pgvector operator smoke test")
    parser.parse_args(argv)
    try:
        result=inspect_postgres(os.getenv("PRISM_POSTGRES_DSN"))
    except Exception as exc:
        # Never include raw driver errors: connection strings may contain secrets.
        print(json.dumps({"status":"blocked","reason":type(exc).__name__,
                          "message":"pgvector probe unavailable; inspect local prerequisites securely."}))
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0 if result["status"]=="passed" else 1

if __name__=="__main__":
    raise SystemExit(main())
