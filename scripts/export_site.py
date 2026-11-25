import re

from common import dump, load, require, table

MIRRORS = {
    'brazil-iron-history.json': ('FLOW_IRON_HISTORY', 'iron-history-data.js'),
    'port-hedland-history.json': ('FLOW_HEDLAND_HISTORY', 'hedland-history-data.js'),
    'us-grain-history.json': ('FLOW_US_GRAIN_HISTORY', 'us-grain-history-data.js'),
    'grain-demand.json': ('FLOW_GRAIN_DEMAND', 'grain-demand-data.js'),
    'fleet-supply-sources.json': ('FLOW_SUPPLY_OUTLOOK', 'supply-outlook-data.js'),
    'company-fleets.json': ('FLOW_COMPANIES', 'company-fleets-data.js'),
}


def artifacts(state):
    result = {}
    def pair(data, filename, variable=None, jsfile=None):
        if filename:
            result[filename] = dump(data)
        if variable:
            result[jsfile] = dump(data, variable)

    d, us, brazil, hedland, grain = (state[k] for k in ('dashboard','us','brazil','hedland','grain'))
    pair(d, None, 'FLOW_DATA', 'data.js')
    pair(brazil, None, 'FLOW_HISTORY', 'history-data.js')
    iron = dict(brazil, series={k: brazil['series'][k] for k in ('iron', 'ironChina')})
    for data, name in [(iron, 'brazil-iron-history.json'), (hedland, 'port-hedland-history.json'),
                       (us, 'us-grain-history.json'), (grain, 'grain-demand.json'),
                       (state['bimco'], 'fleet-supply-sources.json'),
                       (state['companies'], 'company-fleets.json')]:
        pair(data, name, *MIRRORS[name])
    result['brazil-iron-history.csv'] = table(
        ('month', 'brazil_seaborne_iron_tonnes', 'brazil_to_china_iron_tonnes'),
        zip(iron['months'], iron['series']['iron'], iron['series']['ironChina']))
    result['port-hedland-history.csv'] = table(
        ('month', 'iron_ore_export_tonnes', 'approximate', 'source_url'),
        ((m, v, str(bool(hedland['approximate'].get(m))).lower(),
          hedland['records'].get(m, {}).get('url')) for m, v in
         zip(hedland['months'], hedland['series']['portHedland'])))
    result['us-grain-history.csv'] = table(
        ('week_ending', 'commodity', 'seaborne_export_inspections_tonnes'),
        sorted((day, key, value) for key, series in us['series'].items() for day, value in series.items()))
    a = ('period', 'tonnes', 'sourceName', 'sourceGroup', 'method', 'derived',
         'precisionNote', 'cumulativeTonnes', 'lastYearCumulativeTonnes',
         'published', 'publishedType', 'source')
    result['grain-demand-actual.csv'] = table(a, ([r.get(k) for k in a] for r in grain['actual']['rows']))
    f = grain['forecast']
    result['grain-demand-forecast.csv'] = table(
        ('commodity', 'report_date', 'season', 'imports_thousand_tonnes',
         'previous_report_date', 'previous_vintage_imports_thousand_tonnes',
         'previous_season_imports_thousand_tonnes', 'revision_thousand_tonnes',
         'source', 'previous_source'),
        ((c['key'], f['reportDate'], f['season'], c['imports'], f['previousReportDate'],
          c['previousVintageImports'], c['previousSeasonImports'],
          None if c['previousVintageImports'] is None else c['imports']-c['previousVintageImports'],
          c['sourceCurrent'], c['sourcePrevious']) for c in f['commodities']))
    result['grain-demand-balance.csv'] = table(
        ('commodity', 'report_date', 'geography', 'season', 'status', 'imports_thousand_tonnes',
         'consumption_thousand_tonnes', 'ending_stocks_thousand_tonnes', 'stocks_use_pct',
         'crush_thousand_tonnes', 'source'),
        ((c['key'], f['reportDate'], geo, r['season'], r['status'], r['imports'],
          r['domesticConsumption'], r['endingStocks'], r['stocksUsePct'],
          r.get('chinaCrush' if geo == 'China' else 'globalCrush'), c['sourceBalance'])
         for c in f['commodities'] for geo, rows in
         [('World', c['seasons']), ('China', c.get('chinaSeasons', []))] for r in rows))
    pair(state['china'], 'china-iron-monthly.json')
    pair(state['freight'], None, 'FLOW_FREIGHT_INDICES', 'freight-indices.js')
    pair(state['freight']['BDI'], None, 'FLOW_FREIGHT', 'freight-data.js')
    for code, series in state['freight'].items():
        pair(series, f'{code.lower()}-history.json')
        result[f'{code.lower()}-history.csv'] = table(
            ('date', f'{code}_points'), ((r['date'], r['value']) for r in series['rows']))
    return result


def verify(state, outputs, directory, persisted=False):
    d, brazil, us, hedland = (state[k] for k in ('dashboard','brazil','us','hedland'))
    for p in (brazil, hedland):
        require(p['months'] == sorted(set(p['months'])) and p['months'][-1] == p['displayEnd'],
                'Unordered monthly series')
        require(all(len(s) == len(p['months']) for s in p['series'].values()), 'Ragged month series')
    for key, h in (('brazil', brazil), ('portHedland', hedland)):
        point = d['ironFlowSnapshot'][key]
        values = h['series']['iron' if key == 'brazil' else key]
        require(point['period'] == h['displayEnd'] and point['tonnes'] == values[-1],
                'Iron flow card and chart disagree')
    require(us['displayEnd'] == d['usPeriod'] and all(
        rows[us['displayEnd']] == d['us'][k] for k, rows in us['series'].items()),
        'US inspection date or card differs from chart')
    require(d['brazilPeriod'] == brazil['displayEnd'] and
            all(d['brazil'][k][-1] == brazil['series'][k][-1]
                for k in d['brazil']), 'Brazil card differs from chart')
    for code, series in state['freight'].items():
        days = [r['date'] for r in series['rows']]
        require(len(days) > 5 and days == sorted(set(days)), f'Unsorted or duplicate {code}')
    actual = state['grain']['actual']['rows']
    require([r['period'] for r in actual] == sorted({r['period'] for r in actual}),
            'China soybean periods repeat or are unsorted')
    iron = d['ironFlowSnapshot']['china']
    if iron['period'] in state['china']:
        require(iron['tonnes'] == state['china'][iron['period']]['tonnes'],
                'China iron use of the latest archived observation is inconsistent')
    forecast = state['grain']['forecast']
    require({c['key'] for c in forecast['commodities']} == {'soy', 'corn', 'wheat'} and
            all(c['imports'] == c['seasons'][-1]['imports']
                and c['seasons'][-1]['season'] == forecast['season'] for c in forecast['commodities']),
            'WASDE import forecasts and supply/use data disagree')
    require(len(state['companies']['companies']) == 7 and all(
        len(c['bulk']) == 8 and len(c['other']) == 11 for c in state['companies']['companies']),
        'Fleet table matrix is inconsistent')
    markup = (directory / 'index.html').read_text(encoding='utf-8')
    for name in re.findall(r'(?:src|href)="([a-z][\w.-]*\.(?:js|css|json|csv))(?:\?[^"]*)?"', markup):
        require(name in outputs or (directory / name).is_file(), f'Missing website resource {name}')
    if persisted:
        for raw, (_, script) in MIRRORS.items():
            require(load(directory / raw) == load(directory / script), f'Unsynced website mirror {script}')
        require(load(directory / 'freight-indices.js') == state['freight'], 'Unsynced freight data')
        require(load(directory / 'update-status.json') == load(directory / 'update-status-data.js'),
                'Unsynced source status')
        for name, content in outputs.items():
            if name.endswith('.csv'):
                require((directory / name).read_text(encoding='utf-8-sig') == content,
                        f'Unsynced download {name}')
