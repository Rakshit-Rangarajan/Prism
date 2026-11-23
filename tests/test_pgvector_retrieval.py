"""Offline regression tests for scoped pgvector SQL; no database required."""
import unittest
from app.pgvector_retrieval import retrieve_approved, SQL

class Cursor:
    description = [(x,) for x in ("id", "tenant_id", "distance")]
    def __init__(self): self.executed = None
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params): self.executed = (sql, params)
    def fetchall(self): return [(7, "tenant-a", 0.12)]
class Connection:
    def __init__(self): self.c = Cursor()
    def cursor(self): return self.c

class RetrievalTests(unittest.TestCase):
    def test_parameterized_tenant_scoped_approved_only(self):
        db = Connection()
        rows = retrieve_approved(db, tenant_id="tenant-a", domain="Vendor", target_object="SUPPLIER", embedding=[0.2, 0.5])
        self.assertEqual(rows[0]["id"], 7)
        sql, params = db.c.executed
        self.assertEqual(sql, SQL)
        self.assertIn("tenant_id = %s", sql)
        self.assertIn("state = 'approved'", sql)
        self.assertIn("vector_dims(embedding) = %s", sql)
        self.assertEqual(params[1:5], ("tenant-a", "Vendor", "SUPPLIER", 2))
    def test_rejects_missing_scope_without_db_access(self):
        for kwargs in ({"tenant_id":""}, {"domain":""}, {"target_object":""}):
            args=dict(tenant_id="a",domain="Vendor",target_object="SUPPLIER",embedding=[1.0])
            args.update(kwargs)
            with self.assertRaises(ValueError): retrieve_approved(Connection(), **args)
    def test_rejects_invalid_vectors(self):
        for vector in ([], [0,0], [float('nan')], [float('inf')], [True], ["1"], [1]*4097):
            with self.subTest(vector=str(vector)[:20]), self.assertRaises(ValueError):
                retrieve_approved(Connection(), tenant_id="a", domain="Vendor", target_object="SUPPLIER", embedding=vector)
    def test_rejects_invalid_limits(self):
        for limit in (0, 101, True, 1.5):
            with self.assertRaises(ValueError):
                retrieve_approved(Connection(), tenant_id="a", domain="Vendor", target_object="SUPPLIER", embedding=[1], limit=limit)
    def test_scope_injection_is_only_a_parameter(self):
        db=Connection()
        retrieve_approved(db, tenant_id="x' OR 1=1 --", domain="Vendor", target_object="SUPPLIER", embedding=[1])
        sql, params=db.c.executed
        self.assertNotIn("OR 1=1",sql)
        self.assertEqual(params[1],"x' OR 1=1 --")

if __name__ == '__main__': unittest.main()
