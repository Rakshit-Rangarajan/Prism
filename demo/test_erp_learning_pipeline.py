"""Offline regression tests for the ERP learning demo."""
import tempfile
import unittest
from pathlib import Path
from demo.erp_learning_pipeline import Demo, SCENARIOS


class LearningDemoTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "demo.sqlite"
        self.demo = Demo(self.path)

    def tearDown(self):
        self.demo.db.close()
        self.temp.cleanup()

    def test_twenty_scenarios(self):
        self.assertEqual(len(SCENARIOS), 20)
        self.assertEqual(len(self.demo.run()), 20)

    def test_dry_run_does_not_write_target(self):
        self.demo.run()
        self.assertEqual(self.demo.db.execute(
            "SELECT count(*) FROM migrated").fetchone()[0], 0)

    def test_lesson_requires_approval(self):
        first = self.demo.migrate("currency_symbol", 4, apply=True)
        self.assertIn("amount:legacy_format", first["errors"])
        self.assertTrue(self.demo.approve("amount:legacy_format"))
        second = self.demo.migrate("repeated_known_error", 5, apply=True)
        self.assertEqual(second["status"], "migrated")
        self.assertIn("amount:legacy_format", second["reused_lessons"])

    def test_persistent_memory(self):
        self.demo.migrate("currency_symbol", 4)
        self.demo.approve("amount:legacy_format")
        self.demo.db.close()
        self.demo = Demo(self.path)
        result = self.demo.migrate("repeated_known_error", 5)
        self.assertEqual(result["status"], "validated")

    def test_duplicate_is_rejected(self):
        self.demo.migrate("clean", 1, apply=True)
        result = self.demo.migrate("duplicate_id", 6, apply=True)
        self.assertEqual(result["errors"], ["customer_id:duplicate"])


if __name__ == "__main__":
    unittest.main()
