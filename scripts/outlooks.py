import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from urllib.parse import urljoin

from lxml import etree

from common import ReviewRequired, api, document, fetch, node_text, number, require
from wasde_pdf import parse as parse_wasde

WASDE = ('https://www.usda.gov/about-usda/general-information/staff-offices/office-chief-'
         'economist/commodity-markets/wasde-report')
BIMCO = 'https://www.bimco.org/news-insights/market-analysis/shipping-market-overview-and-outlook/'
BIMCO_SITEMAP = 'https://www.bimco.org/sitemap.xml'
BIMCO_PATH = re.compile(r'/shipping-market-overview-and-outlook/(20\d{2})/(\d{8})-smoo-bulk/?', re.I)
MEDIA = 'https://cyprusshippingnews.com/'
MONTHS = 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()


def update_wasde(grain, today):
    doc = document(fetch(WASDE))
    urls = {urljoin(WASDE, a.get('href')) for a in doc.xpath('//a[@href]')
            if re.search(r'/wasde\d{4}(?:v\d+)?\.pdf(?:$|\?)', a.get('href'), re.I)}
    require(urls, 'Official WASDE index contains no release PDF')
    def filename_order(url):
        m = re.search(r'wasde(\d\d)(\d\d)(?:v(\d+))?', url, re.I)
        return int(m[2]), int(m[1]), int(m[3] or 0)
    url = max(urls, key=filename_order)
    report = parse_wasde(fetch(url))
    require(filename_order(url)[:2] == (int(report['reportDate'][2:4]), int(report['reportDate'][5:7])),
            'USDA PDF filename and release cover disagree')
    apply_wasde(grain, report, url, today)
    return report['reportDate']


def apply_wasde(grain, report, url, today):
    forecast = grain['forecast']
    issued = report['reportDate']
    require(forecast['reportDate'] <= issued <= today, 'WASDE PDF is stale or future-dated')
    report_month = report['reportMonthAbbr']
    season = None
    old_issued = forecast['reportDate']
    updated = []
    for old in forecast['commodities']:
        item = report['commodities'][old['key']]
        target = item['targetSeason']
        require(season in (None, target), 'Unexpected mismatch in crop-year labels')
        season = target
        entities = {}
        prior_vintage = {}
        for row in item['rows']:
            values = {k: v for k, v in row.items() if k not in ('month', 'entity', 'page')}
            entity = row['entity']
            if row['season'] == target and row['month'] and row['month'] != report_month:
                if entity == 'World':
                    prior_vintage = row
                continue
            values['consumption'] = values['domesticConsumption']
            bucket = entities.setdefault(entity, {})
            require(row['season'] not in bucket, 'Duplicate USDA World/China crop-year row')
            bucket[row['season']] = values
        world = entities['World']
        current = world[target]
        previous_season = world[sorted(world)[-2]]
        require(len(world) >= 3 and all(r['production'] > 0 and r['endingStocks'] >= 0
                and r['imports'] > 0 and r['domesticConsumption'] > 0 for r in world.values()),
                'WASDE supply/use data failed magnitude checks')
        page = next(r['page'] for r in item['rows']
                    if r['entity'] == 'World' and r['season'] == target and r['month'] == report_month)
        source = url + f'#page={page}'
        previous_import = old.get('previousVintageImports')
        previous_source = old.get('sourcePrevious')
        if issued > old_issued:
            if forecast['season'] == target and prior_vintage:
                previous_import = prior_vintage['imports']
                mm = MONTHS.index(prior_vintage['month']) + 1
                yy = int(issued[:4]) - (mm > int(issued[5:7]))
                previous_source = (f'https://www.usda.gov/oce/commodity/wasde/wasde{mm:02d}{yy%100:02d}.pdf')
            else:
                previous_import = previous_source = None
        elif previous_import != prior_vintage.get('imports') and prior_vintage:
            previous_import = prior_vintage['imports']
        china = entities.get('China', {})
        if old['key'] == 'soy':
            require(set(world) <= set(china), 'WASDE China crush rows incomplete')
            for year, balance in world.items():
                balance['chinaCrush'] = china[year]['chinaCrush']
        new = dict(old, imports=current['imports'], previousVintageImports=previous_import,
                   previousSeasonImports=previous_season['imports'], sourceCurrent=source,
                   sourcePrevious=previous_source, sourceBalance=source,
                   seasons=[world[y] for y in sorted(world)[-3:]])
        if old['key'] == 'soy':
            new['chinaSeasons'] = [china[y] for y in sorted(world)[-3:]]
        updated.append(new)
    if old_issued != issued or updated != forecast['commodities']:
        prior_date = forecast['previousReportDate']
        if old_issued != issued:
            # The report provides the prior month label; only retain a date verified in our archive.
            match_old = any(c.get('sourcePrevious', '').split('#')[0].split('/')[-1]
                            == forecast['sourceGrain'].split('#')[0].split('/')[-1]
                            for c in updated if c.get('sourcePrevious'))
            prior_date = old_issued if match_old else None
        forecast.update(season=season, reportDate=issued, reportId=report['reportId'],
                        previousReportDate=prior_date, commodities=updated,
                        sourceGrain=next(c['sourceBalance'] for c in updated if c['key'] == 'wheat'),
                        sourceOilseeds=next(c['sourceBalance'] for c in updated if c['key'] == 'soy'),
                        releaseNote=f'採用 USDA {issued.replace("-", "/")} 發布之原始 PDF。上期預測採同一年度的對照欄。')
        grain.update(availabilityChecks=[{'url': url, 'available': True,
                     'result': f"Verified cover {report['reportId']} and all three World supply/use tables"}],
                     snapshotOnly=False)

def bimco_date(url):
    match = BIMCO_PATH.search(url)
    if not match:
        return None
    try:
        return datetime.strptime(match[2], '%Y%m%d').date().isoformat()
    except ValueError:
        return None


def discover_bimco():
    sitemap = etree.fromstring(fetch(BIMCO_SITEMAP), parser=etree.XMLParser(resolve_entities=False))
    urls = {url for url in sitemap.xpath('//*[local-name()="loc"]/text()')
            if url.startswith(BIMCO) and bimco_date(url)}
    require(urls, 'No BIMCO dry-bulk editions linked in public index')
    return sorted(urls, key=bimco_date)


def media_candidates(vintage):
    response = api(urljoin(MEDIA, 'wp-json/wp/v2/search'), query={
        'search': 'BIMCO Dry Bulk Shipping Market Overview Outlook',
        'per_page': 15, 'type': 'post', 'subtype': 'post'})
    require(isinstance(response, list), 'Unexpected shipping-news search response')
    return [r['url'] for r in response if r['url'].startswith(MEDIA)
            and re.search(rf'/{vintage[:4]}/(?:{vintage[5:7]}|'
                          rf'{int(vintage[5:7])%12+1:02d})/', r['url'])]


def article(raw):
    doc = document(raw)
    for unwanted in doc.xpath('//script|//style|//nav|//footer|//header|//aside'):
        unwanted.drop_tree()
    candidates = doc.xpath('//article|//main')
    return node_text(max(candidates, key=lambda x: len(node_text(x)))) if candidates else node_text(doc)


PCT = r'(-?\d+(?:\.\d+)?)\s*(?:%|percent|per cent)'
PCT_RANGE = r'(-?\d+(?:\.\d+)?)\s*(?:%)?\s*(?:[-–—]|to)\s*' + PCT


def range_after(text, key):
    match = re.search(key + r'[^.!?]{0,65}?' + PCT_RANGE, text, re.I)
    return [number(match[1]), number(match[2])] if match else None


def indexed_dwt(text, kind, years):
    terms = (r'(?:recycl\w*|demol\w*|scrap\w*)' if kind == 'recycling'
             else r'(?:deliver\w*|newbuild\w*)')
    # Only accept an explicit quantity/unit/year in the same bounded clause.
    values = {}
    for sentence in re.split(r'(?<=[.!?])\s+(?=[A-Z“])', text):
        if not re.search(terms, sentence, re.I) or not re.search(r'\bBIMCO\b|\bforecast|\bexpect', sentence, re.I):
            continue
        if len(sentence) > 520 or re.search(r'other sectors|containership|crude tanker', sentence, re.I):
            continue
        for literal, year in re.findall(r'(\d+(?:\.\d+)?)\s*(?:million|mn)\s*(?:dwt)?\s+(?:in|for|during)\s+(20\d{2})', sentence, re.I):
            if year in years and 0 < float(literal) <= 100 and re.search(r'\bdwt\b', sentence, re.I):
                amount = round(float(literal)*1_000_000)
                if year in values and values[year] != amount:
                    raise ReviewRequired(f'Conflicting {kind} figures for {year}')
                values[year] = amount
    return values


def parse_bimco_public(text, edition, url, official):
    if 'bimco' not in text.lower() or not re.search(r'\bdry bulk\b', text, re.I):
        return None
    closed = {}
    for match in re.finditer(r'\bIn (20\d{2}), (ship demand[^.!?]*(?:\.\d[^.!?]*)*)', text, re.I):
        year, clause = match.groups()
        demand = range_after(clause, r'ship demand(?: growth)?')
        supply = range_after(clause, r'(?:effective )?(?:ship supply|fleet supply|supply)(?: growth)?')
        if int(year) >= int(edition[:4]) and demand and supply and all(
                -20 <= v[0] <= v[1] <= 25 for v in (demand,supply)):
            closed[year] = {'demand': demand, 'supply': supply}
    years = sorted(closed)
    if len(years) != 2 or int(years[1]) != int(years[0])+1:
        return None
    scenarios = {'closed': {'label': '公開摘要基準情境',
                            'assumption': f'引用 BIMCO 公開聲明中適用於 {years[0]}、{years[1]} 的增速區間。',
                            'years': closed}}
    if re.search(r'Hormuz', text, re.I):
        shift = re.search(r'if the strait reopens, both demand and supply growth are expected to be '
                          r'(\d+(?:\.\d+)?) percentage point[s]? higher', text, re.I)
        if not shift or not re.search(rf'In {years[-1]}, .{{0,140}}in both scenarios', text, re.I):
            return None
        offset = number(shift[1])
        scenarios['closed'].update(label='荷姆茲持續受阻', assumption='荷姆茲海峽持續受阻的情境。')
        scenarios['open'] = {'label': f'{years[0]} 年起恢復通行',
                             'assumption': f'{years[0]} 年供給與需求增速各增加 {offset:g} 個百分點。',
                             'years': {years[0]: {k: [x+offset for x in v]
                                                for k,v in closed[years[0]].items()}, years[1]: closed[years[1]]}}
    return {'report': f'Dry Bulk Shipping Market Overview & Outlook — {edition[:7]}',
            'published': edition, 'officialUrl': official, 'publicReleaseUrl': url,
            'scenarios': scenarios, 'balance': ' · '.join(s['label'] for s in scenarios.values()),
            'access': 'Public BIMCO statement; full report may require membership.'}


def update_bimco(outlook, today):
    current = outlook['bimcoLatest']
    official = discover_bimco()[-1]
    issued = bimco_date(official)
    require(current['published'] <= issued <= today, 'BIMCO index returned stale or future edition')
    try:
        articles = [(official, article(fetch(official)))]
    except Exception:
        articles = []
    if issued == current['published']:
        urls = [current['publicReleaseUrl']]
        urls += [s['url'] for s in current.get('deliveryEvidence', {}).get('sources', [])]
        urls += [s['url'] for s in current.get('recyclingEvidence', {}).get('sources', [])]
    else:
        urls = media_candidates(issued[:7])
    def safe_article(url):
        try:
            return url, article(fetch(url))
        except Exception:
            return None
    with ThreadPoolExecutor(max_workers=4) as pool:
        articles.extend(result for result in pool.map(safe_article, dict.fromkeys(urls)) if result)
    require(articles, 'No public BIMCO edition or citation could be read')
    if issued > current['published']:
        candidates = [parse_bimco_public(text, issued, url, official)
                      for url, text in articles]
        parsed = next((result for result in candidates if result), None)
        if not parsed:
            raise ReviewRequired(f'New BIMCO edition {issued} found. Public figures or scenario wording need review.')
        for key in ('deliveriesDWT', 'deliveryEvidence'):
            if key in current:
                parsed[key] = current[key]
        current = parsed
        outlook['bimcoLatest'] = parsed
    years = set(current['scenarios']['closed']['years'])
    for kind in ('delivery', 'recycling'):
        combined, sources = {}, []
        for url, text in articles:
            if 'bimco' not in text.lower():
                continue
            matched = indexed_dwt(text, kind, years)
            if not matched:
                continue
            for year, amount in matched.items():
                if year in combined and combined[year] != amount:
                    raise ReviewRequired(f'Public reports disagree for BIMCO {kind}, {year}')
                combined[year] = amount
            sources.append({'publisher': 'BIMCO' if url == official else '公開報導', 'url': url})
        if not combined:
            continue
        if kind == 'delivery':
            initial = (current.get('deliveriesDWT', {})
                       if current.get('deliveryEvidence', {}).get('reportVintage') == issued[:7] else {})
            if any(initial[y] not in (None, v) for y, v in combined.items() if y in initial):
                raise ReviewRequired('BIMCO delivery quantity conflicts with the verified edition')
            if any(initial.get(y) != v for y, v in combined.items()):
                current['deliveriesDWT'] = initial | combined
                current['deliveryEvidence'] = {'reportVintage': issued[:7], 'sources': sources}
        else:
            previous = outlook['bimcoRecycling']
            if issued[:7] > previous['reportVintage']:
                outlook['bimcoRecycling'] = {'reportVintage': issued[:7], 'url': sources[0]['url'],
                    'officialUrl': official, 'evidenceType': 'public_summary',
                    'years': {y: {'recyclingDWT': value} for y, value in combined.items()}}
    return issued
