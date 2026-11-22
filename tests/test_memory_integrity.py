import unittest
from app.memory_integrity import evaluate_memory_integrity


def entry(identifier, state="approved", version=1, parent=None, domain="Vendor"):
    return {"id": identifier, "domain": domain, "target_object": "SUPPLIER",
            "state": state, "version": version, "supersedes_id": parent,
            "reviewer": "Reviewer" if state != "draft" else None,
            "reviewed_at": "2026-11-22" if state != "draft" else None}


class IntegrityTests(unittest.TestCase):
    def test_empty_catalog_is_valid(self):
        result = evaluate_memory_integrity([], [])
        self.assertTrue(result["ready_for_migration"])

    def test_valid_approved_revision(self):
        old = entry(1, "superseded")
        new = entry(2, "approved", 2, 1)
        result = evaluate_memory_integrity([old, new], [{"entry_id": 1}, {"entry_id": 2}])
        self.assertTrue(result["ready_for_migration"])

    def test_orphan_and_scope_leak(self):
        result = evaluate_memory_integrity([entry(1), entry(2, "draft", 2, 1, "Finance"),
                                            entry(3, "draft", 2, 999)], [])
        self.assertEqual({f["code"] for f in result["findings"]},
                         {"cross_scope_revision", "orphan_predecessor"})

    def test_parallel_drafts(self):
        rows = [entry(1), entry(2, "draft", 2, 1), entry(3, "draft", 2, 1)]
        self.assertIn("parallel_draft_successors",
                      [f["code"] for f in evaluate_memory_integrity(rows, [])["findings"]])

    def test_revision_cycle(self):
        a, b = entry(1, "approved", 2, 2), entry(2, "approved", 3, 1)
        self.assertIn("revision_cycle", [f["code"] for f in evaluate_memory_integrity([a, b], [])["findings"]])

    def test_orphan_event_and_missing_review(self):
        row = entry(1)
        row["reviewer"] = None
        result = evaluate_memory_integrity([row], [{"entry_id": 99}])
        self.assertEqual({f["code"] for f in result["findings"]},
                         {"orphan_event", "missing_review_metadata"})

    def test_competing_accepted_successors(self):
        rows = [entry(1, "superseded"), entry(2, "superseded", 2, 1), entry(3, "approved", 2, 1)]
        codes = [f["code"] for f in evaluate_memory_integrity(rows, [])["findings"]]
        self.assertIn("competing_accepted_successors", codes)

    def test_version_gap(self):
        result = evaluate_memory_integrity([entry(1), entry(2, "draft", 4, 1)], [])
        self.assertIn("version_gap", [f["code"] for f in result["findings"]])


if __name__ == "__main__":
    unittest.main()
