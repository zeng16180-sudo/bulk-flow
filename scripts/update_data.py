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

from common import ROOT, ReviewRequired, dump, load
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
        return None, {'result': result, 'message': message}


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


def report_status(statuses):
    rows = []
    for name, row in statuses.items():
        message = row.get('message', '')
        point = ' · '.join(x for x in (str(row.get('period', '')), message) if x)
        rows.append(f"| {name} | {row['result']} | {point.replace('|', '/')} |\n")
        if message and os.getenv('GITHUB_ACTIONS') == 'true':
            print(f"::warning title=Data source {name}::{message.replace('%', '%25')}")
    summary = os.getenv('GITHUB_STEP_SUMMARY')
    if summary:
        with Path(summary).open('a', encoding='utf-8') as out:
            out.write('## Daily source checks\n\n| Source | Result | Period or issue |\n|---|---|---|\n')
            out.writelines(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--site', type=Path, default=SITE)
    parser.add_argument('--verify-only', action='store_true', help='Verify the current snapshot without the network')
    parser.add_argument('--check-only', action='store_true', help='Fetch and validate, without writing')
    options = parser.parse_args()
    today = datetime.now(ZoneInfo('Asia/Taipei')).date().isoformat()
    original = read_state(options.site)
    if options.verify_only:
        verify(original, artifacts(original), options.site, persisted=True)
        print('Existing snapshot integrity passed.')
        return
    state, statuses = run_checks(original, today)
    synchronize_metadata(state, original, today)
    previous = load(options.site / 'update-status.json')
    for name, row in statuses.items():
        if 'period' not in row and previous.get('sources', {}).get(name, {}).get('period'):
            row['period'] = previous['sources'][name]['period']
    files = render(options.site, state, {'checked': today, 'sources': statuses})
    if not options.check_only:
        write_changed(options.site, files)
    report_status(statuses)
    print('Validated all generated website artifacts.')


if __name__ == '__main__':
    main()
