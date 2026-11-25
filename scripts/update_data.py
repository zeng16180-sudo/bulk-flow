import argparse
import os
import re
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from zoneinfo import ZoneInfo

from common import ROOT, ReviewRequired, dump, is_temporary_error, load
from export_site import artifacts, verify
from fleets import update_company
from iron import update_hedland, update_imports, update_steel, update_vale
from markets import update_brazil, update_freight, update_us
from outlooks import update_bimco, update_wasde

SITE = ROOT / 'site'
FREIGHT = ('BDI', 'BCI', 'BPI', 'BSI')
DATA = {
    'dashboard': 'data.js', 'brazil': 'history-data.js', 'us': 'us-grain-history.json',
    'hedland': 'port-hedland-history.json', 'grain': 'grain-demand.json',
    'bimco': 'fleet-supply-sources.json', 'companies': 'company-fleets.json',
    'china': 'china-iron-monthly.json',
}


def read_state(directory):
    state = {k: load(directory / v) for k, v in DATA.items()}
    state['freight'] = {c: load(directory / f'{c.lower()}-history.json') for c in FREIGHT}
    return state


def groups(state):
    for code in FREIGHT:
        yield code, (('freight', code),), update_freight, (code,)
    yield 'us', (('us',), ('dashboard',)), update_us, ()
    yield 'brazil', (('brazil',), ('dashboard',)), update_brazil, ()
    yield 'china', (('grain',), ('dashboard',), ('china',)), update_imports, ()
    yield 'steel', (('dashboard',),), update_steel, ()
    yield 'hedland', (('hedland',), ('dashboard',)), update_hedland, ()
    yield 'vale', (('dashboard',),), update_vale, ()
    yield 'wasde', (('grain',),), update_wasde, ()
    yield 'bimco', (('bimco',),), update_bimco, ()
    for index, company in enumerate(state['companies']['companies']):
        yield company['name'], (('companies', 'companies', index),), update_company, ()


def locate(state, path):
    for key in path:
        state = state[key]
    return state


def evaluate(state, job, today):
    _, paths, function, extra = job
    originals = [locate(state, path) for path in paths]
    candidates = deepcopy(originals)
    try:
        period = function(*candidates, today, *extra)
        return candidates, {'result': 'updated' if candidates != originals else 'unchanged',
                            'period': period}
    except Exception as error:
        result = 'review' if isinstance(error, ReviewRequired) else 'error'
        message = f'{type(error).__name__}: {error}'.replace('\n', ' ').replace('\r', ' ')[:360]
        return None, {'result': result, 'message': message,
                      'temporary': result == 'error' and is_temporary_error(error)}


def merge(target, before, after):
    for key in before.keys() - after.keys():
        target.pop(key, None)
    for key, value in after.items():
        if key not in before:
            target[key] = value
        elif value != before[key]:
            if isinstance(value, dict) and isinstance(before[key], dict) and isinstance(target.get(key), dict):
                merge(target[key], before[key], value)
            else:
                target[key] = value


def run_checks(original, today):
    state, statuses = deepcopy(original), {}
    jobs = list(groups(original))
    with ThreadPoolExecutor(max_workers=8) as pool:
        replies = list(pool.map(lambda job: evaluate(original, job, today), jobs))
    for (name, paths, _, _), (candidates, status) in zip(jobs, replies):
        statuses[name] = status
        print(f"{name} {status['result']} {status.get('period', status.get('message', ''))}", flush=True)
        if candidates is not None:
            for path, data in zip(paths, candidates):
                merge(locate(state, path), locate(original, path), data)
    return state, statuses


def synchronize_metadata(state, original, today):
    if state != original:
        state['dashboard']['snapshot'] = today
    for key, field in [('companies', 'checked'), ('bimco', 'checked'), ('grain', 'retrieved')]:
        if state[key] != original[key]:
            state[key][field] = today
    bdi_days = {r['date'] for r in state['freight']['BDI']['rows']}
    for code in FREIGHT[1:]:
        days = {r['date'] for r in state['freight'][code]['rows']}
        earliest, latest = min(days), max(days)
        state['freight'][code]['validation']['missingAgainstBDI'] = sorted(
            m for m in bdi_days - days if earliest <= m <= latest)


def render(site, state, checked):
    files = artifacts(state)
    files.update({'update-status.json': dump(checked),
                  'update-status-data.js': dump(checked, 'FLOW_UPDATE_STATUS'),
                  'update-audit.json': dump(checked)})
    markup = (site / 'index.html').read_text(encoding='utf-8')
    def version(match):
        name = match[2]
        content = files[name].encode('utf-8') if name in files else (site / name).read_bytes()
        return f'{match[1]}"{name}?v={sha256(content).hexdigest()[:12]}"'
    files['index.html'] = re.sub(r'(src=|href=)"([a-z][\w.-]*\.(?:js|css))(?:\?[^"]*)?"', version, markup)
    verify(state, files, site)
    return files


def write_changed(directory, files):
    for name, content in files.items():
        path = directory / name
        data = content.encode('utf-8')
        if path.exists() and path.read_bytes() == data:
            continue
        with NamedTemporaryFile(dir=directory, delete=False) as staged:
            staged.write(data)
        try:
            os.replace(staged.name, path)
        finally:
            Path(staged.name).unlink(missing_ok=True)


def source_periods(state):
    dashboard = state['dashboard']
    iron = dashboard['ironFlowSnapshot']
    soy = state['grain']['actual']['rows'][-1]
    return {
        **{code: series['rows'][-1]['date'] for code, series in state['freight'].items()},
        'us': dashboard['usPeriod'],
        'brazil': dashboard['brazilPeriod'],
        'china': f"黃豆 {soy['period']} · 鐵礦砂 {iron['china']['period']}",
        'steel': dashboard['steelProduction']['period'],
        'hedland': state['hedland']['displayEnd'],
        'vale': dashboard['vale']['period'],
        'wasde': state['grain']['forecast']['reportDate'],
        'bimco': state['bimco']['bimcoLatest']['published'],
        **{c['name']: c.get('sourceDate') for c in state['companies']['companies']},
    }


def describe_statuses(original, state, statuses):
    previous_periods, periods = source_periods(original), source_periods(state)
    companies = {c['name']: c for c in state['companies']['companies']}
    old_companies = {c['name']: c for c in original['companies']['companies']}
    latest_soy = state['grain']['actual']['rows'][-1]
    latest_iron = state['dashboard']['ironFlowSnapshot']['china']
    outlook = state['bimco']
    delivery_vintage = outlook['bimcoLatest'].get('deliveryEvidence', {}).get('reportVintage')
    for name, row in statuses.items():
        row['previousPeriod'] = previous_periods[name]
        row['period'] = periods[name]
        succeeded = row['result'] in ('updated', 'unchanged')
        row['verifiedPeriod'] = periods[name] if succeeded else None
        if name in companies:
            before, company = old_companies[name], companies[name]
            row['vesselCount'] = sum(n or 0 for n in company['bulk'] + company['other'])
            row['previousVesselCount'] = sum(n or 0 for n in before['bulk'] + before['other'])
            row['detail'] = ('日期為最近一筆逐船紀錄的維護日' if periods[name]
                             else '官網未標示全船隊基準日，按可讀名冊或分類合計比對')
        elif name == 'china':
            row['detail'] = (f"黃豆：{latest_soy['sourceName']} · "
                             f"鐵礦砂：{latest_iron.get('sourceType', '海關資料')}")
            official_soy = [r['period'] for r in state['grain']['actual']['rows']
                            if 'fdi.mofcom.gov.cn' in r['source']]
            official_iron = [r['period'] for r in state['china'].values()
                             if 'fdi.mofcom.gov.cn' in r['source']]
            if official_soy and official_iron:
                common_period = min(max(official_soy), max(official_iron))
                if common_period < min(latest_soy['period'], latest_iron['period']):
                    row['detail'] += f' · 商務部轉載兩項皆有資料至 {common_period}'
        elif name == 'bimco':
            row['detail'] = (f"拆船量化版次 {outlook['bimcoRecycling']['reportVintage']}"
                             + (f" · 交付量化版次 {delivery_vintage}" if delivery_vintage else ''))


def record_temporary_failures(statuses, previous, day):
    old_sources = previous.get('sources', {})
    for name, row in statuses.items():
        if row.get('temporary'):
            old_days = old_sources.get(name, {}).get('temporaryFailureDays', 0)
            row['temporaryFailureDays'] = max(1, old_days + (previous.get('checked') != day))


def report_status(statuses, checked_at):
    def cell(value):
        return str(value).replace('|', '/').replace('\n', ' ')

    rows = []
    for name, row in statuses.items():
        message = row.get('message', '')
        result = row['result']
        failure_days = row.get('temporaryFailureDays', 0)
        count = row.get('vesselCount')
        undated = '官網未標日期' if count is not None else '—'
        previous = row['previousPeriod'] or undated
        verified = row['verifiedPeriod'] or undated
        if row['result'] in ('error', 'review'):
            verified = '未核驗 · 保留原值'
        vessels = '—'
        if count is not None:
            old_count = row['previousVesselCount']
            vessels = f'{count} 艘' if old_count == count else f'{old_count} → {count} 艘'
        detail = ' · '.join(x for x in (row.get('detail'), message) if x) or '—'
        if failure_days:
            result = '暫時故障' if failure_days < 3 else '暫時故障 · 請留意'
            detail += f' · 連續 {failure_days} 個查核日未恢復，下次排程自動再查'
        rows.append('| ' + ' | '.join(map(cell, (name, result, previous,
                                                 verified, vessels, detail))) + ' |\n')
        if message and (not failure_days or failure_days >= 3) and os.getenv('GITHUB_ACTIONS') == 'true':
            print(f"::warning title=Data source {name}::{message.replace('%', '%25')}")
    summary = os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with Path(summary).open('a', encoding='utf-8') as out:
            out.write('## Daily source checks\n\n')
            out.write(f"**查核完成（台灣時間）**　{checked_at.replace('T', ' ')}\n\n")
            out.write('`updated` 已抓取且採用數值或來源資訊有變動（也可能是歷史修訂）。'
                      '`unchanged` 已抓取，來源回傳的可核驗資料與原資料一致。'
                      '`暫時故障` 由排程自動再查。`error` 抓取或驗證失敗，需查看原因。'
                      '`review` 需要人工核對。\n\n')
            out.write('本次核驗期別以目前可讀的來源為準。網站何時採用本次結果，可查看 **deploy** 工作。\n\n')
            out.write('| 來源 | 結果 | 更新前採用期別 | 本次核驗期別 | 船隊艘數 | 說明 |\n'
                      '|---|---|---|---|---:|---|\n')
            out.writelines(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--site', type=Path, default=SITE)
    parser.add_argument('--verify-only', action='store_true', help='Verify the current snapshot without the network')
    parser.add_argument('--check-only', action='store_true', help='Fetch and validate, without writing')
    options = parser.parse_args()
    timezone = ZoneInfo('Asia/Taipei')
    today = datetime.now(timezone).date().isoformat()
    original = read_state(options.site)
    if options.verify_only:
        verify(original, artifacts(original), options.site, persisted=True)
        print('Existing snapshot integrity passed.')
        return
    state, statuses = run_checks(original, today)
    synchronize_metadata(state, original, today)
    describe_statuses(original, state, statuses)
    checked_at = datetime.now(timezone).isoformat(timespec='seconds')
    checked_day = checked_at[:10]
    record_temporary_failures(statuses, load(options.site / 'update-status.json'), checked_day)
    files = render(options.site, state, {'checked': checked_day, 'checkedAt': checked_at, 'sources': statuses})
    if not options.check_only:
        write_changed(options.site, files)
    report_status(statuses, checked_at)
    print('Validated all generated website artifacts.')


if __name__ == '__main__':
    main()
