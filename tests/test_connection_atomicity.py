"""Regression tests: failed governance operations must never persist partial writes."""
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from app import server


class ConnectionAtomicityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.database = str(Path(self.tmp.name) / "memory.sqlite3")
        self.db_patch = patch.object(server, "DB", self.database)
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)
        with server.connection() as conn:
            conn.execute("CREATE TABLE governance (id INTEGER PRIMARY KEY, decision TEXT)")

    def rows(self):
        with closing(sqlite3.connect(self.database)) as conn:
            return conn.execute("SELECT decision FROM governance ORDER BY id").fetchall()

    def test_success_commits(self):
        with server.connection() as conn:
            conn.execute("INSERT INTO governance(decision) VALUES (?)", ("approved",))
        self.assertEqual(self.rows(), [("approved",)])

    def test_exception_rolls_back_implicit_transaction(self):
        with self.assertRaisesRegex(ValueError, "review failed"):
            with server.connection() as conn:
                conn.execute("INSERT INTO governance(decision) VALUES (?)", ("unreviewed",))
                raise ValueError("review failed")
        self.assertEqual(self.rows(), [])

    def test_exception_rolls_back_explicit_immediate_transaction(self):
        with self.assertRaisesRegex(RuntimeError, "audit failed"):
            with server.connection() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute("INSERT INTO governance(decision) VALUES (?)", ("approved",))
                raise RuntimeError("audit failed")
        self.assertEqual(self.rows(), [])

    def test_failed_second_write_cannot_leave_first_write(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with server.connection() as conn:
                conn.execute("INSERT INTO governance(id,decision) VALUES (1,'approved')")
                conn.execute("INSERT INTO governance(id,decision) VALUES (1,'duplicate')")
        self.assertEqual(self.rows(), [])

    def test_prior_committed_records_survive_failed_transaction(self):
        with server.connection() as conn:
            conn.execute("INSERT INTO governance(decision) VALUES ('existing')")
        with self.assertRaises(ValueError):
            with server.connection() as conn:
                conn.execute("INSERT INTO governance(decision) VALUES ('failed')")
                raise ValueError("abort")
        self.assertEqual(self.rows(), [("existing",)])


if __name__ == "__main__":
    unittest.main()
