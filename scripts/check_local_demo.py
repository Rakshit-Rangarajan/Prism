"""Verify model/data identity, live API and actual read-only MySQL access."""
import hashlib
import json
import os
from pathlib import Path
import httpx
import pymysql


def main():
    local = Path(__file__).resolve().parents[1] / '.local'
    settings = json.loads((local / 'settings.json').read_text())
    manifest = json.loads((local / 'artifacts.json').read_text())
    for item in [manifest['model'], *manifest['datasets']]:
        if hashlib.sha256(Path(item['path']).read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Artifact drift: ' + item['path'])
    auth = ('prism', settings['demoPassword'])
    with httpx.Client(base_url='http://127.0.0.1:8091', auth=auth, timeout=15, trust_env=False) as client:
        health = client.get('/api/health'); health.raise_for_status()
        status = client.get('/api/local/status'); status.raise_for_status()
        status = status.json()
        assert status['company'] == settings['company'] and status['inference_online']
        source = client.post('/api/demo/database/mysql/snapshot'); source.raise_for_status()
        assert source.content.startswith(b'SQLite format 3\0')
    env = dict(line.split('=', 1) for line in (local / 'mysql.env').read_text().splitlines() if '=' in line)
    with pymysql.connect(host='127.0.0.1', port=3307, user='prism_reader', password=env['MYSQL_PASSWORD'], database='prism_erp') as db:
        with db.cursor() as cur:
            cur.execute('SELECT COUNT(*) FROM vendors')
            assert cur.fetchone()[0] == 81
            try:
                cur.execute("UPDATE vendors SET name=name WHERE id=-1")
            except pymysql.err.OperationalError as exc:
                assert exc.args[0] in (1142, 1143)
            else:
                raise AssertionError('MySQL reader unexpectedly has UPDATE privilege')
    print(json.dumps({'ready': True, 'verified_datasets': 20, 'model_hash_verified': True,
                      'mysql_read_only_verified': True, 'company': status['company'], 'model': status['model'],
                      'approved_corrections': status['approved_corrections']}))


if __name__ == '__main__':
    main()
