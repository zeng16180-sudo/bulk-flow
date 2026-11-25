import json
import re
from collections import Counter

from common import document, fetch, node_text, number, require

SNC = 'https://www.snc.com.tw/船隊明細/'
BULK = ('vloc', 'cape', 'panamax', 'supra', 'ultra', 'handy', 'small', 'otherBulk')
OTHER = ('cement', 'tanker', 'lng', 'csov', 'ctv', 'multi', 'cargo',
         'passenger', 'tug', 'pilot', 'other')
WORDING = {'vloc': 'VLOC', 'cape': 'Capesize', 'panamax': 'Panamax／Kamsarmax',
           'supra': 'Supramax', 'ultra': 'Ultramax', 'handy': 'Handysize', 'small': 'Small Handy',
           'otherBulk': '其他散裝', 'cement': '水泥船', 'tanker': '油輪', 'lng': 'LNG',
           'csov': 'CSOV', 'ctv': 'CTV', 'multi': '多用途船', 'cargo': '雜貨船',
           'passenger': '客輪', 'tug': '拖船', 'pilot': '引水船', 'other': '其他'}


def column_counts(elements, mapping, identity, value):
    counts, unique = Counter(), set()
    for element in elements:
        key = identity(element)
        require(key in mapping, f'Unrecognized fleet category {key}')
        if key not in unique:
            counts[mapping[key]] += value(element)
            unique.add(key)
    require(set(mapping) <= unique, 'Fleet category absent from source')
    return counts


def summary(counts):
    return '、'.join(f'{WORDING[key]} {n}' for key, n in counts.items() if n) + ' 艘。'


def uming(raw):
    doc = document(raw)
    mapping = dict(zip(('FCA0002', 'FCA0006', 'FCA0003', 'FCA0004', 'FCA0005',
                        'FCA0007', 'FCA0010', 'FCA0009', 'FCA0008'),
                       ('vloc', 'tanker', 'cape', 'panamax', 'ultra', 'cement', 'lng', 'csov', 'ctv')))
    counts = column_counts(doc.xpath('//li[@data-table="FleetCata" and @data-id]'), mapping,
                           lambda item: item.get('data-id'),
                           lambda item: int(re.search(r'\d+', node_text(item.xpath('.//h5')[0]))[0]))
    return counts, f'官網各船型合計 {sum(counts.values())} 艘，口徑含合資及在建船。' + summary(counts), None, None


def wisdom(raw):
    text = raw.decode('utf-8-sig')
    match = re.search(r'\blet\s+dataCurrentFleets\s*=\s*(\[.*?\])\s*;', text, re.S)
    require(match, 'Official Wisdom fleet data array absent')
    rows = json.loads(match[1])
    mapping = {'Panamax': 'panamax', 'Supramax': 'supra', 'Handy': 'handy',
               'Small Handy': 'small', 'Other': 'other'}
    require(rows and len({r['current_fleet_id'] for r in rows}) == len(rows)
            and len({r['vessel_name'].strip().casefold() for r in rows}) == len(rows),
            'Duplicate or empty Wisdom vessel roster')
    counts, ownership = Counter(), Counter()
    for row in rows:
        kind = row['ship_type'].strip()
        require(kind in mapping and row['ownership'] in ('Wisdom Owned', 'Manage Only'),
                'New Wisdom fleet ship type or ownership')
        counts[mapping[kind]] += 1
        ownership[row['ownership']] += 1
    latest = max(r['updated_at'][:10].replace('/', '-') for r in rows)
    require(re.fullmatch(r'20\d{2}-\d\d-\d\d', latest), 'Invalid Wisdom source record date')
    basis = f'最近一筆逐船紀錄 {latest.replace("-", "/")}'
    return counts, (f'官網逐船共 {len(rows)} 艘，自有 {ownership["Wisdom Owned"]}、代管 '
                    f'{ownership["Manage Only"]}。紀錄日期為個別船舶維護日期。' + summary(counts)), basis, latest


def cmt(raw):
    doc = document(raw)
    counts, planned, names = Counter(), [], set()
    for li in doc.xpath('//li[contains(concat(" ",normalize-space(@class)," "), " list-item ")]'):
        title = li.xpath('.//h5[contains(@class,"title")]')
        dwt = li.xpath('.//*[contains(@class,"detail-item") and contains(@class,"dwt")]//*[contains(@class,"value")]')
        if not (title and dwt):
            continue
        name = node_text(title[0])
        if not re.fullmatch(r'\d[\d,.]*', node_text(dwt[0])):
            continue
        require(name and name not in names, 'Duplicate CMT roster entry')
        names.add(name)
        amount = number(node_text(dwt[0]))
        if re.fullmatch(r'(?:H\d+|BC210K-\d+)', name):
            planned.append(name)
        else:
            require(name.startswith('中華') and amount >= 120_000, 'Unexpected CMT named vessel classification')
            counts['cape'] += 1
    require(counts, 'No named CMT vessels parsed')
    return counts, f'官網具名船 {sum(counts.values())} 艘。另列 {len(planned)} 艘船號新船，主表只計具名船。', None, None


def sincere(raw):
    doc = document(raw)
    mapping = {'Double Hull Capesize': 'cape', 'Capesize Bulker': 'cape',
               'Kamsarmax': 'panamax', 'VLOC': 'vloc', 'VLCC': 'tanker'}
    counts, names = Counter(), set()
    for heading in doc.xpath('//h2'):
        title = node_text(heading)
        key = next((k for k in mapping if re.search(r'\b'+k+r'\b', title, re.I)), None)
        if not key:
            continue
        table = heading.xpath('following::table[1]')
        if not table:
            continue
        for tr in table[0].xpath('.//tr[td]'):
            values = [node_text(c) for c in tr.xpath('./td')]
            if len(values) < 3 or not re.search(r'\d[\d,]{4,}', ' '.join(values[1:])):
                continue
            ship = values[0]
            require(ship and ship not in names, 'Duplicate Sincere fleet entry')
            names.add(ship)
            counts[mapping[key]] += 1
    if not counts:
        text = node_text(doc)
        match = re.search(r'共有\s*(\d+)\s*艘.{0,130}?(\d+)\s*艘\s*Kamsarmax.{0,80}?(\d+)\s*艘\s*海岬.{0,80}?(\d+)\s*艘\s*250,000.{0,80}?(\d+)\s*艘\s*30萬', text)
        require(match, 'Sincere type rows and summary unavailable')
        total, panamax, cape, vloc, tanker = map(int, match.groups())
        counts = Counter(panamax=panamax, cape=cape, vloc=vloc, tanker=tanker)
        require(total == sum(counts.values()), 'Sincere summary does not reconcile')
    require(all(counts[key] for key in mapping.values()), 'Incomplete Sincere fleet classes')
    return counts, f'官網列示 {sum(counts.values())} 艘。' + summary(counts), None, None


def tnc(raw):
    doc = document(raw)
    counts, names, managed_tankers = Counter(), set(), 0
    mapping = {'Kamsarmax': 'panamax', 'Supramax': 'supra', 'Handysize': 'handy',
               '油輪': 'tanker', 'FERRY': 'passenger', '拖船': 'tug', '引水': 'pilot'}
    key = None
    for tr in doc.xpath('//table[contains(@class,"tw-fleet-table")]//tbody/tr'):
        heading = tr.xpath('./th//h2')
        if heading:
            title = node_text(heading[0])
            label = next((label for label in mapping if label.lower() in title.lower()), None)
            require(label, f'Unrecognized Taiwan Navigation vessel section {title}')
            key = mapping[label]
            continue
        cells = [node_text(c) for c in tr.xpath('./td')]
        if len(cells) < 4 or 'fleet-header' in tr.get('class', ''):
            continue
        name = (cells[1] or cells[0]).strip().casefold()
        require(key and name and name not in names, 'Unexpected Taiwan Navigation vessel row')
        names.add(name)
        counts[key] += 1
        managed_tankers += key == 'tanker' and any('代營' in c for c in cells)
    require(counts and all(counts[k] for k in ('panamax', 'supra', 'handy')),
            'Taiwan Navigation bulk fleet rows incomplete')
    return counts, summary(counts) + f'其中油輪 {managed_tankers} 艘代營，船型採官網分類。', None, None


def swnav(raw):
    doc = document(raw)
    mapping = {'1': 'panamax', '2': 'panamax', '3': 'ultra', '5': 'handy',
               '6': 'multi', '8': 'passenger'}
    counts = column_counts(doc.xpath('//*[@id="ship"]//a[contains(@href,"/ships?id=")]'), mapping,
                           lambda item: re.search(r'id=(\d+)', item.get('href'))[1],
                           lambda item: int(re.search(r'艘數\s*(\d+)', node_text(item))[1]))
    return counts, '依官網船型，Panamax 與 Kamsarmax 合列。' + summary(counts), None, None


def franbo(raw):
    doc = document(raw)
    counts, names = Counter(), set()
    for tr in doc.xpath('//*[contains(@class,"fleet-module")]//tbody/tr[@data-href]'):
        row = [node_text(c) for c in tr.xpath('./td')]
        require(len(row) >= 6 and row[0] and row[0] not in names, 'Invalid Franbo vessel roster')
        names.add(row[0])
        kind = row[5].casefold()
        if kind == 'bulk carrier':
            dwt = number(row[3])
            require(20_000 <= dwt <= 400_000, 'Franbo bulk carrier DWT out of range')
            if dwt >= 200_000:
                key = 'vloc'
            elif dwt >= 120_000:
                key = 'cape'
            elif dwt >= 65_000:
                key = 'panamax'
            elif dwt >= 60_000:
                key = 'ultra'
            elif dwt >= 45_000:
                key = 'supra'
            elif dwt >= 42_000:
                key = 'otherBulk'
            else:
                key = 'handy'
        else:
            key = {'general cargo': 'cargo', 'multi-purpose': 'multi'}.get(kind)
            require(key, f'Unrecognized Franbo type {row[5]}')
        counts[key] += 1
    expected = re.search(r'(?:Vessel Count\s*(\d+)|(\d+)\s*Vessel Count)', node_text(doc), re.I)
    require(counts and expected and sum(counts.values()) == int(next(x for x in expected.groups() if x)),
            'Franbo roster does not match official vessel count')
    return counts, f'官網逐船共 {len(names)} 艘。散裝船依 DWT 區間歸類。' + summary(counts), None, None


PARSERS = {'裕民': uming, '慧洋-KY': wisdom, '中航': cmt, '新興': sincere,
           '台航': tnc, '四維航': swnav, '正德': franbo}


def update_company(item, today):
    url = SNC if item['name'] == '新興' else item['url']
    try:
        counts, note, basis, source_date = PARSERS[item['name']](fetch(url))
    except Exception:
        if item['name'] != '新興':
            raise
        url = 'https://www.snc.com.tw/新興船隊/'
        counts, note, basis, source_date = sincere(fetch(url))
    require(not source_date or source_date <= today, 'Source record date is in the future')
    bulk = [counts.get(key) or None for key in BULK]
    other = [counts.get(key) or None for key in OTHER]
    current = sum(v or 0 for v in item['bulk'] + item['other'])
    require(current * 0.5 <= sum(counts.values()) <= current * 1.6, 'Large fleet change requires review')
    item.update(bulk=bulk, other=other, note=note,
                basis=basis or '官網未標示全船隊基準日', url=url, sourceDate=source_date)
    return source_date or f'{sum(counts.values())} 艘'
