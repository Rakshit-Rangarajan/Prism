"""Prepare local Qlik CSV inputs from a completed, synthetic PRISM rehearsal."""
import argparse
import csv
import hashlib
import json
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path


def prepare(run, output):
    run, output = Path(run).resolve(), Path(output).resolve()
    summaries = json.loads((run / 'summary.json').read_text(encoding='utf-8'))
    source = run / 'processed-01.sqlite'
    if not source.is_file() or not summaries:
        raise ValueError('A completed PRISM rehearsal is required')
    with zipfile.ZipFile(run / 'processed-01.zip') as archive:
        audit = json.loads(archive.read('reconciliation.json'))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != audit['processed_sha256'] or audit['reviewer'] != 'Automated synthetic rehearsal':
        raise ValueError('Expected unchanged processed data from a synthetic rehearsal')
    if summaries[0]['before'] != audit['before']['issue_count'] or summaries[0]['after'] != audit['after']['issue_count']:
        raise ValueError('Metrics do not match the processed database audit')
    output.mkdir(parents=True, exist_ok=False)
    script = ["// PRISM synthetic demonstration; approvals were simulated.",
              "// Create a folder connection named PRISM Demo pointing to this folder.",
              "SET DecimalSep='.';", "SET ThousandSep=',';"]
    counts = {}
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as db:
        for table in ('vendors', 'materials', 'invoices'):
            cursor = db.execute(f'SELECT * FROM "{table}"')
            fields = [column[0] for column in cursor.description]
            records = cursor.fetchall()
            with (output / f'{table}.csv').open('w', encoding='utf-8', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(fields)
                writer.writerows(records)
            counts[table] = len(records)
            aliases = []
            for field in fields:
                # Only the intended vendor relationship is shared across tables.
                alias = 'vendor_id' if (table == 'vendors' and field == 'id') or (table == 'invoices' and field == 'vendor_id') else f'{table}_{field}'
                aliases.append(f'    [{field}] AS [{alias}]')
            script.append(f'\n[{table}]:\nLOAD\n' + ',\n'.join(aliases) + f'\nFROM [lib://PRISM Demo/{table}.csv]\n(txt, utf8, embedded labels, delimiter is \',\', msq);')
    with (output / 'quality.csv').open('w', encoding='utf-8', newline='') as stream:
        writer = csv.writer(stream)
        writer.writerow(['Dataset', 'Stage', 'Findings', 'QualityScore', 'MemoryMatches'])
        for item in summaries:
            for stage in ('before', 'after'):
                writer.writerow([item['batch'], stage, item[stage], item[f'quality_{stage}'], item['memory_matches']])
    script.append("\n[Quality]:\nLOAD * FROM [lib://PRISM Demo/quality.csv]\n(txt, utf8, embedded labels, delimiter is ',', msq);")
    (output / 'PRISM.qvs').write_text('\n'.join(script) + '\n', encoding='utf-8')
    manifest = {'source_run': str(run), 'processed_sha256': digest,
                'datasets': len(summaries), 'rows': counts, 'synthetic': True,
                'first_dataset': {'before': summaries[0]['before'], 'after': summaries[0]['after']},
                'approval': 'simulated', 'qlik_cloud_connected': False}
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (output / 'README.txt').write_text(
        'PRISM local Qlik demo\n\nCreate an app in Qlik Sense Desktop. In Data load editor, create a Folder connection\n'
        'named PRISM Demo pointing to this folder. Paste PRISM.qvs and Load data.\n'
        'Suggested charts: Dataset vs Sum(Findings), colored by Stage; Dataset vs Avg(QualityScore), colored by Stage.\n'
        'Filter to Dataset=1 for the MySQL snapshot comparison. Vendors and invoices share vendor_id; materials is independent.\n'
        'Amounts with invalid values remain unresolved and must not be treated as zero.\n\n'
        'All data is synthetic. Steward approvals were simulated. This is a local file integration, not Qlik Cloud or Talend.\n'
        'Rerun prepare_qlik_demo for a new completed rehearsal; create a new output folder and update the Qlik folder connection.\n', encoding='utf-8')
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.run, args.output), indent=2))
