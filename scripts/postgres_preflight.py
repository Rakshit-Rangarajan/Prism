"""Read-only PostgreSQL prerequisites check for PRISM Migration Memory.

No schema changes, row contents, credentials or secrets are emitted. Run against
an explicitly authorized disposable database before enabling any adapter.
"""
import argparse
import json
import os


def inspect_connection(conn):
    """Assess a connection with a read-only transaction and metadata-only SQL."""
    with conn.transaction():
        conn.execute("SET TRANSACTION READ ONLY")
        server = conn.execute("SHOW server_version_num").fetchone()[0]
        version = int(server)
        extensions = {r[0] for r in conn.execute(
            "SELECT extname FROM pg_catalog.pg_extension WHERE extname IN ('vector')"
        ).fetchall()}
        names = ("memory_entries", "memory_events")
        existing = {name: conn.execute("SELECT to_regclass(%s)", ("public." + name,)).fetchone()[0] is not None
                    for name in names}
        # A nonempty destination must not be overwritten by the offline migrator.
        # No row data is selected, only counts on known application tables.
        counts = {name: conn.execute("SELECT COUNT(*) FROM public." + name).fetchone()[0]
                  if existing[name] else None for name in names}
        # A vector extension is necessary, not sufficient, for local semantic search.
        report = {
            "mode": "read_only", "server_version_num": version,
            "postgres_supported": version >= 140000,
            "pgvector_installed": "vector" in extensions,
            "tables_present": existing, "table_counts": counts,
            "empty_migration_target": all(value in (None, 0) for value in counts.values()),
            "ready_for_offline_migration": version >= 140000 and all(value in (None, 0) for value in counts.values()),
            "ready_for_semantic_retrieval": False,
            "limitations": [
                "No schema, RLS, tenant authorization, vector index, embedding model or semantic quality validation is performed.",
                "This report never authorizes a production migration or enterprise data processing."
            ],
        }
        return report


def inspect_postgres(dsn):
    if not dsn:
        raise ValueError("PRISM_POSTGRES_DSN must be set")
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("Install optional psycopg v3 to run this offline preflight") from exc
    with psycopg.connect(dsn, options="-c default_transaction_read_only=on", connect_timeout=5) as conn:
        return inspect_connection(conn)


def main(argv=None):
    parser = argparse.ArgumentParser(description="PRISM read-only PostgreSQL readiness preflight")
    parser.add_argument("--json", action="store_true", help="Print a machine-readable metadata report")
    args = parser.parse_args(argv)
    try:
        result = inspect_postgres(os.getenv("PRISM_POSTGRES_DSN"))
    except Exception as exc:
        # Do not print database errors: some drivers include DSN/host/user details.
        print(json.dumps({"status": "blocked", "reason": type(exc).__name__,
                          "message": "PostgreSQL preflight could not complete; inspect connectivity and prerequisites securely."}))
        return 2
    print(json.dumps(result, indent=2 if args.json else None, sort_keys=True))
    return 0 if result["ready_for_offline_migration"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
