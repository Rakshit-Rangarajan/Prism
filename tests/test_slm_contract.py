import unittest
from app.slm_contract import build_training_pair, resolve_selection

class ContractTests(unittest.TestCase):
    def example(self):
        return {'entry_id': 7, 'version': 2, 'input': {'title': 'Tax'}, 'output': {'recommendation': 'Review mapping', 'evidence': 'SYNTH-1'}}
    def test_schema(self):
        pair = build_training_pair(self.example())
        self.assertEqual(pair['output'], {'action': 'reuse_approved', 'evidence_id': 'candidate_1'})
        self.assertEqual(pair['input']['candidates'][0]['id'], pair['output']['evidence_id'])
    def test_provenance(self):
        pair = build_training_pair(self.example())
        self.assertEqual(resolve_selection(pair['output'], {'candidate_1': pair['provenance']}), {'entry_id': 7, 'version': 2})
    def test_invalid(self):
        example = self.example(); example['version'] = True
        with self.assertRaises(ValueError): build_training_pair(example)
    def test_abstain(self):
        self.assertIsNone(resolve_selection({'action': 'abstain', 'evidence_id': None}, {}))
    def test_unknown(self):
        with self.assertRaises(KeyError): resolve_selection({'action': 'reuse_approved', 'evidence_id': 'unknown'}, {})
