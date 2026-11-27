"""Self-contained, offline demo report and evidence package. No browser login needed."""
import argparse
import base64
import hashlib
import html
import io
import json
import zipfile
from pathlib import Path


def render_report(folder):
    folder = Path(folder).resolve()
    summaries = json.loads((folder / 'summary.json').read_text(encoding='utf-8'))
    if len(summaries) < 2:
        raise ValueError('A learning demonstration needs at least two completed datasets')
    for item in summaries:
        batch = item['batch']
        with zipfile.ZipFile(folder / f'processed-{batch:02d}.zip') as archive:
            audit = json.loads(archive.read('reconciliation.json'))
            source = folder / f'source-{batch:02d}.sqlite'
            if hashlib.sha256(source.read_bytes()).hexdigest() != audit['source_sha256']:
                raise ValueError('Source drift detected in completed demo')
            before_rows = {t['table']: t['rows'] for t in audit['before']['tables']}
            after_rows = {t['table']: t['rows'] for t in audit['after']['tables']}
            if before_rows != after_rows or item['after'] >= item['before']:
                raise ValueError('Demo reconciliation failed')
    if summaries[0]['memory_matches'] != 0 or summaries[1]['memory_matches'] < 1:
        raise ValueError('Fresh-memory learning sequence was not demonstrated')
    first, second = summaries[:2]
    logo = Path(__file__).resolve().parents[1] / 'frontend/src/assets/prism-logo.png'
    logo_html = '<h1>PRISM</h1>'
    if logo.exists():
        logo_html = '<img class="logo" alt="PRISM" src="data:image/png;base64,' + base64.b64encode(logo.read_bytes()).decode('ascii') + '">'
    def link(name, label):
        return '<a href="' + html.escape((folder / name).as_uri(), quote=True) + '">' + html.escape(label) + '</a>'
    rows = []
    for item in summaries:
        mode = 'Local SLM' if item['inference'] else 'Approved retrieval'
        timing = f"{item['inference']['seconds']:.1f}s" if item['inference'] else 'No inference'
        batch = item['batch']
        rows.append(f"<tr><td>{batch:02d}</td><td>{mode}</td><td>{item['memory_matches']}</td><td>{item['before']} &rarr; {item['after']}</td><td>{item['quality_after']:.2f}%</td><td>{timing}</td><td>{link(f'processed-{batch:02d}.zip', 'Download')}</td></tr>")
    total_before = sum(x['before'] for x in summaries)
    total_after = sum(x['after'] for x in summaries)
    content = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PRISM Demo Results</title><style>
    *{box-sizing:border-box}body{margin:0;background:#091321;color:#e4edfa;font-family:Segoe UI,Arial,sans-serif}main{max-width:1120px;margin:auto;padding:35px 26px 70px}.logo{width:min(100%,500px);height:auto;display:block;margin:0 auto 25px;border-radius:12px}.eyebrow{color:#afbbff;font-size:12px;letter-spacing:1.5px;font-weight:700}h1{font-size:38px;margin:12px 0}h2{font-size:24px;margin-top:34px}p,li{font-size:16px;line-height:1.7;color:#b9cbe0}a{color:#9edfee}a:focus-visible{outline:2px solid #fff;outline-offset:4px}.actions{display:flex;flex-wrap:wrap;gap:14px;margin:25px 0}.actions a{padding:12px 18px;background:#1b3551;border:1px solid #4a6486;border-radius:7px;text-decoration:none;color:#e9f0ff}.notice{padding:16px 20px;background:#172239;border-left:4px solid #afa1ff;border-radius:4px}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:28px 0}.metric{border-top:2px solid #587997;padding:18px 0}.metric strong{display:block;font-size:40px;color:#9be7d4}.metric span{font-size:14px;color:#c0d2e5}.comparison{display:grid;grid-template-columns:1fr 1fr;gap:35px;margin:24px 0}.comparison strong{font-size:48px;display:block}.comparison small{display:block;font-size:16px;margin:12px 0;color:#b1c7dd}progress{width:100%;height:24px;accent-color:#72d9c4}.timeline{padding-left:25px}.timeline li{padding:8px 0}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:13px;border-bottom:1px solid #30465d;white-space:nowrap}th{color:#aec3e2}.fine{font-size:13px;color:#8fa8c3}.status{color:#8be4c5}details{margin-top:25px}summary{cursor:pointer;color:#b6d6ff}@media(max-width:650px){h1{font-size:29px}.metrics,.comparison{grid-template-columns:1fr}.metric strong{font-size:32px}main{padding:22px 18px}}
    </style></head><body><main>'''
    content += logo_html
    content += f'''<div class="eyebrow">PREDICTIVE RISK INTELLIGENCE FOR SECURE MIGRATION</div>
    <h1>The local migration demonstration passed</h1><p class="status">{len(summaries)} datasets completed. Source hashes and row counts preserved.</p>
    <div class="notice"><b>Automated rehearsal with synthetic data</b><p>This script simulates steward approvals to make the demonstration repeatable. It does not represent a human review. The interactive PRISM workspace continues to require explicit approval.</p></div>
    <div class="actions"><a href="http://127.0.0.1:8091/">Open PRISM workspace</a>{link('processed-01.zip', 'First processed database + CSV')}{link('source-01.sqlite', 'First source database')}{link('evidence.zip', 'All demo evidence')}</div>
    <div class="metrics"><div class="metric"><strong>{len(summaries)}</strong><span>datasets completed</span></div><div class="metric"><strong>{total_before-total_after:,}</strong><span>quality findings resolved across datasets</span></div><div class="metric"><strong>{second['memory_matches']}</strong><span>approved corrections retrieved on dataset 2</span></div></div>
    <h2>First dataset: {'real local MySQL snapshot' if first['mysql'] else 'SQLite source'}</h2><div class="comparison"><div><small>Source quality score</small><strong>{first['quality_before']:.2f}%</strong><progress max="100" value="{first['quality_before']}" aria-label="Source quality score"></progress><p>{first['before']} findings before cleaning</p></div><div><small>Processed quality score</small><strong>{first['quality_after']:.2f}%</strong><progress max="100" value="{first['quality_after']}" aria-label="Processed quality score"></progress><p>{first['after']} findings remain for review</p></div></div>
    <p class="fine">Scores count illustrative ERP findings per cell and can include overlapping issues. They are not SAP acceptance or certification. Duplicates, invalid dates and unresolved financial mappings remain visible.</p>
    <h2>What the demonstration proves</h2><ol class="timeline"><li>PRISM profiles a source with no approved history in a fresh rehearsal company.</li><li>The local Qwen model selects structured transformation candidates. Python validates them.</li><li>The rehearsal records a clearly labelled simulated approval and stores the correction.</li><li>Dataset 2 retrieves the approved evidence and receives a new local-model recommendation.</li><li>Subsequent datasets reuse approved resolutions. Every target database remains separate from its source.</li></ol>
    <p><b>This sequence demonstrates retrieval-based learning.</b> It does not train model weights or promote a fine-tuned adapter. QLoRA remains a separate workflow. No live Qlik or SAP load runs.</p>
    <h2>Dataset results</h2><div class="table-wrap"><table><thead><tr><th>Dataset</th><th>Recommendation</th><th>Memory matches</th><th>Findings</th><th>Target quality</th><th>Model time</th><th>Package</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
    <details><summary>Evidence and execution logs</summary><p>{link('summary.json', 'Machine-readable results')}<br>{link('pipeline.log', 'Pipeline log')}<br>{link('startup.log', 'Startup checks')}<br>{link('pipeline-errors.log', 'Runtime diagnostics')}</p></details>
    <p class="fine">Each launch creates a new synthetic rehearsal and retains earlier results. The interactive company's existing memory, source database and model files remain unchanged.</p></main></body></html>'''
    report = folder / 'PRISM Demo Report.html'
    report.write_text(content, encoding='utf-8')
    with zipfile.ZipFile(folder / 'evidence.zip', 'w', zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(folder / 'summary.json', 'summary.json')
        for item in summaries:
            for stem, suffix in [('source', '.sqlite'), ('processed', '.zip'), ('plan', '.json')]:
                name = f"{stem}-{item['batch']:02d}{suffix}"
                bundle.write(folder / name, name)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', type=Path, required=True)
    print(render_report(parser.parse_args().run))
