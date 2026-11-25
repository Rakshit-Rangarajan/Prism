# PostgreSQL tenant-isolation structural audit

Run `python -m scripts.postgres_rls_audit` with `PRISM_POSTGRES_DSN` set to an **authorized disposable local PostgreSQL** connection for the **restricted application role**. Install optional `psycopg[binary]` only in the isolated testing environment. This tool performs read-only metadata inspection and makes no changes.

It checks that `public.memory_entries`, `public.memory_events`, and `public.memory_vectors` exist, have `tenant_id NOT NULL`, RLS enabled and forced, and at least one policy. It also rejects roles with SUPERUSER or BYPASSRLS privileges.

**This is not an isolation certification.** It deliberately does not trust policy presence as proof of correct tenant predicates. It cannot verify policy expressions, grants, application authentication, transaction-local tenant identity, privilege escalation, or actual cross-tenant visibility. A separate test with two synthetic tenants, a restricted runtime role and explicit negative read/write assertions is mandatory before enabling PostgreSQL for enterprise data. Never point this tool at production without authorization. It reports no row contents or DSN details.
