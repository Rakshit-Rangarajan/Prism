import unittest
from app.slm_output import validate_output


class OutputTests(unittest.TestCase):
    def test_reuse(self):
        self.assertEqual(validate_output('{"action":"reuse_approved","evidence_id":"v1"}', {'v1'})['action'], 'reuse_approved')
    def test_abstain(self):
        self.assertEqual(validate_output('{"action":"abstain","evidence_id":null}', set())['action'], 'abstain')
    def test_invalid(self):
        for raw in ('{}', '[]', 'not json', '{"action":"execute","evidence_id":null}', '{"action":"reuse_approved","evidence_id":"other"}', '{"action":"review","evidence_id":"v1"}', '{"action":"review","action":"abstain","evidence_id":null}', '{"action":"review","evidence_id":null,"sql":"DROP"}', ' '*8193):
            with self.subTest(raw=raw[:100]), self.assertRaises(ValueError):
                validate_output(raw, {'v1'})
