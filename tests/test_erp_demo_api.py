"""Isolated ERP demo API tests. No Render, enterprise data or network."""
import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app import erp_demo


class DemoApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.override = patch.dict(os.environ, {
            "PRISM_ERP_DEMO_DB": os.path.join(self.tmp.name, "synthetic.sqlite")
        })
        self.override.start()

    def tearDown(self):
        self.override.stop()
        self.tmp.cleanup()

    def test_scenarios_are_synthetic_and_bounded(self):
        response = erp_demo.scenarios()
        self.assertTrue(response["synthetic"])
        self.assertEqual(response["count"], 20)
        self.assertEqual(len(response["scenarios"]), 20)

    def test_preview_does_not_write_target(self):
        response = erp_demo.run_demo(erp_demo.RunRequest(apply=False))
        self.assertEqual(response["mode"], "preview")
        self.assertEqual(response["reconciliation"]["target_total_records"], 0)

    def test_approve_only_after_discovery_and_confirmation(self):
        with self.assertRaises(HTTPException):
            erp_demo.approve_lesson(erp_demo.ApprovalRequest(
                signature="amount:legacy_format", confirmation="APPROVE SYNTHETIC RULE"))
        erp_demo.run_demo(erp_demo.RunRequest())
        with self.assertRaises(HTTPException):
            erp_demo.approve_lesson(erp_demo.ApprovalRequest(
                signature="amount:legacy_format", confirmation=""))
        with self.assertRaises(HTTPException):
            erp_demo.approve_lesson(erp_demo.ApprovalRequest(
                signature="email:invalid", confirmation="APPROVE SYNTHETIC RULE"))
        result = erp_demo.approve_lesson(erp_demo.ApprovalRequest(
            signature="amount:legacy_format", confirmation="APPROVE SYNTHETIC RULE"))
        self.assertTrue(result["approved"])
        self.assertTrue(erp_demo.lessons()["lessons"])

    def test_reset_requires_confirmation_and_clears_only_demo_state(self):
        erp_demo.run_demo(erp_demo.RunRequest(apply=True))
        before = erp_demo.lessons()["lessons"]
        self.assertGreater(len(before), 0)
        with self.assertRaises(HTTPException):
            erp_demo.reset_demo(erp_demo.ResetRequest(confirmation="RESET"))
        response = erp_demo.reset_demo(
            erp_demo.ResetRequest(confirmation="RESET SYNTHETIC DEMO"))
        self.assertTrue(response["synthetic"])
        self.assertEqual(erp_demo.lessons()["lessons"], [])
        after = erp_demo.run_demo(erp_demo.RunRequest(apply=False))
        self.assertEqual(after["reconciliation"]["target_total_records"], 0)

    def test_replay_uses_persisted_approved_lesson(self):
        erp_demo.run_demo(erp_demo.RunRequest())
        erp_demo.approve_lesson(erp_demo.ApprovalRequest(
            signature="amount:legacy_format", confirmation="APPROVE SYNTHETIC RULE"))
        result = erp_demo.run_demo(erp_demo.RunRequest(apply=True))
        self.assertGreater(result["reconciliation"]["migrated_this_run"], 0)
        self.assertGreater(result["reconciliation"]["approved_rule_reuse"]["amount:legacy_format"], 0)


if __name__ == "__main__":
    unittest.main()
