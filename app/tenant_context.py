"""PostgreSQL tenant context boundary for future PRISM persistence.

NOT wired to demo Basic Auth. The caller must supply claims verified by an
upstream authentication provider, never a tenant header or request body.
A transaction-scoped GUC alone is not an authorization boundary: PostgreSQL
RLS, restricted roles, and source-of-truth ownership checks are required.
"""
from contextlib import contextmanager
from dataclasses import dataclass
import re
from uuid import UUID

_TENANT_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}$")
_SUBJECT_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:@-]{2,127}$")


@dataclass(frozen=True)
class VerifiedIdentity:
    tenant_id: str
    subject_id: str
    issuer: str
    verified: bool = False

    def validate(self):
        if not self.verified:
            raise PermissionError("Verified authentication is required")
        if not isinstance(self.tenant_id, str) or not _TENANT_ID.fullmatch(self.tenant_id):
            raise PermissionError("Invalid verified tenant identity")
        if not isinstance(self.subject_id, str) or not _SUBJECT_ID.fullmatch(self.subject_id):
            raise PermissionError("Invalid verified subject identity")
        if not isinstance(self.issuer, str) or not self.issuer.strip() or len(self.issuer) > 256:
            raise PermissionError("Missing verified issuer")
        return self


@contextmanager
def tenant_transaction(conn, identity: VerifiedIdentity):
    """Bind a verified principal to one PostgreSQL transaction.

    Requires a psycopg-compatible connection. Never uses SET SESSION, which
    could leak tenant context across pooled connections. Database RLS must
    reject missing tenant settings and enforce all row-level operations.
    """
    if not isinstance(identity, VerifiedIdentity):
        raise PermissionError("Expected verified authentication claims")
    identity.validate()
    with conn.transaction():
        conn.execute(
            "SELECT pg_catalog.set_config('prism.tenant_id', %s, true)",
            (identity.tenant_id,),
        )
        conn.execute(
            "SELECT pg_catalog.set_config('prism.subject_id', %s, true)",
            (identity.subject_id,),
        )
        yield conn


def memory_rls_statements(table_name="memory_entries"):
    """Generate reviewable RLS DDL for an already tenant-keyed table.

    This helper does not run migrations. Table and tenant_id column must exist;
    migrations must add NOT NULL tenant ownership before enabling RLS.
    """
    allowed = {"memory_entries", "memory_events", "migration_memory_vectors"}
    if table_name not in allowed:
        raise ValueError("Unsupported memory table")
    return (
        f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY",
        f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY",
        f"DROP POLICY IF EXISTS prism_tenant_isolation ON {table_name}",
        f"""CREATE POLICY prism_tenant_isolation ON {table_name}
        FOR ALL
        USING (
          tenant_id = NULLIF(pg_catalog.current_setting('prism.tenant_id', true), '')
        )
        WITH CHECK (
          tenant_id = NULLIF(pg_catalog.current_setting('prism.tenant_id', true), '')
        )""",
    )
