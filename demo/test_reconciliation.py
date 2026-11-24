"""Reconciliation regression tests for the offline PRISM ERP demo."""
import sqlite3
import unittest
from demo.reconciliation import reconcile


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.executescript("""
            CREATE TABLE lessons (
                signature TEXT, suggestion TEXT, approved INTEGER, occurrences INTEGER
            );
            CREATE TABLE migrated (customer_id TEXT);
            INSERT INTO lessons VALUES ('amount:legacy_format', 'Strip USD', 1, 3);
            INSERT INTO migrated VALUES ('C001');
        """)

    def tearDown(self):
        self.db.close()

    def test_counts_and_reused_approved_lesson(self):
        result = reconcile([
            {"status": "migrated", "record": {"customer_id": "C001"},
             "reused_lessons": ["amount:legacy_format"]},
            {"status": "rejected", "errors": ["amount:invalid"]},
            {"status": "validated", "record": {"customer_id": "C003"}},
        ], self.db)
        self.assertEqual(result["scenario_count"], 3)
        self.assertEqual(result["migrated_this_run"], 1)
        self.assertEqual(result["rejected_this_run"], 1)
        self.assertEqual(result["validated_only"], 1)
        self.assertEqual(result["target_total_records"], 1)
        self.assertTrue(result["reconciliation_passed"])
        self.assertEqual(result["approved_rule_reuse"]["amount:legacy_format"], 1)
        self.assertTrue(result["lessons"][0]["approved"])

    def test_duplicate_written_ids_fail_reconciliation(self):
        result = reconcile([
            {"status": "migrated", "record": {"customer_id": "C001"}},
            {"status": "migrated", "record": {"customer_id": "C001"}},
        ], self.db)
        self.assertFalse(result["reconciliation_passed"])
        self.assertEqual(result["unique_migrated_ids_this_run"], 1)

    def test_read_only_empty_run(self):
        result = reconcile([], self.db)
        self.assertEqual(result["scenario_count"], 0)
        self.assertEqual(result["target_total_records"], 1)
        self.assertTrue(result["reconciliation_passed"])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM lessons").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
