"""Create a local Qlik Desktop app using its documented Engine JSON API.

Requires Qlik Desktop to be running and its licensed session launched. This
connects only to loopback; no Cloud credentials or generated SQL are involved.
"""
import argparse
import asyncio
import json
import uuid
from pathlib import Path
from urllib.parse import quote
from websockets.asyncio.client import connect


class Engine:
    def __init__(self, socket):
        self.socket, self.sequence = socket, 0

    async def call(self, handle, method, params=None):
        self.sequence += 1
        request_id = self.sequence
        await self.socket.send(json.dumps({'jsonrpc': '2.0', 'id': request_id,
            'handle': handle, 'method': method, 'params': params or []}))
        async with asyncio.timeout(90):
            while True:
                reply = json.loads(await self.socket.recv())
                if reply.get('id') != request_id:
                    continue
                if 'error' in reply:
                    raise RuntimeError(f'{method}: {reply["error"]}')
                return reply.get('result', {})


def chart(identifier, title, measure, label):
    return {'qInfo': {'qId': identifier, 'qType': 'barchart'}, 'visualization': 'barchart',
        'title': title, 'showTitles': True, 'orientation': 'vertical',
        'subtitle': 'Synthetic ERP data | approvals simulated | retrieval learning',
        'footnote': 'Local Qlik Desktop integration. Unresolved findings remain visible.',
        'version': '1.0.0', 'components': [],
        'legend': {'show': True, 'showTitle': True, 'dock': 'bottom'},
        'dimensionAxis': {'show': 'all', 'dock': 'near', 'label': 'auto', 'axisDisplayMode': 'max', 'continuousAuto': True, 'maxVisibleItems': 20},
        'measureAxis': {'show': 'all', 'dock': 'near', 'autoMinMax': True, 'min': 0, 'max': 100, 'minMax': 'min', 'spacing': 1},
        'gridLine': {'auto': True, 'spacing': 2},
        'dataPoint': {'showLabels': False, 'showSegmentLabels': False, 'showTotalLabels': True},
        'refLine': {'refLines': [], 'dimRefLines': []},
        'tooltip': {'auto': True, 'hideBasic': False},
        'preferContinuousAxis': False, 'showMiniChartForContinuousAxis': False,
        'scrollbar': 'none', 'scrollStartPos': 0, 'showDisclaimer': True,
        'barGrouping': {'grouping': 'grouped'}, 'color': {'auto': True},
        'qHyperCubeDef': {'qDimensions': [{'qDef': {'qFieldDefs': ['Dataset'], 'qSortCriterias': [{'qSortByNumeric': 1}]}}],
            'qMeasures': [{'qDef': {'qDef': f'{measure}({{<Stage={{\'{stage}\'}}>}} {label})', 'qLabel': stage.title()}} for stage in ('before', 'after')],
            'qInitialDataFetch': [{'qTop': 0, 'qLeft': 0, 'qHeight': 100, 'qWidth': 3}]}}


async def load(folder):
    folder = Path(folder).resolve()
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('synthetic') is not True or manifest.get('approval') != 'simulated':
        raise ValueError('This loader accepts only labelled synthetic rehearsal packages')
    if (folder / 'qlik-app.json').exists():
        raise FileExistsError('An app was already created for this package; use its saved URL')
    name = 'PRISM Migration Demo ' + uuid.uuid4().hex[:8]
    async with connect('ws://localhost:4848/app/', origin='http://localhost:4848', max_size=8*1024*1024) as socket:
        engine = Engine(socket)
        created = await engine.call(-1, 'CreateApp', [name])
        if not created.get('qSuccess'):
            raise RuntimeError(f'CreateApp failed: {created}')
        app_id = created['qAppId']
        # Preserve recovery information immediately if a later API operation fails.
        state = {'app_id': app_id, 'name': name, 'loaded': False, 'cloud_connected': False}
        state_path = folder / 'qlik-app.json'
        state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
        opened = await engine.call(-1, 'OpenDoc', [app_id])
        app = opened['qReturn']['qHandle']
        await engine.call(app, 'CreateConnection', [{'qName': 'PRISM Demo', 'qConnectionString': str(folder), 'qType': 'folder'}])
        await engine.call(app, 'SetScript', [(folder / 'PRISM.qvs').read_text(encoding='utf-8')])
        result = await engine.call(app, 'DoReload')
        if result.get('qReturn') is not True:
            raise RuntimeError(f'Qlik data reload failed: {result}')
        for field, expected in [('vendors_name', manifest['rows']['vendors']), ('materials_id', manifest['rows']['materials']), ('invoices_id', manifest['rows']['invoices']), ('Stage', manifest['datasets']*2)]:
            result = await engine.call(app, 'Evaluate', [f'Count([{field}])'])
            if int(float(result['qReturn'])) != expected:
                raise ValueError(f'Qlik row count mismatch: {field}: {result}')
        for stage, expected in manifest['first_dataset'].items():
            result = await engine.call(app, 'Evaluate', [f"Sum({{<Dataset={{1}},Stage={{'{stage}'}}>}} Findings)"])
            if float(result['qReturn']) != expected:
                raise ValueError('First-dataset findings do not match PRISM metrics')
        for properties in [chart('prism-findings', 'Data quality findings by dataset', 'Sum', 'Findings'),
                           chart('prism-quality', 'Quality score by dataset (%)', 'Avg', 'QualityScore')]:
            obj = await engine.call(app, 'CreateObject', [properties])
            layout = await engine.call(obj['qReturn']['qHandle'], 'GetLayout')
            if layout['qLayout']['qHyperCube']['qSize']['qcy'] != manifest['datasets']:
                raise ValueError('Qlik chart dataset count mismatch')
        cells = [{'name': name, 'type': 'barchart', 'col': 0, 'row': row, 'colspan': 24, 'rowspan': 6,
                  'bounds': {'x': 0, 'y': row*100/12, 'width': 100, 'height': 50}} for name, row in [('prism-findings', 0), ('prism-quality', 6)]]
        await engine.call(app, 'CreateObject', [{'qInfo': {'qId': 'prism-overview', 'qType': 'sheet'},
            'qMetaDef': {'title': 'PRISM Migration Quality', 'description': 'Predictive Risk Intelligence for Secure Migration. Synthetic data; approvals simulated. Local file integration.'},
            'rank': 1, 'columns': 24, 'rows': 12, 'cells': cells,
            'qChildListDef': {'qData': {'title': '/title'}}}])
        await engine.call(app, 'DoSave')
        state.update(loaded=True, rows_verified=manifest['rows'], datasets=manifest['datasets'],
                     url='http://localhost:4848/sense/app/' + quote(app_id, safe='') + '/sheet/prism-overview/state/analysis')
        state_path.write_text(json.dumps(state, indent=2), encoding='utf-8')
        (folder / 'Open PRISM Qlik.url').write_text('[InternetShortcut]\nURL=' + state['url'] + '\n', encoding='utf-8')
        return state


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', type=Path, required=True)
    print(json.dumps(asyncio.run(load(parser.parse_args().folder)), indent=2))
