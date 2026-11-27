"""Source interchange and one-click evidence must remain consistent."""
import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from app.database_demo import sqlite_connection
from app.erp_samples import generate
from app.erp_rules import Rule, execute, quality
from scripts.export_erp_samples import export_samples, literal
from scripts.demo_report import render_report


class DemoDeliverableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_sqlite_dump_roundtrip_and_non_destructive_exports(self):
        manifest = export_samples(self.root)
        with sqlite_connection(':memory:') as db:
            db.executescript((self.root / 'prism-erp-sqlite.sql').read_text())
            for table, count in manifest['row_counts'].items():
                self.assertEqual(db.execute('SELECT count(*) FROM '+table).fetchone()[0], count)
            self.assertEqual(db.execute("SELECT count(*) FROM invoices WHERE posting_date='2026-02-30'").fetchone()[0], 8)
        mysql = (self.root/'prism-erp-mysql.sql').read_text()
        sqlserver = (self.root/'prism-erp-sqlserver.sql').read_text()
        self.assertIn('ENGINE=InnoDB', mysql)
        self.assertIn('THROW 50001', sqlserver)
        self.assertIn('NVARCHAR(255)', sqlserver)
        self.assertNotIn('DROP TABLE', mysql.upper())
        self.assertNotIn('DROP TABLE', sqlserver.upper())
        original = (self.root/'prism-erp-source.sqlite').read_bytes()
        with self.assertRaises(FileExistsError):
            export_samples(self.root)
        self.assertEqual(original, (self.root/'prism-erp-source.sqlite').read_bytes())
        self.assertEqual(literal("O'Brien", 'sqlserver'), "N'O''Brien'")

    def evidence(self):
        summaries = []
        for batch in (1, 2):
            source = generate(self.root/f'source-{batch:02d}.sqlite', batch)
            target = self.root/f'target-{batch:02d}.sqlite'
            target.write_bytes(source.read_bytes())
            with sqlite_connection(target) as db:
                before = quality(db)
                execute(db, [Rule(table='invoices', column='amount', operation='decimal_us', reason='Known US locale')])
                after = quality(db)
            audit = {'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'before': before, 'after': after}
            with zipfile.ZipFile(self.root/f'processed-{batch:02d}.zip', 'w') as archive:
                archive.writestr('reconciliation.json', json.dumps(audit))
                archive.write(target, 'prism-processed.sqlite')
            (self.root/f'plan-{batch:02d}.json').write_text('{}')
            summaries.append({'batch':batch,'before':before['issue_count'],'after':after['issue_count'],
                              'quality_before':before['quality_score'],'quality_after':after['quality_score'],
                              'memory_matches':batch-1,'inference':{'seconds':1},'mysql':False})
        (self.root/'summary.json').write_text(json.dumps(summaries))

    def test_report_packages_evidence_and_labels_simulated_approval(self):
        self.evidence()
        report = render_report(self.root)
        content = report.read_text(encoding='utf-8')
        self.assertIn('does not represent a human review', content)
        self.assertIn('does not train model weights', content)
        self.assertTrue((self.root/'evidence.zip').is_file())
        with zipfile.ZipFile(self.root/'evidence.zip') as archive:
            self.assertIn('source-01.sqlite', archive.namelist())
            self.assertIn('processed-02.zip', archive.namelist())

    def test_report_refuses_changed_source_or_missing_learning_sequence(self):
        self.evidence()
        source = self.root/'source-01.sqlite'
        source.write_bytes(source.read_bytes()+b'drift')
        with self.assertRaisesRegex(ValueError, 'Source drift'):
            render_report(self.root)
