# PRISM PostgreSQL read-only preflight

This is an **offline operator utility**, not a live API, database migration, or evidence of production readiness. It requires an explicitly authorized disposable PostgreSQL database. It does not create resources, install extensions, modify schema, read row contents, or connect to Qlik/SAP.

```bash
python -m pip install 'psycopg[binary]>=3,<4'  # optional, in a disposable environment
export PRISM_POSTGRES_DSN='postgresql://...'    # never commit this value
python -m scripts.postgres_preflight --json
```

The connection is configured with `default_transaction_read_only=on` and executes `SET TRANSACTION READ ONLY` before checking version, pgvector installation, memory table presence and counts. Exit code 0 means the basic version and empty-destination conditions are met; 1 means those checks fail; 2 means the inspection could not complete. A successful exit is **not** permission to migrate or a guarantee of PostgreSQL/pgvector integration readiness.

The tool intentionally reports `ready_for_semantic_retrieval: false` until tenant authorization, schema and index verification, local embedding evaluation, and actual PostgreSQL integration tests exist. Use `python -m unittest discover -s tests -p 'test_*.py' -v` to run regression tests. Database connection errors are redacted from CLI output to avoid leaking credentials. The live Render demo continues to use ephemeral SQLite.
