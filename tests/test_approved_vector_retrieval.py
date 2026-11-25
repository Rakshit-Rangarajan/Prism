import unittest
from app.approved_vector_retrieval import retrieve_approved

class ApprovedVectorRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.scope = dict(tenant_id="tenant-a", domain="erp", target_object="vendor", dimensions=2)

    def record(self, identifier, vector, **changes):
        record = dict(id=identifier, tenant_id="tenant-a", domain="erp", target_object="vendor",
                      state="approved", superseded=False, vector=vector)
        record.update(changes)
        return record

    def test_cosine_ranking_and_limit(self):
        records = [self.record(1, [0, 1]), self.record(2, [2, 0]), self.record(3, [1, 1])]
        self.assertEqual([r["id"] for r in retrieve_approved([1, 0], records, **self.scope, limit=2)], [2, 3])

    def test_never_returns_other_tenants_or_unapproved_or_old_versions(self):
        records = [self.record(1, [1, 0], tenant_id="tenant-b"), self.record(2, [1, 0], state="draft"),
                   self.record(3, [1, 0], superseded=True), self.record(4, [1, 0], domain="finance"),
                   self.record(5, [1, 0], target_object="customer"), self.record(6, [0, 1])]
        self.assertEqual([r["id"] for r in retrieve_approved([1, 0], records, **self.scope)], [6])

    def test_missing_scope_fails_closed(self):
        for key in ("tenant_id", "domain", "target_object"):
            with self.assertRaises(ValueError):
                retrieve_approved([1, 0], [], **dict(self.scope, **{key: ""}))

    def test_invalid_vectors_fail_closed(self):
        for vector in ([0, 0], [float("nan"), 1], [float("inf"), 1], [1], [True, 0]):
            with self.assertRaises(ValueError):
                retrieve_approved(vector, [], **self.scope)
        with self.assertRaises(ValueError):
            retrieve_approved([1, 0], [self.record(1, [0, 0])], **self.scope)

    def test_invalid_limits_fail_closed(self):
        for limit in (0, 101, True):
            with self.assertRaises(ValueError):
                retrieve_approved([1, 0], [], **self.scope, limit=limit)

    def test_does_not_mutate_records(self):
        record = self.record(1, [1, 0])
        retrieve_approved([1, 0], [record], **self.scope)
        self.assertEqual(record["vector"], [1, 0])
        self.assertNotIn("cosine_similarity", record)
