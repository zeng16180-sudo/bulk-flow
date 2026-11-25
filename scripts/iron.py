import io
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from urllib.parse import urlencode, urljoin

from pypdf import PdfReader

from common import (ReviewRequired, apply_month_history, document, fetch, histories_to_maps,
                    month_shift, node_text, number, positive, report_date, require)

FDI = 'https://fdi.mofcom.gov.cn/'
FDI_API = urljoin(FDI, 'cipa-api/statistics/web/')
FDI_INDEX = urljoin(FDI, 'come-datatongji-list.html')
# A verified preliminary table bridges this release until the official repost appears.
IMPORT_REPRINTS = {'2026-10': 'https://www.steelhome.com/detailspage.php?nid=4791027&ntype=n'}
NBS = 'https://www.stats.gov.cn/sj/zxfb/'
PILBARA = ('https://www.pilbaraports.com.au/ports/port-of-port-hedland/'
           'about-port-of-port-hedland/port-statistics-and-reports')
PILBARA_TEASER = ('https://www.pilbaraports.com.au/pilbaraportsauthority/media/documents/'
                   'about%20ppa/news,%20media%20and%20statistics/news/teaser/'
                   'cargo-stats-by-destination_origin.pdf')
VALE = 'https://vale.com/investors'
IMPORT_TITLE = re.compile(r'(20\d{2})年\s*(?:(?:1\s*[至—－-]\s*)?)(\d{1,2})月.*进口.*商品量值表.*人民币')
CN_LABELS = {'大豆': 'soy', '铁矿砂及其精矿': 'iron'}


def pdf_pages(raw):
    require(raw.startswith(b'%PDF-'), 'Source returned a page rather than the requested PDF')
    return [page.extract_text() or '' for page in PdfReader(io.BytesIO(raw)).pages]


def fdi_request(route, post=None, query=None):
    url = FDI_API + route
    if query:
        url += '?' + urlencode(query)
    arguments = ['curl', '--silent', '--show-error', '--fail', '--max-time', '20',
                 '--retry', '1', '--referer', FDI_INDEX]
    payload = None
    if post:
        arguments += ['--header', 'Content-Type: application/json;charset=UTF-8', '--data-binary', '@-']
        payload = json.dumps(post, ensure_ascii=False).encode('utf-8')
    response = subprocess.run([*arguments, url], input=payload, capture_output=True, timeout=50)
    require(response.returncode == 0, 'China Commerce Ministry API: ' +
            response.stderr.decode('utf-8', errors='replace').strip()[:250])
    return json.loads(response.stdout)


def parse_import(article, today):
    match = IMPORT_TITLE.search(article['name'])
    require(match, 'China imports table title or currency mismatch')
    period = f'{match[1]}-{int(match[2]):02d}'
    published = article.get('issueDate', '')[:10]
    require(re.fullmatch(r'20\d{2}-\d\d-\d\d', published) and period <= today[:7]
            and published <= today, 'Invalid official repost date or month')
    url = urljoin(FDI, f'come-datatongji-con.html?id={int(article["id"])}')
    rows = [[re.sub(r'\s+', '', node_text(c)) for c in tr.xpath('./td|./th')]
            for tr in document(article['content']).xpath('//tr')]
    header = next((r for r in rows if r and r[0] == '商品名称'), [])
    explicit_month = len(header) >= 6 and header[2] == f'{int(match[2])}月'
    if not explicit_month and period.endswith('-02'):
        return {}
    require(explicit_month and '累计' in header[3] and '累计' in header[4],
            'China table does not identify month and cumulative columns')
    parsed = {}
    for row in rows:
        if not row or row[0] not in CN_LABELS:
            continue
        require(len(row) >= 10 and row[1] == '万吨', 'China import unit or column count changed')
        key = CN_LABELS[row[0]]
        require(key not in parsed, 'Duplicate commodity in China official table')
        observed, cumulative, last_year = (number(row[i]) * 10000 for i in (2, 4, 6))
        require(0 <= observed <= cumulative and last_year >= 0, 'Invalid China import quantities')
        value = {'period': period, 'tonnes': observed, 'source': url,
                 'sourceName': '中國海關／商務部官方轉載', 'sourceGroup': 'china-official-tables',
                 'published': published, 'publishedType': '官方轉載日期',
                 'method': 'reported_monthly_quantity', 'originalUnit': '萬噸',
                 'precisionNote': '依官方量值表原有精度', 'cumulativeTonnes': cumulative,
                 'lastYearCumulativeTonnes': last_year, 'retrieved': today,
               'reportedCumulativeYoY': number(row[8]) if re.search(r'\d', row[8]) else None,
               'title': article['name']}
        parsed[key] = [value]
        if period.endswith('-02') and cumulative > observed:
            parsed[key].append(dict(value, period=month_shift(period, -1),
                                    tonnes=cumulative-observed,
                                    method='derived_same_table_jan_feb_cumulative_minus_february',
                                    derived=True, cumulativeTonnes=None,
                                    lastYearCumulativeTonnes=None, reportedCumulativeYoY=None,
                                    precisionNote='同一官方表 1–2 月累計減明列的 2 月，為約數'))
    require(set(parsed) == set(CN_LABELS.values()), 'Official table lacks soybean or iron ore')
    return parsed


def read_imports(today, anchor):
    earliest = month_shift(anchor, -13)
    candidates = {}
    for year in range(int(earliest[:4]), int(today[:4])+1):
        for keyword in ('进口', '主要商品'):
            for page in (1, 2, 3):
                result = fdi_request('list', post={'menuId': 1, 'classifyId': '12',
                                     'year': str(year), 'keyWord': keyword, 'page': page})
                require(result.get('code') == 0 and isinstance(result['data'], list),
                        'FDI index response not recognized')
                matches = 0
                for item in result['data']:
                    match = IMPORT_TITLE.search(item['name'])
                    if match and f'{match[1]}-{int(match[2]):02d}' >= earliest:
                        candidates[item['id']] = item
                        matches += 1
                if len(result['data']) < 10 or (page >= 2 and not matches):
                    break
            if any(f'{year}年' in c['name'] for c in candidates.values()):
                break
    require(candidates, 'No current official China import tables were found')
    def get(item):
        payload = fdi_request('get', query={'id': item['id']})
        require(payload.get('code') == 0, 'FDI article response not recognized')
        return parse_import(payload['data'], today)
    with ThreadPoolExecutor(max_workers=4) as pool:
        articles = list(pool.map(get, candidates.values()))
    result = {'soy': {}, 'iron': {}}
    for article in articles:
        for key, rows in article.items():
            for row in rows:
                previous = result[key].get(row['period'])
                if not previous or (not row.get('derived'), row['published']) > (
                        not previous.get('derived'), previous['published']):
                    result[key][row['period']] = row
    return result


def read_import_reprint(raw, today, url):
    doc = document(raw)
    title = next((node_text(h) for h in doc.xpath('//h1|//h2|//h3|//title')
                  if re.search(r'20\d{2}年\d{1,2}月全国进口重点商品量值表', node_text(h))), '')
    match = re.search(r'(20\d{2})年(\d{1,2})月全国进口重点商品量值表', title)
    require(match, 'Reprint title has no explicit customs month')
    period = f'{match[1]}-{int(match[2]):02d}'
    require(period <= today[:7] and not period.endswith('-02'), 'Reprint month not supported')
    text = node_text(doc)
    dates = re.findall(r'(20\d{2}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2}', text[:12000])
    published = next((d for d in dates if period < d[:7] and d <= today), None)
    require(published, 'Reprint publication date absent')
    table = []
    for tr in doc.xpath('//tr'):
        row = [re.sub(r'\s+', '', node_text(td)) for td in tr.xpath('./td|./th')]
        if row and row[0] in ('商品名称', *CN_LABELS):
            table.append(row)
    require(any(len(r) >= 5 and r[:5] == ['商品名称', '计量单位', '当月', '1至当月累计', '去年同期累计']
                for r in table), 'Reprint monthly and cumulative columns did not match')
    output = {}
    for cells in table:
        if cells[0] not in CN_LABELS:
            continue
        require(len(cells) == 10 and cells[1] == '万吨', 'Reprint unit or columns changed')
        value, accumulated, prior = [number(cells[i]) * 10000 for i in (2, 4, 6)]
        require(0 < value <= accumulated and prior > 0, 'Reprint quantities failed checks')
        output[CN_LABELS[cells[0]]] = {period: {
            'period': period, 'tonnes': value, 'source': url,
            'sourceName': '中國海關快訊／鋼之家轉載', 'sourceGroup': 'china-official-tables',
            'published': published, 'publishedType': '第三方轉載日期', 'retrieved': today,
            'method': 'gacc_preliminary_monthly_quantity_reprint',
            'originalUnit': '萬噸', 'precisionNote': '海關快訊轉載，待官方月報覆核',
            'cumulativeTonnes': accumulated, 'lastYearCumulativeTonnes': prior,
            'reportedCumulativeYoY': number(cells[8]), 'title': title}}
    require(set(output) == set(CN_LABELS.values()), 'Both commodities required in customs reprint')
    return output


def update_imports(grain, dashboard, archive, today):
    actual = grain['actual']
    current = dashboard['ironFlowSnapshot']['china']
    soy_old = {r['period']: r for r in actual['rows']}
    prior = max(max(soy_old), current['period'])
    fresh = read_imports(today, prior)
    require(fresh['soy'] and fresh['iron'], 'Official China imports index returned no measurable months')
    official_months = [r['period'] for r in soy_old.values()
                       if r['source'].startswith(FDI) and not r.get('derived')]
    require(not official_months or max(fresh['soy']) >= max(official_months),
            'Official China imports index is behind existing official observations')
    latest_official = max(fresh['soy'])
    for period, url in IMPORT_REPRINTS.items():
        if latest_official >= period or period in soy_old or period > today[:7]:
            continue
        reprint = read_import_reprint(fetch(url), today, url)
        require(all(period in rows for rows in reprint.values()), 'Unexpected reprint month')
        for key in fresh:
            fresh[key].update(reprint[key])
    soy = soy_old.copy()
    for period, row in fresh['soy'].items():
        old = soy_old.get(period)
        if old and (old.get('sourceGroup') != 'china-official-tables'
                    or (old['source'].startswith(FDI) and (old.get('published') or '') > row['published'])):
            continue
        if not old or row != dict(old, retrieved=today):
            soy[period] = row
    if soy != soy_old:
        latest = max(soy)
        year = int(latest[:4])
        actual.update(rows=[soy[m] for m in sorted(soy)], years=list(range(year-4, year+1)),
                      checked=today)
        actual['missingPeriods'] = [f'{y}-{m:02d}' for y in actual['years']
                                    for m in range(1, (int(latest[5:]) if y == year else 12)+1)
                                    if f'{y}-{m:02d}' not in soy]
        actual['coverage'] = {str(y): sum(m.startswith(str(y)) for m in soy)
                              for y in range(year-5, year+1)}
        stage = ' · 海關快訊轉載，待官方月報覆核' if soy[latest]['method'].startswith('gacc_preliminary') else ''
        actual['coverageNote'] = f'最新已核驗月份 {latest.replace("-", "/")}{stage}。缺月留空。'
    iron = archive.copy()
    for period, row in fresh['iron'].items():
        if period not in iron or ((not iron[period]['source'].startswith(FDI) or row['published'] >= iron[period]['published'])
                                  and row != dict(iron[period], retrieved=today)):
            iron[period] = row
    latest_iron = max(iron)
    new = iron[latest_iron]
    if latest_iron >= current['period']:
        previous = [iron.get(month_shift(latest_iron, d)) for d in (-1, -12)]
        comparison = {}
        for old, key in zip(previous, ('previousMonth', 'previousYear')):
            comparison[key] = old['tonnes'] if old else None
            comparison[key+'Source'] = old['source'] if old else None
        card = {k: new[k] for k in ('tonnes', 'period', 'published', 'source')}
        card.update(approximate=bool(new.get('derived')), sourceType=new['sourceName'],
                    publishedType=new.get('publishedType'),
                    scope='China imports of iron ore and concentrates; all modes', **comparison)
        if any(current.get(key) != value for key, value in card.items()):
            card['checked'] = today
            dashboard['china'] = card.copy()
            dashboard['ironFlowSnapshot']['china'] = card
    archive.update(iron)
    return f'黃豆 {max(soy)} · 鐵礦砂 {max(latest_iron, current["period"])}'


def parse_steel(raw, period):
    result = {}
    for tr in document(raw).xpath('//tr'):
        cells = [re.sub(r'\s+', '', node_text(cell)).replace('（', '(').replace('）', ')')
                 for cell in tr.xpath('./td|./th')]
        names = {'生铁(万吨)': 'pigIron', '粗钢(万吨)': 'crudeSteel'}
        if cells and cells[0] in names:
            require(len(cells) >= 4, 'Industrial production table lacks monthly fields')
            result[names[cells[0]]] = {'value': positive(cells[1]), 'yoyPct': number(cells[2])}
    require(len(result) == 2, 'Industrial production report lacks pig iron or crude steel rows')
    return result


def update_steel(dashboard, today):
    index = document(fetch(NBS))
    urls = {}
    for link in index.xpath('//a[@href]'):
        text = link.get('title') or node_text(link)
        match = re.search(r'(20\d{2})年\s*(\d{1,2})月份规模以上工业增加值', text)
        if match and int(match[2]) > 1:
            month = f'{match[1]}-{int(match[2]):02d}'
            urls[month] = urljoin(NBS, link.get('href'))
    require(urls, 'No monthly industrial-production report at NBS index')
    old = dashboard['steelProduction']
    period = max(urls)
    require(old['period'] <= period <= today[:7], 'NBS index is stale or ahead of today')
    def load_month(month):
        url = urls[month]
        alternate = re.sub(r'/sj/zxfb/', '/xxgk/sjfb/zxfb2020/', url)
        for candidate in dict.fromkeys((alternate, url)):
            try:
                return parse_steel(fetch(candidate), month), candidate
            except Exception:
                if candidate == url:
                    raise
    values, url = load_month(period)
    previous_period = month_shift(period, -1)
    previous, previous_url = None, None
    if previous_period in urls:
        previous, previous_url = load_month(previous_period)
    elif old['period'] == previous_period:
        previous, previous_url = old, old['source']
    elif old['period'] == period:
        previous_url = old.get('previousMonthSource')
        previous = {key: {'value': old[key].get('previousMonth')} for key in values}
    for key in values:
        values[key]['previousMonth'] = previous[key]['value'] if previous else None
    if period != old['period'] or any(values[key] != old[key] for key in values):
        old.update(period=period, published=report_date(url), checked=today,
                   source=url, previousMonthSource=previous_url, **values)
    return period


def parse_hedland(raw):
    require(raw.startswith(b'%PDF-'), 'Port Hedland returned a page instead of a PDF')
    for pdf_page in PdfReader(io.BytesIO(raw)).pages:
        page = pdf_page.extract_text(extraction_mode='layout') or ''
        if not re.search(r'(?m)^\s*LOAD\s*$', page) or 'Iron Ore' not in page:
            continue
        match = re.search(r'Departure\s*Date\s*:?\s*(\d{1,2})/0?1/(20\d{2})\s+to\s+(\d{1,2})/(\d{1,2})/(20\d{2})', page)
        lines = page.splitlines()
        headers = [line for line in lines if 'Iron Ore' in line and 'Total' in line]
        totals = [line for line in lines if re.match(r'^\s*Total\s+[\d,.]+', line)]
        if match and totals and match[1] == match[3] and match[2] == match[5]:
            start = date(int(match[2]), int(match[1]), 1)
            end = date(int(match[5]), int(match[3]), int(match[4]))
            require((end + timedelta(days=1)).month != start.month, 'Partial Port Hedland month')
            require(len(totals) == len(headers) == 1, 'Ambiguous Port Hedland load totals')
            header = list(re.finditer(r'\S.*?(?=\s{2,}|$)', headers[0]))
            iron = next(i for i, col in enumerate(header) if col[0] == 'Iron Ore')
            left = (header[iron-1].end() + header[iron].start()) / 2
            right = (header[iron].end() + header[iron+1].start()) / 2
            cells = list(re.finditer(r'\d[\d,]*\.\d{2}', totals[0]))
            value = [c[0] for c in cells if left <= c.end() <= right]
            require(len(value) == 1 and len(cells) >= 2, 'Cannot align Iron Ore column')
            amount = positive(value[0])
            require(20_000_000 <= amount <= 85_000_000, 'Unexpected Port Hedland monthly quantity/unit')
            return start.isoformat()[:7], amount, totals[0].strip()
    raise ValueError('Port Hedland PDF lacks a recognized monthly LOAD / Iron Ore total')


def update_hedland(payload, dashboard, today):
    try:
        doc = document(fetch(PILBARA))
        urls = list(dict.fromkeys(urljoin(PILBARA, a.get('href'))
                    for a in doc.xpath('//tr/td[1]//a[@href]')
                    if re.search(r'\.pdf(?:$|\?)', a.get('href'), re.I)
                    and ('cargo-stats' in a.get('href').lower() or 'cargo by destination' in node_text(a).lower())))
    except Exception:
        urls = []
    index_available = bool(urls)
    prior = payload['displayEnd']
    result = histories_to_maps(payload)['portHedland']
    valid = []
    errors = []
    for url in dict.fromkeys([*urls[:3], PILBARA_TEASER]):
        try:
            period, tonnes, total = parse_hedland(fetch(url))
        except Exception as error:
            errors.append(str(error))
            continue
        require(period <= today[:7], 'Future Port Hedland observation')
        if period < month_shift(prior, -2):
            continue
        valid.append(period)
        if result.get(period) == tonnes and not payload['approximate'].get(period):
            continue
        record = {'period': period, 'url': url, 'tonnes': tonnes,
                  'totalRow': total, 'approximate': False}
        result[period] = tonnes
        payload['approximate'][period] = False
        payload['records'][period] = record
    latest = max(result)
    require(valid and max(valid) >= prior and latest in payload['records'],
            'No current Port Hedland cargo PDF. ' + '; '.join(errors))
    if latest == prior and not index_available and today[:7] > month_shift(prior, 1):
        raise ReviewRequired('Port index unavailable; the directly accessible official report has not advanced')
    if latest > prior or any(result.get(m) != v for m, v in
                             zip(payload['months'], payload['series']['portHedland'])):
        apply_month_history(payload, {'portHedland': result}, latest)
        payload.update(retrieved=today, checked=today,
                       note='Official PDF LOAD → Iron Ore → Total. Marked approximate observations are official rounded releases.',
                       latestAvailabilityNote=f'Latest detailed observation: {latest}')
        p = month_shift(latest, -1)
        y = month_shift(latest, -12)
        dashboard['ironFlowSnapshot']['portHedland'] = {
            'period': latest, 'tonnes': result[latest], 'published': None, 'checked': today,
            'source': payload['records'][latest]['url'], 'approximate': False,
            'previousMonth': result.get(p), 'previousYear': result.get(y),
            'previousMonthSource': payload['records'].get(p, {}).get('url'),
            'previousYearSource': payload['records'].get(y, {}).get('url')}
    return latest


def update_vale(dashboard, today):
    doc = document(fetch(VALE))
    items = []
    for heading in doc.xpath('//h2|//h3|//h4'):
        match = re.fullmatch(r'([1-4])Q(\d{2})', node_text(heading))
        if not match:
            continue
        for container in list(heading.iterancestors())[:4]:
            links = [a for a in container.xpath('.//a[@href]')
                     if any(re.match(r"Vale[’']s Performance\b", node_text(parent), re.I)
                            for parent in list(a.iterancestors())[:4])
                     and 'mziq.com/' in a.get('href')]
            if len(links) == 1:
                items.append((f'20{match[2]}-Q{match[1]}', urljoin(VALE, links[0].get('href'))))
                break
    require(items, 'No quarterly Vale performance PDF found')
    period, url = max(items)
    old = dashboard['vale']
    require(period >= old['period'], 'Vale report index returned an older quarter')
    pages = pdf_pages(fetch(url))
    quarter = f'{period[-1]}Q{period[2:4]}'
    require(re.search(rf'\b{quarter}\b', ' '.join(pages[:2])), 'Vale PDF quarter mismatch')
    target = next((p for p in pages if 'Production Summary' in p and 'Sales Summary' in p), '')
    require(target and re.search(r'000[’\x27]?\s*metric tons', target, re.I), 'Vale report quantities or unit missing')
    values = {}
    for heading, key in [('Production Summary', 'production'), ('Sales Summary', 'sales')]:
        report = target.split(heading, 1)[1]
        match = re.search(r'(?m)^\s*Iron ore(?:[¹²³⁴]|\s*\d+/)?\s+(\d{1,3},\d{3})\s+(\d{1,3},\d{3})', report)
        require(match and quarter in report[:match.start()], 'Vale iron ore row or quarter labels missing')
        values[key], values[key+'PreviousYear'] = (positive(x)/1000 for x in match.groups())
    if period != old['period'] or old.get('source') != url or any(values[k] != old[k] for k in values):
        released = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?,\s*(20\d{2})', pages[0])
        published = datetime.strptime(' '.join(released.groups()), '%B %d %Y').date().isoformat() if released else None
        require(not published or published <= today, 'Vale PDF dated in the future')
        old.update(period=period, source=url, sourcePage=VALE, published=published,
                   checked=today, **values)
    return period
