"""Real local-model/MySQL demo evidence. Requires a running loopback model.

Creates isolated synthetic company storage under --output and never approves
real company data. The explicit CLI invocation represents demo steward approval.
"""
import argparse
import hashlib
import io
import json
import os
import sqlite3
import zipfile
from pathlib import Path
from contextlib import closing


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mysql', action='store_true')
    parser.add_argument('--model-batches', type=int, default=2)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['PRISM_COMPANY_ID'] = 'synthetic-validation'
    os.environ['PRISM_COMPANY_ROOT'] = str(out / 'companies')
    os.environ['PRISM_DB'] = str(out / 'application.sqlite')
    os.environ['PRISM_ERP_DEMO_DB'] = str(out / 'legacy-demo.sqlite')
    os.environ.setdefault('PRISM_DEMO_PASSWORD', 'synthetic-local-test')
    os.environ.setdefault('PRISM_SLM_URL', 'http://127.0.0.1:8092/v1')
    os.environ.setdefault('PRISM_SLM_MODEL', 'qwen3-4b')
    from fastapi.testclient import TestClient
    from app.server import app
    from app.erp_samples import generate
    auth = ('prism', os.environ['PRISM_DEMO_PASSWORD'])
    reports = []
    with TestClient(app) as client:
        def checked(response):
            if response.status_code != 200:
                raise RuntimeError(f'{response.status_code}: {response.text[:1000]}')
            return response

        for batch in range(1, 21):
            source = out / f'source-{batch:02d}.sqlite'
            generate(source, batch)
            data = source.read_bytes()
            mysql_verified = False
            if batch == 1 and args.mysql:
                data = checked(client.post('/api/demo/database/mysql/snapshot', auth=auth)).content
                (out / 'mysql-snapshot.sqlite').write_bytes(data)
                mysql_verified = True
            mode = 'model' if batch <= args.model_batches else 'retrieval'
            plan = checked(client.post('/api/local/recommend?mode=' + mode, content=data, auth=auth)).json()
            (out / f'plan-{batch:02d}.json').write_text(json.dumps(plan, indent=2))
            assert not plan['approved']
            assert client.post(f"/api/local/plans/{plan['plan_id']}/export", auth=auth).status_code == 409
            checked(client.post(f"/api/local/plans/{plan['plan_id']}/approve", auth=auth, json={
                'source_sha256': plan['source_sha256'], 'rules': plan['advice']['rules'],
                'reviewer': 'Synthetic demo steward', 'note': 'Approved synthetic-only migration rules for benchmark replay.',
                'confirmation': 'APPROVE TRANSFORMATIONS'}))
            result = checked(client.post(f"/api/local/plans/{plan['plan_id']}/export", auth=auth)).content
            (out / f'processed-{batch:02d}.zip').write_bytes(result)
            with zipfile.ZipFile(io.BytesIO(result)) as archive:
                report = json.loads(archive.read('reconciliation.json'))
                target = out / f'processed-{batch:02d}.sqlite'
                target.write_bytes(archive.read('prism-processed.sqlite'))
            assert hashlib.sha256(data).hexdigest() == report['source_sha256']
            assert report['after']['issue_count'] < report['before']['issue_count']
            assert [t['rows'] for t in report['before']['tables']] == [t['rows'] for t in report['after']['tables']]
            with closing(sqlite3.connect(target)) as db:
                assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
            assert source.read_bytes() == data or mysql_verified
            summary = {'batch': batch, 'method': mode, 'mysql': mysql_verified,
                       'before': report['before']['issue_count'], 'after': report['after']['issue_count'],
                       'quality_before': report['before']['quality_score'], 'quality_after': report['after']['quality_score'],
                       'memory_matches': len(plan['provenance']['retrieved_ids']), 'inference': plan['provenance']['inference']}
            reports.append(summary)
            print(json.dumps(summary), flush=True)
            (out / 'summary.json').write_text(json.dumps(reports, indent=2))


if __name__ == '__main__':
    main()
