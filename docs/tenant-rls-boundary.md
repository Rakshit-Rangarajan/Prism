# PostgreSQL tenant authorization boundary (experimental)

This increment is **not** active in the public demo and is **not** proof of enterprise-grade tenant isolation.

`app/tenant_context.py` provides a strict `VerifiedIdentity` contract, transaction-local PostgreSQL context and reviewable RLS statements. It does **not** trust request-supplied tenant IDs. The demo's shared Basic Auth cannot produce a verified tenant principal.

Before enabling this in an environment with real data:

1. Integrate a trusted OIDC/SSO verifier, validate signature, issuer, audience, expiration, tenant membership and revocation as appropriate, then construct `VerifiedIdentity(..., verified=True)` **only in the trusted authentication layer**. The boolean flag is a programming contract, not cryptographic proof.
2. Introduce immutable tenant ownership (`tenant_id TEXT NOT NULL`) on each memory and vector table, backfill with approved ownership evidence, and reject unowned/ambiguous records. Do not run the DDL helper on current SQLite tables.
3. Run the generated RLS statements with a migration-only owner role; use a separate non-owner runtime role without `BYPASSRLS`, `CREATEROLE` or table-owner privileges. Ensure it cannot alter policies or schemas.
4. Treat `set_config` as defense in depth, **not** a trust anchor. A runtime role capable of arbitrary SQL can set custom GUCs itself; use parameterized fixed SQL, least-privilege functions and database-enforced identity where required. Consider separate tenant roles or verified DB-side claims for hostile SQL execution threat models.
5. Use `tenant_transaction(conn, verified_identity)` for each request; revalidate approval/version and tenant ownership in the same snapshot as retrieval. For pooled connections, never use session-scoped `SET`.
6. Execute real PostgreSQL RLS integration tests (two tenants, no tenant, cross-tenant read/write, owner bypass, pooling, concurrent approval/revision). Validate the pgvector adapter against the same RLS rules before wiring routes.
7. Keep the public Render deployment on synthetic SQLite until authenticated tenancy, durable PostgreSQL, backup/restore, and rollback are proven.

Run isolated tests: `python -m unittest tests.test_tenant_context -v`.

No paid resources, production schema changes, external AI calls or enterprise records are required.
