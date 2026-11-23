import contextlib
import unittest
from app.tenant_context import VerifiedIdentity, tenant_transaction, memory_rls_statements


class FakeConnection:
    def __init__(self):
        self.statements = []
        self.entered = False
        self.exited = False

    @contextlib.contextmanager
    def transaction(self):
        self.entered = True
        try:
            yield self
        finally:
            self.exited = True

    def execute(self, sql, params):
        self.statements.append((sql, params))


def principal(**changes):
    values = dict(tenant_id="tenant_123", subject_id="user:456", issuer="test-issuer", verified=True)
    values.update(changes)
    return VerifiedIdentity(**values)


class TenantBoundaryTests(unittest.TestCase):
    def test_reject_unverified_identity_before_transaction(self):
        c = FakeConnection()
        with self.assertRaises(PermissionError):
            with tenant_transaction(c, principal(verified=False)):
                pass
        self.assertFalse(c.entered)

    def test_reject_request_dictionary_instead_of_verified_claims(self):
        with self.assertRaises(PermissionError):
            with tenant_transaction(FakeConnection(), {"tenant_id": "victim"}):
                pass

    def test_reject_tenant_injection(self):
        for bad in ("x", "abc'; DROP TABLE memory_entries; --", "a b c", "", "équipe", "a"*65):
            with self.subTest(bad=bad):
                with self.assertRaises(PermissionError):
                    principal(tenant_id=bad).validate()

    def test_reject_missing_subject_and_issuer(self):
        for identity in (principal(subject_id=""), principal(issuer=""), principal(subject_id="a b")):
            with self.assertRaises(PermissionError):
                identity.validate()

    def test_parameterized_transaction_local_context(self):
        c = FakeConnection()
        with tenant_transaction(c, principal()):
            self.assertTrue(c.entered)
            self.assertEqual(len(c.statements), 2)
            self.assertEqual(c.statements[0][1], ("tenant_123",))
            self.assertEqual(c.statements[1][1], ("user:456",))
            self.assertTrue(all("set_config" in sql and "true" in sql for sql, _ in c.statements))
            self.assertTrue(all("tenant_123" not in sql for sql, _ in c.statements))
        self.assertTrue(c.exited)

    def test_transaction_exits_on_failure(self):
        c = FakeConnection()
        with self.assertRaisesRegex(RuntimeError, "failure"):
            with tenant_transaction(c, principal()):
                raise RuntimeError("failure")
        self.assertTrue(c.exited)

    def test_rls_is_forced_and_fails_closed_when_setting_missing(self):
        statements = memory_rls_statements()
        self.assertIn("ENABLE ROW LEVEL SECURITY", statements[0])
        self.assertIn("FORCE ROW LEVEL SECURITY", statements[1])
        self.assertIn("current_setting('prism.tenant_id', true)", statements[3])
        self.assertIn("WITH CHECK", statements[3])
        self.assertIn("tenant_id =", statements[3])

    def test_rls_rejects_arbitrary_table_name(self):
        with self.assertRaises(ValueError):
            memory_rls_statements("memory_entries; DROP TABLE audit")
        for table in ("memory_entries", "memory_events", "migration_memory_vectors"):
            self.assertEqual(len(memory_rls_statements(table)), 4)


if __name__ == "__main__":
    unittest.main()
