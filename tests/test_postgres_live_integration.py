"""Explicitly opt-in tests against a disposable PostgreSQL+pgvector database.

Runs only when PRISM_INTEGRATION_TEST=1. Never runs against production implicitly.
Requires a DB whose name is exactly prism_integration_test, on loopback.
"""
import os
import unittest
from urllib.parse import urlsplit

from scripts.pgvector_smoke import inspect_vector_connection
from scripts.postgres_preflight import inspect_connection


def _integration_dsn():
    if os.getenv("PRISM_INTEGRATION_TEST") != "1":
        return None
    dsn = os.getenv("PRISM_INTEGRATION_DSN", "")
    if not dsn:
        raise RuntimeError("Explicit PRISM_INTEGRATION_DSN is required")
    parsed = urlsplit(dsn)
    if parsed.scheme not in ("postgres", "postgresql"):
        raise RuntimeError("Only PostgreSQL URLs are allowed for disposable tests")
    if parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise RuntimeError("Integration tests must use a loopback database")
    if parsed.path != "/prism_integration_test":
        raise RuntimeError("Database must be named prism_integration_test")
    return dsn


class DisposablePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = _integration_dsn()
        if cls.dsn is None:
            raise unittest.SkipTest("Disposable PostgreSQL integration not opted in")
        try:
            import psycopg
        except ImportError:
            raise unittest.SkipTest("Install psycopg[binary] locally for integration testing")
        cls.psycopg = psycopg

    def connect(self):
        return self.psycopg.connect(self.dsn, connect_timeout=5)

    def test_pgvector_real_operator_and_read_only_transaction(self):
        with self.connect() as conn:
            # Test-only extension installation; explicit isolated DB.
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.commit()
            report = inspect_vector_connection(conn)
            self.assertEqual(report["status"], "passed")
            self.assertTrue(report["read_only"])
            self.assertFalse(report["semantic_retrieval_ready"])
            self.assertAlmostEqual(report["identical_cosine_distance"], 0, places=6)
            self.assertAlmostEqual(report["orthogonal_cosine_distance"], 1, places=6)

    def test_postgres_preflight_is_metadata_only(self):
        with self.connect() as conn:
            report = inspect_connection(conn)
            self.assertTrue(report["postgres_supported"])
            self.assertTrue(report["pgvector_installed"])
            self.assertTrue(report["empty_migration_target"])
            self.assertFalse(report["ready_for_semantic_retrieval"])

    def test_read_only_transaction_refuses_mutation(self):
        with self.connect() as conn:
            with self.assertRaises(self.psycopg.errors.ReadOnlySqlTransaction):
                with conn.transaction():
                    conn.execute("SET TRANSACTION READ ONLY")
                    conn.execute("CREATE TABLE prism_forbidden_write (id int)")
            conn.rollback()
            exists = conn.execute("SELECT to_regclass('public.prism_forbidden_write')").fetchone()[0]
            self.assertIsNone(exists)

    def test_wrong_database_and_remote_host_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError, "loopback"):
            with unittest.mock.patch.dict(os.environ, {
                "PRISM_INTEGRATION_TEST": "1",
                "PRISM_INTEGRATION_DSN": "postgresql://u:p@production.example/prism_integration_test",
            }):
                _integration_dsn()
        with self.assertRaisesRegex(RuntimeError, "prism_integration_test"):
            with unittest.mock.patch.dict(os.environ, {
                "PRISM_INTEGRATION_TEST": "1",
                "PRISM_INTEGRATION_DSN": "postgresql://u:p@127.0.0.1/enterprise",
            }):
                _integration_dsn()


if __name__ == "__main__":
    unittest.main()
