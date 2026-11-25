import unittest
from app.slm_training_export import export_examples

class ExportTests(unittest.TestCase):
    def row(self, **changes):
        return dict(dict(id=1,version=1,tenant_id='a',state='approved',reviewer='r',reviewed_at='now',domain='ERP',target_object='vendor',title='Tax mapping',resolution='Use approved mapping',evidence='SYNTH-1'), **changes)
    def test_approved_only(self):
        self.assertEqual(export_examples([self.row(),self.row(id=2,state='draft'),self.row(id=3,state='superseded')],'a')['count'],1)
    def test_cross_tenant(self):
        with self.assertRaises(PermissionError): export_examples([self.row(tenant_id='b',state='draft')],'a')
    def test_provenance(self):
        with self.assertRaises(ValueError): export_examples([self.row(reviewer='')],'a')
    def test_determinism(self):
        a,b=self.row(),self.row(id=2)
        self.assertEqual(export_examples([a,b],'a'),export_examples([b,a],'a'))
    def test_duplicate(self):
        with self.assertRaises(ValueError): export_examples([self.row(),self.row()],'a')
    def test_invalid_version(self):
        with self.assertRaises(ValueError): export_examples([self.row(version=True)],'a')
