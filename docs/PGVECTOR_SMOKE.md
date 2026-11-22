# Local pgvector capability smoke test

This optional probe validates that an **already-authorized PostgreSQL** database can execute 384-dimensional pgvector cosine-distance operations using two generated synthetic vectors. It performs no writes and never downloads an embedding model.

## Prerequisites

- PostgreSQL 14+ and pgvector installed in the connected database
- Read-only credentials to a **disposable, authorized test database**
- Python 3.12+ and optional `pip install 'psycopg[binary]>=3,<4'`

Set `PRISM_POSTGRES_DSN` **in your shell/environment only**, never in code or logs. Run:

```bash
python -m scripts.postgres_preflight --json
python -m scripts.pgvector_smoke
python -m unittest tests.test_pgvector_smoke -v
```

The smoke test checks that identical vectors have cosine distance 0 and orthogonal vectors have cosine distance 1. It uses `SET TRANSACTION READ ONLY` and a connection-level read-only option. If pgvector is absent or distances differ, it fails closed. Raw database connection errors are not printed.

**Not yet validated:** actual local model inference, vector indexing, persistent approved-only retrieval, tenant authorization/RLS, semantic relevance, or a real PostgreSQL integration run. No live service switches database because of this probe. Do not run against enterprise databases without approval.
