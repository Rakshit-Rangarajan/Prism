# Local semantic retrieval — opt-in adapter

This feature branch adds an **unwired** PostgreSQL/pgvector derived index for
company-scoped, approved Migration Memory. It does not change the live API,
replace SQLite, or provision PostgreSQL.

## Requirements
- Existing PostgreSQL with pgvector installed and a reviewed schema migration.
- Explicit tenant identity from authenticated authorization, **never** an
  arbitrary company name from the client.
- Approved entries and their revision state remain authoritative in the
  primary store. A retrieval result MUST be checked against the current
  approved source record before returning content.
- Optional `sentence-transformers` dependency and a locally cached
  384-dimensional embedding model (e.g. a vetted MiniLM-compatible model).
  The adapter refuses to download a model automatically.
- Tenant-specific retention, encryption, backups, and authorization policies.

## Operations
- Review `SCHEMA_SQL` in `app/semantic.py` before applying; `CREATE EXTENSION`
  may require database permissions. No automatic DDL on app startup.
- Index **only after** a human approval transaction commits, and retire
  superseded entries. Handle stale index rows by source-of-truth revalidation.
- Search requires tenant, domain, target object and an embedding. SQL is
  parameterized; cosine distance ranks within the approved scope.
- This exact-vector scan is suitable only for limited data volumes; benchmark
  and choose tenant-aware indexing strategies before scaling.
- Run: `python -m unittest tests.test_semantic -v`

## Explicit limitations
No deployed local LLM, fine-tuning, persistent database, tenant auth, live
integration, model evaluation, or semantic API route in this increment.
Production wiring must wait for PostgreSQL integration tests and verified
tenant authorization. This branch is intentionally not merged or deployed.
