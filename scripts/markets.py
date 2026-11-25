from datetime import date
from common import (api, apply_month_history, date_shift, display_start, histories_to_maps,
                    month_shift, number, periods, positive, require)

MDIC = 'https://api-comexstat.mdic.gov.br/general?language=en'
FGIS = 'https://agtransport.usda.gov/resource/sruw-w49i.json'
CODES = {'1005': 'corn', '1201': 'soy', '1001': 'wheat', '2601': 'iron'}
GRAINS = {'CORN': 'corn', 'SOYBEANS': 'soy', 'WHEAT': 'wheat'}
FREIGHT_IDS = {'BDI': 'EMI00107664', 'BCI': 'EMI00107666',
               'BPI': 'EMI00107665', 'BSI': 'EMI00107667'}


def read_freight(code, today, previous):
    endpoint = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
    index = FREIGHT_IDS[code]
    response = api(endpoint, query={'reportName': 'RPT_INDUSTRY_INDEX',
                   'columns': 'ALL', 'filter': f'(INDICATOR_ID="{index}")',
                   'pageSize': 500, 'pageNumber': 1,
                   'sortColumns': 'REPORT_DATE', 'sortTypes': -1})
    reported = response['result']['data']
    require(all(row['INDICATOR_ID'] == index for row in reported), 'Freight code mismatch')
    rows = [(row['REPORT_DATE'][:10], row['INDICATOR_VALUE']) for row in reported]
    return freight_rows(rows, today, previous)


def freight_rows(rows, today, previous):
    parsed = {}
    for period, value in rows:
        if date.fromisoformat(period).weekday() >= 5:
            continue
        require(period <= today and period not in parsed, 'Future or duplicate freight date')
        parsed[period] = number(value)
    require(parsed and max(parsed) >= previous, 'Provider returned an older freight snapshot')
    return parsed


def update_freight(payload, today, code):
    prior = payload['rows'][-1]['date']
    fresh = read_freight(code, today, prior)
    original = {r['date']: r['value'] for r in payload['rows']}
    changed = [m for m, v in fresh.items() if m in original and original[m] != v]
    result = original | fresh
    if result != original:
        payload.update(retrieved=today, rows=[{'date': m, 'value': result[m]}
                                              for m in sorted(result)],
                       sourceUrl=f'https://data.eastmoney.com/cjsj/hyzs_list_{FREIGHT_IDS[code]}.html')
        payload['validation'] = {
            'note': '東方財富公開轉載。同一來源合併，排除週末，未補缺值。',
            'overlapChanged': sorted(changed), 'previousLatest': prior}
    return max(result)


def read_brazil(start, end, headings, china=False):
    filters = [{'filter': 'heading', 'values': headings}, {'filter': 'via', 'values': ['01']}]
    if china:
        filters.append({'filter': 'country', 'values': ['160']})
    response = api(MDIC, post={'flow': 'export', 'monthDetail': True,
                   'period': {'from': start, 'to': end}, 'filters': filters,
                   'details': ['heading'], 'metrics': ['metricKG']})
    rows = response['data']['list']
    require(rows, 'Comex Stat returned no monthly rows')
    result = {('ironChina' if china else CODES[h]): {} for h in headings}
    for row in rows:
        heading = str(row['headingCode']).zfill(4)
        key = 'ironChina' if china else CODES[heading]
        period = f"{row['year']}-{int(row['monthNumber']):02d}"
        require(start <= period <= end and period not in result[key] and heading in headings,
                'Unexpected or duplicate Comex Stat row')
        amount = number(row['metricKG']) / 1000
        require(amount >= 0, 'Negative export total')
        result[key][period] = amount
    return result


def update_brazil(history, dashboard, today):
    old = histories_to_maps(history)
    maps = {key: values.copy() for key, values in old.items()}
    year = int(today[:4])
    end = month_shift(today[:7], -1)
    start = f'{min(year-1, int(history["displayEnd"][:4]))}-01'
    fresh = read_brazil(start, end, list(CODES))
    fresh.update(read_brazil(start, end, ['2601'], china=True))
    for key, values in fresh.items():
        maps[key].update(values)
    core = ('corn', 'soy', 'iron', 'ironChina')
    complete = set.intersection(*(set(m for m, v in maps[key].items() if v is not None)
                                  for key in core))
    prior = history['displayEnd']
    latest = max(complete)
    require(latest >= prior and all(prior in fresh[key] for key in core),
            'Source lacks a known month or a required combination')
    display_year = int(latest[:4])
    require(all(maps[key].get(m) is not None for key in core
                for m in periods(f'{display_year}-01', latest)),
            'Missing month in the current-year Brazil series')
    if maps != old:
        apply_month_history(history, maps, latest)
        history.update(retrieved=today, note='Comex Stat official API. HS 1001, 1005, 1201, 2601; maritime mode. Missing observations remain blank.')
        same_year = list(periods(f'{display_year}-01', latest))
        last_year = list(periods(f'{display_year-1}-01', f'{display_year-1}-12'))
        dashboard.update(brazilPeriod=latest, brazilYear=display_year, brazilRetrieved=today,
                         brazil={k: [maps[k].get(m) for m in same_year] for k in CODES.values()},
                         brazilPrevious={k: [maps[k].get(m) for m in last_year] for k in CODES.values()},
                         brazilChina=[maps['ironChina'].get(m) for m in same_year],
                         brazilChinaPrevious=[maps['ironChina'].get(m) for m in last_year])
        dashboard['ironFlowSnapshot']['brazil'].update(
            period=latest, tonnes=maps['iron'][latest], previousMonth=maps['iron'].get(month_shift(latest, -1)),
            previousYear=maps['iron'].get(month_shift(latest, -12)), checked=today)
        dashboard['comparisonNotes']['brazil'] = 'Comex Stat 官方 API，同一海運與商品口徑。'
    return latest


def read_us(today, start):
    where = (f"date between '{start}T00:00:00.000' and '{today}T23:59:59.999'"
             " AND type_carrier_text='SHIP' AND grain in ('WHEAT','CORN','SOYBEANS')")
    params = {'$select': 'date,grain,sum(mt) as metric_tons', '$where': where,
              '$group': 'date,grain', '$order': 'date,grain', '$limit': 10000}
    rows = api(FGIS, query=params)
    require(isinstance(rows, list) and 0 < len(rows) < 10000, 'Unexpected FGIS response size')
    result = {k: {} for k in GRAINS.values()}
    for row in rows:
        day, key = row['date'][:10], GRAINS[row['grain']]
        tonnes = number(row['metric_tons'])
        date.fromisoformat(day)
        require(start <= day <= today and tonnes >= 0 and day not in result[key],
                'Invalid FGIS weekly row')
        result[key][day] = tonnes
    return result


def update_us(history, dashboard, today):
    prior = history['displayEnd']
    fresh = read_us(today, date_shift(prior, -105))
    latest = max(set.intersection(*(set(x) for x in fresh.values())))
    require(latest >= prior and latest == max(max(x) for x in fresh.values()),
            'Latest FGIS week is older or not complete for the three grains')
    original = history['series']
    maps = {k: dict(sorted((original[k] | fresh[k]).items())) for k in original}
    if maps != original:
        wow, yoy = date_shift(latest, -7), date_shift(latest, -364)
        weeks = [date_shift(latest, -7 * i) for i in range(4)]
        history.update(series=maps, retrieved=today, displayEnd=latest,
                       displayStart=display_start(latest) + '-01',
                       years=list(range(int(latest[:4])-4, int(latest[:4])+1)))
        dashboard.update(usPeriod=latest, usPublished=None, usRetrieved=today,
                         usComparisonPeriod=yoy, usPreviousWeekPeriod=wow, usWeeks=maps,
                         us={k: v[latest] for k, v in maps.items()},
                         usPrevious={k: v.get(yoy) for k, v in maps.items()},
                         usLastWeek={k: v.get(wow) for k, v in maps.items()},
                         usFourWeekAverage={k: sum(v[m] for m in weeks) / 4
                                            if all(m in v for m in weeks) else None
                                            for k, v in maps.items()})
        dashboard['comparisonNotes']['usPreviousYear'] = f'{latest} 對比 {yoy}（52 週前）'
    return latest
