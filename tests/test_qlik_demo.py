import csv
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from app.erp_samples import generate
from scripts.prepare_qlik_demo import prepare


class QlikPackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        source = generate(self.root / 'processed-01.sqlite')
        audit = {'processed_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                 'reviewer': 'Automated synthetic rehearsal',
                 'before': {'issue_count': 786}, 'after': {'issue_count': 125}}
        with zipfile.ZipFile(self.root / 'processed-01.zip', 'w') as archive:
            archive.writestr('reconciliation.json', json.dumps(audit))
        (self.root / 'summary.json').write_text(json.dumps([
            {'batch': 1, 'before': 786, 'after': 125, 'quality_before': 42.46,
             'quality_after': 90.85, 'memory_matches': 0}]))

    def test_package_preserves_rows_and_only_intended_join_key(self):
        out = self.root / 'qlik'
        manifest = prepare(self.root, out)
        for table, expected in manifest['rows'].items():
            with (out / (table + '.csv')).open(encoding='utf-8', newline='') as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), expected)
        script = (out / 'PRISM.qvs').read_text()
        self.assertEqual(script.count('AS [vendor_id]'), 2)
        self.assertIn('AS [materials_currency_code]', script)
        self.assertIn('AS [invoices_currency_code]', script)
        with self.assertRaises(FileExistsError):
            prepare(self.root, out)

    def test_refuses_drift_before_creating_export(self):
        with (self.root / 'processed-01.sqlite').open('ab') as stream:
            stream.write(b'drift')
        out = self.root / 'qlik'
        with self.assertRaisesRegex(ValueError, 'unchanged processed data'):
            prepare(self.root, out)
        self.assertFalse(out.exists())
