"""Approval boundary, company isolation and deterministic ERP execution."""
import hashlib
import io
import json
import os
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.server import app
from app.erp_rules import Advice, Rule, execute, quality
from app.erp_samples import generate
from app.database_demo import sqlite_connection


class CompanyLearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {'PRISM_COMPANY_ROOT': self.tmp.name, 'PRISM_COMPANY_ID': 'company-a', 'PRISM_DEMO_PASSWORD': 'synthetic-test-password'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.auth = ('prism', 'synthetic-test-password')
        self.source = generate(Path(self.tmp.name) / 'source.sqlite').read_bytes()
        self.rule = Rule(table='invoices', column='amount', operation='decimal_us', reason='Approved US locale')
        self.advice = Advice(summary='Normalize known source format', rules=[self.rule], risks=['Invalid dates require review'])

    def plan(self):
        with patch('app.company_learning.inference', return_value=(self.advice, {'model': 'test-double', 'seconds': 0})):
            response = self.client.post('/api/local/recommend', content=self.source, auth=self.auth)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def approval(self, plan, **kwargs):
        body = dict(source_sha256=plan['source_sha256'], rules=plan['advice']['rules'], reviewer='Test steward',
                    note='Reviewed synthetic data only', confirmation='APPROVE TRANSFORMATIONS')
        body.update(kwargs)
        return self.client.post(f"/api/local/plans/{plan['plan_id']}/approve", json=body, auth=self.auth)

    def test_approval_export_retrieval_and_isolation(self):
        plan = self.plan()
        route = f"/api/local/plans/{plan['plan_id']}/export"
        self.assertEqual(self.client.post(route, auth=self.auth).status_code, 409)
        self.assertEqual(self.approval(plan, source_sha256='0'*64).status_code, 409)
        self.assertEqual(self.approval(plan).status_code, 200)
        self.assertEqual(self.approval(plan).status_code, 409)
        result = self.client.post(route, auth=self.auth)
        self.assertEqual(result.status_code, 200, result.text[:100])
        with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
            report = json.loads(archive.read('reconciliation.json'))
            self.assertLess(report['after']['issue_count'], report['before']['issue_count'])
            self.assertEqual(report['source_sha256'], hashlib.sha256(self.source).hexdigest())
            self.assertEqual(report['before']['orphan_invoices'], report['after']['orphan_invoices'])
        replay = self.client.post('/api/local/recommend?mode=retrieval', content=self.source, auth=self.auth).json()
        self.assertEqual(len(replay['provenance']['retrieved_ids']), 1)
        self.assertFalse(replay['approved'])
        with patch.dict(os.environ, {'PRISM_COMPANY_ID': 'company-b'}):
            self.assertEqual(self.client.post(route, auth=self.auth).status_code, 404)
            self.assertEqual(self.client.get('/api/local/memory', auth=self.auth).json()['corrections'], [])
            self.assertEqual(self.client.post('/api/local/recommend?mode=retrieval', content=self.source, auth=self.auth).status_code, 409)

    def test_human_correction_rejects_sql_protected_columns_and_unknown_ops(self):
        plan = self.plan()
        for bad in [dict(self.rule.model_dump(), sql='DROP TABLE invoices'),
                    dict(self.rule.model_dump(), column='id'),
                    dict(self.rule.model_dump(), operation='execute_sql')]:
            self.assertEqual(self.approval(plan, rules=[bad]).status_code, 422)
        corrected = dict(self.rule.model_dump(), operation='trim', reason='Steward chose trim only')
        self.assertEqual(self.approval(plan, rules=[corrected]).status_code, 200)
        memory = self.client.get('/api/local/memory', auth=self.auth).json()
        self.assertEqual(json.loads(memory['corrections'][0]['rule'])['operation'], 'trim')

    def test_model_endpoint_must_be_local_and_authenticated(self):
        self.assertEqual(self.client.get('/api/local/status').status_code, 401)
        with patch.dict(os.environ, {'PRISM_SLM_URL': 'https://remote.example/v1'}):
            response = self.client.post('/api/local/recommend', content=self.source, auth=self.auth)
            self.assertEqual(response.status_code, 503)

    def test_twenty_sources_differ_and_keep_review_only_findings(self):
        digests = set()
        for batch in range(1, 21):
            path = generate(Path(self.tmp.name) / f'batch-{batch}.sqlite', batch)
            digests.add(hashlib.sha256(path.read_bytes()).hexdigest())
            with sqlite_connection(path) as db:
                before = quality(db)
                execute(db, [self.rule])
                after = quality(db)
                self.assertLess(after['issue_count'], before['issue_count'])
                self.assertEqual(after['orphan_invoices'], before['orphan_invoices'])
                self.assertEqual(after['duplicate_candidates'], before['duplicate_candidates'])
        self.assertEqual(len(digests), 20)

    def test_crosswalk_precedes_uppercase_even_when_retrieval_reorders_rules(self):
        rules = [Rule(table='materials', column='uom', operation='uppercase', reason='Normalize unit code'),
                 Rule(table='materials', column='uom', operation='map_values', mapping={'pieces': 'EA'}, reason='Approved crosswalk')]
        with sqlite_connection(':memory:') as db:
            db.execute('CREATE TABLE materials(id INTEGER PRIMARY KEY,uom TEXT)')
            db.execute("INSERT INTO materials VALUES(1,'pieces')")
            execute(db, rules)
            self.assertEqual(db.execute('SELECT uom FROM materials').fetchone()[0], 'EA')
            execute(db, rules)
            self.assertEqual(db.execute('SELECT uom FROM materials').fetchone()[0], 'EA')


if __name__ == '__main__':
    unittest.main()
