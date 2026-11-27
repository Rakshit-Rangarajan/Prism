"""Attach the local, SELECT-only synthetic MySQL source to a PRISM Qlik app."""
import argparse
import asyncio
import json
from pathlib import Path
import pymysql
from websockets.asyncio.client import connect
from app.erp_samples import SCHEMA
from scripts.load_qlik_demo import Engine

START = '// BEGIN PRISM LOCAL MYSQL SOURCE'
END = '// END PRISM LOCAL MYSQL SOURCE'


def source_script():
    lines = [START, "LIB CONNECT TO 'PRISM MySQL Source';"]
    for table, ddl in SCHEMA.items():
        fields = [column.strip().split()[0] for column in ddl.split(',')]
        aliases = []
        for field in fields:
            alias = 'source_vendor_id' if (table, field) in [('vendors', 'id'), ('invoices', 'vendor_id')] else f'source_{table}_{field}'
            aliases.append(f'[{field}] AS [{alias}]')
        lines.append(f'\n[source_{table}]:\nLOAD ' + ', '.join(aliases) + ';\nSQL SELECT ' + ', '.join('`'+f+'`' for f in fields) + f' FROM `prism_erp`.`{table}` LIMIT 5000;')
    return '\n'.join(lines + ['DISCONNECT;', END])


async def attach(folder):
    folder = Path(folder).resolve()
    state_path = folder / 'qlik-app.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    if not state.get('loaded'):
        raise ValueError('Load and verify the processed-data Qlik app first')
    env_path = Path(__file__).resolve().parents[1] / '.local/mysql.env'
    env = dict(line.split('=', 1) for line in env_path.read_text().splitlines() if '=' in line and not line.startswith('#'))
    if env.get('MYSQL_USER') != 'prism_reader' or env.get('MYSQL_DATABASE') != 'prism_erp':
        raise ValueError('Only the configured read-only synthetic demo source is supported')
    with pymysql.connect(host='127.0.0.1', port=3307, user=env['MYSQL_USER'], password=env['MYSQL_PASSWORD'], database='prism_erp') as db:
        with db.cursor() as cursor:
            counts = {}
            for table in SCHEMA:
                cursor.execute(f'SELECT count(*) FROM `{table}`')
                counts[table] = cursor.fetchone()[0]
                if counts[table] > 5000:
                    raise ValueError('Synthetic demo exceeds bounded Qlik source load')
    connection = {'qName': 'PRISM MySQL Source', 'qType': 'QvOdbcConnectorPackage.exe',
        'qConnectionString': 'CUSTOM CONNECT TO "provider=QvOdbcConnectorPackage.exe;driver=mysql;host=127.0.0.1;port=3307;db=prism_erp;SSLMode=PREFERRED;UseTrustStore=false;QueryTimeout=30;"',
        'qUserName': env['MYSQL_USER'], 'qPassword': env['MYSQL_PASSWORD']}
    async with connect('ws://localhost:4848/app/', origin='http://localhost:4848') as socket:
        engine = Engine(socket)
        if not (await engine.call(-1, 'IsValidConnectionString', [connection])).get('qReturn'):
            raise RuntimeError('Qlik MySQL connection validation failed')
        app = (await engine.call(-1, 'OpenDoc', [state['app_id']]))['qReturn']['qHandle']
        connections = (await engine.call(app, 'GetConnections'))['qConnections']
        existing = next((c for c in connections if c['qName'] == connection['qName']), None)
        if existing:
            await engine.call(app, 'ModifyConnection', [existing['qId'], connection])
        else:
            await engine.call(app, 'CreateConnection', [connection])
        original = (await engine.call(app, 'GetScript'))['qScript']
        backup = folder / 'PRISM-before-mysql.qvs'
        if not backup.exists():
            backup.write_text(original, encoding='utf-8')
        if START in original:
            before, rest = original.split(START, 1)
            _, after = rest.split(END, 1)
            updated = before + source_script() + after
        else:
            updated = original + '\n\n' + source_script() + '\n'
        try:
            await engine.call(app, 'SetScript', [updated])
            if not (await engine.call(app, 'DoReload')).get('qReturn'):
                raise RuntimeError('Qlik MySQL data reload failed')
            for table, field in [('vendors', 'name'), ('materials', 'id'), ('invoices', 'id')]:
                value = (await engine.call(app, 'Evaluate', [f'Count([source_{table}_{field}])']))['qReturn']
                if int(float(value)) != counts[table]:
                    raise ValueError(f'Qlik source row count mismatch: {table}')
            await engine.call(app, 'DoSave')
        except Exception:
            await engine.call(app, 'SetScript', [original])
            raise
        state['mysql_source'] = {'connected': True, 'host': '127.0.0.1', 'port': 3307,
            'database': 'prism_erp', 'user': 'prism_reader', 'rows_verified': counts,
            'mode': 'Reload-time SELECT; not streaming or CDC', 'query_limit_per_table': 5000}
        state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
        return state['mysql_source']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', type=Path, required=True)
    print(json.dumps(asyncio.run(attach(parser.parse_args().folder)), indent=2))
