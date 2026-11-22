import contextlib
import unittest
from unittest.mock import patch
from io import StringIO
from scripts.pgvector_smoke import inspect_vector_connection, synthetic_vector, inspect_postgres, main

class Cursor:
    def __init__(self,value):self.value=value
    def fetchone(self):return (self.value,)

class FakeConnection:
    def __init__(self,installed=True,distances=(0.0,1.0)):
        self.installed=installed
        self.distances=iter(distances)
        self.queries=[]
    @contextlib.contextmanager
    def transaction(self):yield self
    def execute(self,sql,params=None):
        self.queries.append((sql,params))
        if sql=="SET TRANSACTION READ ONLY":return Cursor(None)
        if "pg_catalog.pg_extension" in sql:return Cursor(self.installed)
        if "<=>" in sql:
            self.test_vectors(params)
            return Cursor(next(self.distances))
        raise AssertionError("Unexpected SQL")
    def test_vectors(self,params):
        self_test=unittest.TestCase()
        self_test.assertEqual(len(params),2)
        for vector in params:
            self_test.assertEqual(len(vector.strip("[]").split(",")),384)

class VectorSmokeTests(unittest.TestCase):
    def test_synthetic_vector_is_exactly_384_dimensions(self):
        self.assertEqual(len(synthetic_vector(0).strip("[]").split(",")),384)
        self.assertEqual(synthetic_vector(383).count("1"),1)
        with self.assertRaises(ValueError):synthetic_vector(384)
    def test_success_is_read_only_and_not_semantic_ready(self):
        conn=FakeConnection()
        report=inspect_vector_connection(conn)
        self.assertEqual(report["status"],"passed")
        self.assertFalse(report["semantic_retrieval_ready"])
        self.assertEqual(conn.queries[0][0],"SET TRANSACTION READ ONLY")
        self.assertEqual(sum("<=>" in sql for sql,_ in conn.queries),2)
        self.assertTrue(all(not sql.upper().startswith(("CREATE","DROP","INSERT","UPDATE","DELETE","ALTER")) for sql,_ in conn.queries))
    def test_missing_extension_fails_closed(self):
        conn=FakeConnection(installed=False)
        self.assertEqual(inspect_vector_connection(conn)["reason"],"pgvector_not_installed")
        self.assertEqual(len(conn.queries),2)
    def test_wrong_distance_fails(self):
        report=inspect_vector_connection(FakeConnection(distances=(0.1,0.7)))
        self.assertEqual(report["status"],"failed")
    def test_missing_dsn_does_not_attempt_driver_import(self):
        with self.assertRaisesRegex(ValueError,"PRISM_POSTGRES_DSN"):inspect_postgres("")
    def test_cli_redacts_driver_errors(self):
        with patch("scripts.pgvector_smoke.inspect_postgres",side_effect=RuntimeError("password=SECRET host=private")):
            with patch("sys.stdout",new_callable=StringIO) as output:
                self.assertEqual(main([]),2)
            self.assertNotIn("SECRET",output.getvalue())
            self.assertNotIn("private",output.getvalue())

if __name__=="__main__":unittest.main()
