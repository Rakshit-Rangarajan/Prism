# Disposable pgvector integration gate

This is a **local-only, synthetic** integration environment. It is not the
production PostgreSQL service, not tenant isolation, and not real semantic
retrieval. The container uses a fixed test password and a tmpfs database,
bound to loopback port 55432. Do not expose it publicly.

## Run locally

Requires Docker Compose (or a compatible local Podman Compose provider),
Python 3.12+, and optional psycopg v3. No paid service or external LLM is used.

```sh
docker compose -f infra/postgres/compose.integration.yml up -d --wait
python -m pip install "psycopg[binary]>=3,<4"
export PRISM_INTEGRATION_TEST=1
export PRISM_INTEGRATION_DSN='postgresql://prism_test:local_test_only_not_for_production@127.0.0.1:55432/prism_integration_test'
python -m unittest discover -s tests -p 'test_postgres_live_integration.py' -v
docker compose -f infra/postgres/compose.integration.yml down --volumes
```

The integration tests reject non-loopback hosts and database names other
than `prism_integration_test`. They install the vector extension only in
the disposable test DB, verify real 384-dimensional cosine operators,
exercise read-only metadata preflight, and prove writes fail in a read-only
transaction. The general Docker build runs the tests as **skipped** unless
explicitly opted in. No production credentials should be used.

**Still required:** validate schema/migration end to end; PostgreSQL RLS,
tenant identity and authorization; approved-version revalidation; local
embedding model; semantic recall benchmarks; persistence in FastAPI.
Do not mark those capabilities complete from this smoke test.
