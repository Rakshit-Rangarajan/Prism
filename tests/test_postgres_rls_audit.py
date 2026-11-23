import contextlib
import io
import json
import unittest
from unittest.mock import patch
from scripts.postgres_rls_audit import audit_connection, audit_postgres, main

class Cursor:
    def __init__(self,rows):self.rows=rows
    def fetchone(self):return self.rows[0] if self.rows else None
    def fetchall(self):return self.rows

class Conn:
    def __init__(self,superuser=False,bypass=False,forced=True,tenant=True,policies=True,missing=False,unrestricted=False):
        self.superuser=superuser;self.bypass=bypass;self.forced=forced
        self.tenant=tenant;self.policies=policies;self.missing=missing;self.unrestricted=unrestricted;self.calls=[]
    @contextlib.contextmanager
    def transaction(self):yield self
    def execute(self,sql,params=None):
        self.calls.append((sql,params))
        if sql=="SET TRANSACTION READ ONLY":return Cursor([])
        if "FROM pg_catalog.pg_roles" in sql:return Cursor([("prism_runtime",self.superuser,self.bypass)])
        if "FROM pg_catalog.pg_class" in sql:
            return Cursor([(t,True,self.forced,False) for t in ("memory_entries","memory_events","memory_vectors") if not (self.missing and t=="memory_vectors")])
        if "FROM information_schema.columns" in sql:
            return Cursor([(t,"tenant_id","NO" if self.tenant else "YES") for t in ("memory_entries","memory_events","memory_vectors")])
        if "FROM pg_catalog.pg_policies" in sql:
            return Cursor([(t,"tenant_policy","ALL","(TRUE)" if self.unrestricted else "tenant_id = current_setting(...)","tenant_id = current_setting(...)") for t in ("memory_entries","memory_events","memory_vectors")] if self.policies else [])
        raise AssertionError("Unexpected SQL")

class AuditTests(unittest.TestCase):
    def test_structural_prerequisites_are_not_tenant_verification(self):
        c=Conn();r=audit_connection(c)
        self.assertTrue(r["structural_prerequisites_pass"])
        self.assertFalse(r["tenant_isolation_verified"])
        self.assertEqual(c.calls[0][0],"SET TRANSACTION READ ONLY")
        self.assertTrue(all(q.startswith(("SELECT","SET TRANSACTION READ ONLY")) for q,_ in c.calls))
    def test_superuser_blocked(self):
        self.assertFalse(audit_connection(Conn(superuser=True))["structural_prerequisites_pass"])
    def test_bypass_rls_blocked(self):
        self.assertFalse(audit_connection(Conn(bypass=True))["role"]["safe_for_rls"])
    def test_force_rls_required(self):
        self.assertIn("rls_not_forced",audit_connection(Conn(forced=False))["tables"]["memory_entries"]["issues"])
    def test_tenant_column_not_null_required(self):
        self.assertIn("tenant_id_not_null_missing",audit_connection(Conn(tenant=False))["tables"]["memory_entries"]["issues"])
    def test_policy_required(self):
        self.assertIn("policy_missing",audit_connection(Conn(policies=False))["tables"]["memory_entries"]["issues"])
    def test_unrestricted_policy_is_flagged(self):
        result=audit_connection(Conn(unrestricted=True))
        self.assertFalse(result["structural_prerequisites_pass"])
        self.assertIn("unrestricted_policy_expression",result["tables"]["memory_entries"]["issues"])
    def test_missing_table_blocked(self):
        self.assertIn("table_missing",audit_connection(Conn(missing=True))["tables"]["memory_vectors"]["issues"])
    def test_no_dsn(self):
        with self.assertRaisesRegex(ValueError,"PRISM_POSTGRES_DSN"):audit_postgres("")
    def test_cli_redacts_connection_secrets(self):
        with patch("scripts.postgres_rls_audit.audit_postgres",side_effect=RuntimeError("password=SECRET host=private")):
            with patch("sys.stdout",new_callable=io.StringIO) as out:
                self.assertEqual(main([]),2)
            self.assertNotIn("SECRET",out.getvalue())
            self.assertNotIn("private",out.getvalue())

if __name__=="__main__":unittest.main()
