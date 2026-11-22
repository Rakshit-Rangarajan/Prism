"""Synthetic readiness gate tests; no enterprise or SAP access."""
import unittest
from app.readiness_rules import evaluate_readiness

def issue(identifier, domain="Vendor", severity="medium", state="open"):
    return {"id":identifier,"domain":domain,"severity":severity,"state":state}

class ReadinessGateTests(unittest.TestCase):
    def test_critical_blocks(self):
        r=evaluate_readiness([issue(1,severity="critical")])
        self.assertEqual(r["overall_gate"],"blocked")
        self.assertEqual(r["domain_gates"][0]["blocking_exception_ids"],[1])
    def test_high_blocks(self):
        self.assertEqual(evaluate_readiness([issue(1,severity="high")])["overall_gate"],"blocked")
    def test_rejected_and_reopened_remain_unresolved(self):
        r=evaluate_readiness([issue(1,severity="high",state="rejected"),issue(2,state="reopened")])
        self.assertEqual(r["domain_gates"][0]["unresolved"],2)
    def test_medium_requires_review(self):
        self.assertEqual(evaluate_readiness([issue(1)])["overall_gate"],"review_required")
    def test_approved_is_only_provisional(self):
        r=evaluate_readiness([issue(1,state="approved")])
        self.assertEqual(r["overall_gate"],"provisional")
        self.assertFalse(r["certified_sap_readiness"])
        self.assertTrue(r["missing_controls"])
    def test_empty_and_missing_domain_fail_closed(self):
        self.assertEqual(evaluate_readiness([])["overall_gate"],"unknown")
        r=evaluate_readiness([issue(1,state="approved")],expected_domains=["Vendor","Finance"])
        self.assertEqual(r["overall_gate"],"unknown")
        self.assertEqual(r["domain_gates"][0]["gate"],"unknown")
    def test_unrecognized_state_fails_closed(self):
        self.assertEqual(evaluate_readiness([issue(1,state="unexpected")])["overall_gate"],"unknown")
    def test_no_cross_domain_blocker_leakage(self):
        r=evaluate_readiness([issue(1,domain="Vendor",severity="critical"),issue(2,domain="Finance",state="approved")])
        by_domain={d["domain"]:d for d in r["domain_gates"]}
        self.assertEqual(by_domain["Finance"]["blocking_exception_ids"],[])
        self.assertEqual(by_domain["Vendor"]["blocking_exception_ids"],[1])

if __name__=="__main__":
    unittest.main()
