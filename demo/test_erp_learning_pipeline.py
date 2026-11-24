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

    def test_preview_detects_duplicate_within_source_batch(self):
        results = self.demo.run(apply=False)
        duplicate = next(r for r in results if r["scenario"] == "duplicate_id")
        self.assertEqual(duplicate["errors"], ["customer_id:duplicate"])
        self.assertEqual(self.demo.db.execute("SELECT COUNT(*) FROM migrated").fetchone()[0], 0)

    def test_nonfinite_amounts_fail_closed(self):
        from unittest.mock import patch
        with patch("demo.erp_learning_pipeline.sample", return_value={
            "customer_id": "C777", "name": "Demo", "email": "test@example.com",
            "amount": "NaN"
        }):
            result = self.demo.migrate("clean", 777, apply=True)
        self.assertIn("amount:non_finite", result["errors"])
        self.assertEqual(self.demo.db.execute("SELECT COUNT(*) FROM migrated").fetchone()[0], 0)

    def test_first_run_fails_and_approved_replay_improves_outcome(self):
        before = self.demo.run(apply=False)
        initial_rejections = sum(r["status"] == "rejected" for r in before)
        initial_formats = [
            r for r in before if "amount:legacy_format" in r.get("errors", [])
        ]
        self.assertEqual(len(initial_formats), 3)
        self.assertTrue(self.demo.approve("amount:legacy_format"))
        after = self.demo.run(apply=True)
        final_rejections = sum(r["status"] == "rejected" for r in after)
        self.assertLess(final_rejections, initial_rejections)
        corrected = [
            r for r in after
            if "amount:legacy_format" in r.get("reused_lessons", [])
        ]
        self.assertEqual(len(corrected), 3)
        self.assertTrue(all(r["status"] == "migrated" for r in corrected))
        self.assertEqual(self.demo.report(after)["migrated_this_run"],
                         self.demo.report(after)["target_total_records"])

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
