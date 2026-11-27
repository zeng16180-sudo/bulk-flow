import argparse
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from hashlib import sha256
from pathlib import Path
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

from common import ROOT, api, dump, load, number, periods, require
from update_data import write_changed

SITE = ROOT / 'site'
ASSET = 'equity-market-data.js'
VARIABLE = 'FLOW_EQUITY_MARKET'
TWSE = 'https://www.twse.com.tw'
TPEX = 'https://www.tpex.org.tw'
MARKETS = {'TWSE': ('2605','2606','2612','2617','2637','5608'), 'TPEx': ('2641',)}
FIELDS = {
    'quotes': ('close','volume'),
    'valuation': ('pe','pb','yield'),
    'institutions': ('foreign','trust','dealer','total'),
    'margin': ('long','short'),
}
LABELS = {'quotes':'收盤價與成交量', 'valuation':'本益比與股價淨值比',
          'institutions':'三大法人買賣超', 'margin':'融資融券餘額'}
SOURCES = {
    'TWSE': {
        'quotes': TWSE+'/zh/trading/historical/stock-day.html',
        'valuation': TWSE+'/zh/trading/historical/bwibbu-day.html',
        'institutions': TWSE+'/fund/T86?response=html&selectType=ALLBUT0999',
        'margin': TWSE+'/zh/trading/margin/mi-margn.html',
    },
    'TPEx': {
        'quotes': TPEX+'/zh-tw/mainboard/trading/info/stock-pricing.html',
        'valuation': TPEX+'/zh-tw/mainboard/trading/info/stock-pe.html',
        'institutions': TPEX+'/www/zh-tw/insti/dailyTrade?type=Daily&sect=EW&response=html',
        'margin': TPEX+'/zh-tw/mainboard/trading/margin-trading/transactions.html',
    },
}


def iso_day(value):
    parts = re.findall(r'\d+', str(value))
    if len(parts) == 1 and len(parts[0]) in (7,8):
        text = parts[0]
        parts = [text[:-4],text[-4:-2],text[-2:]]
    require(len(parts)==3, f'Unknown trading date {value}')
    y,m,d = map(int, parts)
    return date(y+1911 if y<1911 else y,m,d).isoformat()


def integer(cell):
    n = number(cell)
    require(n.is_integer(), f'Expected full share count or lots, got {cell}')
    return int(n)


def ratio(cell):
    if cell is None or str(cell).strip() in ('','-','--','---','N/A','NA','不適用'):
        return None
    return number(cell)


def report_table(reply, required):
    tables = reply.get('tables', [reply])
    found = [t for t in tables if required <= set(t.get('fields', [])) and t.get('data')]
    require(len(found)==1, f'Missing or ambiguous report table ({", ".join(sorted(required))})')
    return found[0]['fields'],found[0]['data']


def indexed_report(reply, market, required):
    codes = {'證券代號','股票代號','代號'}
    found = []
    for table in reply.get('tables', [reply]):
        fields = table.get('fields', [])
        if not required <= set(fields) or not codes.intersection(fields):
            continue
        key = next(i for i,v in enumerate(fields) if v in codes)
        selected = {}
        for row in table.get('data', []):
            if len(row)<=key:
                continue
            code = str(row[key]).strip()
            if code in MARKETS[market]:
                require(code not in selected, f'Duplicate report row for {code}')
                selected[code] = row
        if selected:
            found.append((fields,selected))
    require(len(found)==1, f'Missing or ambiguous {market} table ({", ".join(sorted(required))})')
    return found[0]


def evaluations(fields, row):
    p,e,y = (ratio(row[fields.index(field)]) for field in ('本益比','股價淨值比','殖利率(%)'))
    return {'pe':p if p and p>0 else None,'pb':e if e and e>0 else None,
            'yield':y if y is not None and y>=0 else None}


def date_query(market, day):
    return day.replace('-', '' if market=='TWSE' else '/')


def request_daily(market, key, day):
    query = {'date':date_query(market,day)}
    if market == 'TWSE':
        paths = {'quotes':'/exchangeReport/MI_INDEX','valuation':'/exchangeReport/BWIBBU_d',
                 'institutions':'/rwd/zh/fund/T86','margin':'/rwd/zh/marginTrading/MI_MARGN'}
        if key == 'quotes':
            query['type'] = 'ALLBUT0999'
        else:
            query['selectType'] = 'ALLBUT0999' if key=='institutions' else 'ALL'
        query['response'] = 'json'
        try:
            return api(TWSE+paths[key],query=query)
        except HTTPError as error:
            legacy = {'institutions':'/fund/T86','margin':'/exchangeReport/MI_MARGN'}
            if key not in legacy or error.code != 428:
                raise
            return api(TWSE+legacy[key],query=query)
    paths = {'quotes':'afterTrading/dailyQuotes','valuation':'afterTrading/peQryDate',
             'institutions':'insti/dailyTrade','margin':'margin/balance'}
    if key == 'institutions':
        query.update(type='Daily',sect='EW')
    query['response'] = 'json'
    return api(TPEX+'/www/zh-tw/'+paths[key],query=query)


def institutions(market, fields, row):
    if market == 'TWSE':
        def val(name):
            return integer(row[fields.index(name)])
        foreign = val('外陸資買賣超股數(不含外資自營商)') + val('外資自營商買賣超股數')
        trust = val('投信買賣超股數')
        dealer = val('自營商買賣超股數')
        total = val('三大法人買賣超股數')
    else:
        require(len(fields)==24 and all(fields[i]=='買賣超股數' for i in (4,7,10,13,22)) and
                fields[23]=='三大法人買賣超股數合計','TPEx institutional columns changed')
        foreign,trust,dealer,total = (integer(row[i]) for i in (10,13,22,23))
        require(foreign == integer(row[4])+integer(row[7]),'TPEx foreign components do not reconcile')
    require(total==foreign+trust+dealer, 'Institutional total does not reconcile')
    return dict(foreign=foreign,trust=trust,dealer=dealer,total=total)


def margins(market, fields, row):
    if market == 'TWSE':
        indices = [i for i,v in enumerate(fields) if v=='今日餘額']
        require(indices==[6,12], 'TWSE margin balance columns changed')
    else:
        indices = [fields.index(v) for v in ('資餘額','券餘額')]
    long,short = (integer(row[i]) for i in indices)
    require(min(long,short)>=0,'Negative margin balance')
    return dict(long=long,short=short)


def daily(market, key, day):
    reply = request_daily(market,key,day)
    require(str(reply.get('stat','')).lower()=='ok',f'{market} 尚無 {day} 的{LABELS[key]}')
    require(iso_day(reply.get('date'))==day,f'{market} 回傳日期與查詢日期不一致')
    price_field = '收盤價' if market=='TWSE' else '收盤'
    columns = {
        'valuation': {'本益比','股價淨值比','殖利率(%)'},
        'quotes': {price_field,'成交股數'},
        'institutions': {'三大法人買賣超股數' if market=='TWSE' else '三大法人買賣超股數合計'},
        'margin': {'今日餘額'} if market=='TWSE' else {'資餘額','券餘額'},
    }
    fields,rows = indexed_report(reply,market,columns[key])
    if key=='valuation':
        return {c:evaluations(fields,r) for c,r in rows.items()}
    if key=='institutions':
        return {c:institutions(market,fields,r) for c,r in rows.items()}
    if key=='margin':
        return {c:margins(market,fields,r) for c,r in rows.items()}
    close_col, volume_col = (fields.index(v) for v in (price_field,'成交股數'))
    result = {}
    for c,r in rows.items():
        close = ratio(r[close_col])
        volume = integer(r[volume_col])
        if close is not None and close>0 and volume>=0:
            result[c] = {'close':close,'volume':volume}
    return result


def valuation_month(market, code, month):
    if market=='TWSE':
        url = TWSE+'/exchangeReport/BWIBBU'
        query = {'stockNo':code,'date':month.replace('-','')+'01','response':'json'}
    else:
        url = TPEX+'/www/zh-tw/afterTrading/peQryStock'
        query = {'code':code,'date':month.replace('-','/')+'/01','response':'json'}
    reply = api(url,query=query)
    required = {'日期','本益比','股價淨值比','殖利率(%)'}
    fields,rows = report_table(reply,required)
    index = fields.index('日期')
    result = {}
    for row in rows:
        day = iso_day(row[index])
        require(day.startswith(month+'-') and day not in result,f'Wrong month or duplicate valuation day for {code}')
        result[day] = evaluations(fields,row)
    return result


def prepare(seed):
    companies = {code:{key:{} for key in FIELDS} for market in MARKETS.values() for code in market}
    for code,company in companies.items():
        for record in seed['companies'][code]['quotes']:
            company['quotes'][record['date']] = {k:v for k,v in record.items() if k != 'date'}
    days = sorted({d for company in companies.values() for d in company['quotes']})
    require(len(days)>=200,'Insufficient trade days in the initial close series')
    return {'companies':companies,'tradingDays':days,'sources':SOURCES}


def archive_cutoff(today):
    end = date.fromisoformat(today)
    return end.replace(year=end.year-1,day=28 if (end.month,end.day)==(2,29) else end.day).isoformat()


def record_table(payload, key, day, result):
    for code,row in result.items():
        records = payload['companies'][code][key]
        if key=='quotes' and row.get('volumeApproximate') and day in records and not records[day].get('volumeApproximate'):
            continue
        records[day] = row


def backfill(payload, cache):
    cache.mkdir(parents=True,exist_ok=True)
    days = payload['tradingDays']
    jobs = [
        (market,'valuation',month,code) for market,codes in MARKETS.items() for code in codes
        for month in periods(days[0][:7],days[-1][:7])
    ] + [
        (market,key,day,None) for day in reversed(days[-60:]) for market in MARKETS
        for key in ('institutions','margin')
    ]

    def collect(job):
        market,key,period,code = job
        path = cache / ('-'.join(filter(None,job))+'.json')
        try:
            if path.is_file():
                return load(path),None
            rows = valuation_month(market,code,period) if code else daily(market,key,period)
            path.write_text(dump(rows),encoding='utf-8')
            return rows,None
        except Exception as e:
            return None,f'{market} {key} {period} {code or ""} · {type(e).__name__}: {e}'

    failures = []
    with ThreadPoolExecutor(max_workers=5) as pool:
        for index,(job,(rows,error)) in enumerate(zip(jobs,pool.map(collect,jobs)),1):
            market,key,period,code = job
            if error:
                failures.append(error)
                print(error,flush=True)
            elif code:
                quotes = payload['companies'][code]['quotes']
                payload['companies'][code][key].update({d:r for d,r in rows.items() if d in quotes})
            else:
                record_table(payload,key,period,rows)
            if index%40==0 or index==len(jobs):
                print(f'Historical reports {index}/{len(jobs)}',flush=True)
    return failures


def verify(payload, seeded=False):
    companies = payload['companies']
    require(set(companies)=={c for codes in MARKETS.values() for c in codes},'Company list mismatch')
    days = payload['tradingDays']
    require(days==sorted(set(days)) and len(days)>=190,'Trading calendar is incomplete or unordered')
    known_days = set(days)
    for code,company in companies.items():
        require(set(company)==set(FIELDS) and len(company['quotes'])>=190,f'{code} quote history missing')
        for kind,rows in company.items():
            require(set(rows)<=known_days,f'{code} {kind} contains dates outside the calendar')
            for day,row in rows.items():
                date.fromisoformat(day)
                require(set(FIELDS[kind])<=set(row),f'{code} {kind} {day} missing fields')
                if kind=='institutions':
                    require(row['total']==row['foreign']+row['trust']+row['dealer'],f'{code} institutional sums differ')
                if kind=='quotes':
                    require(row['close']>0 and row['volume']>=0,f'{code} invalid share price or volume')
                if kind=='margin':
                    require(row['long']>=0 and row['short']>=0,f'{code} invalid margin balance')
            if seeded:
                required_days = set(company['quotes'] if kind=='valuation' else days[-60:])
                require(required_days<=set(rows),f'{code} {kind} has {len(required_days-set(rows))} initial gaps')
    if checks := payload.get('checks'):
        require(datetime.fromisoformat(checks['checkedAt']).utcoffset() is not None,'Missing check timezone')
        require(set(checks['markets'])==set(MARKETS),'Market check coverage differs from the archive')
        for market,groups in checks['markets'].items():
            require(set(groups)==set(FIELDS),f'{market} source check list changed')
            for row in groups.values():
                require(row['result'] in ('updated','unchanged','waiting'),'Unknown source result')
                require(row['officialDay'] is None or row['officialDay'] in known_days,'Unknown official trading day')
                require(isinstance(row['pending'],int) and row['pending']>=0,'Invalid missing trading day count')


def write_asset(site,payload):
    content = dump(payload,VARIABLE)
    digest = sha256(content.encode()).hexdigest()[:12]
    index = (site/'index.html').read_text(encoding='utf-8')
    pattern = rf'src="{re.escape(ASSET)}(?:\?[^"]*)?"'
    index,changes = re.subn(pattern,f'src="{ASSET}?v={digest}"',index)
    require(changes==1,'The website must reference the equity market data once')
    write_changed(site,{ASSET:content,'index.html':index})


def update_calendar(payload,today):
    days = set(payload['tradingDays'])
    first = max(archive_cutoff(today)[:7],max(days)[:7])
    problems = []
    for month in periods(first,today[:7]):
        try:
            reply = api(TWSE+'/exchangeReport/FMTQIK',query={
                'date':month.replace('-','')+'01','response':'json',
            })
            fields,rows = report_table(reply,{'日期','成交股數'})
            actual = {iso_day(row[fields.index('日期')]) for row in rows}
            require(all(day[:7]==month for day in actual),'Trading calendar returned a different month')
            days.update(day for day in actual if day<=today)
        except Exception as error:
            problems.append(f'{month} {type(error).__name__}: {error}')
    payload['tradingDays'] = sorted(days)
    return problems


def ranges(payload,today):
    days = [day for day in payload['tradingDays'] if day<=today]
    recent = [day for day in days if day>=archive_cutoff(today)]
    return {'quotes':recent,'valuation':recent,'institutions':days[-60:],'margin':days[-60:]}


def missing_days(payload,market,key,days):
    return [day for day in days if any(
        day not in payload['companies'][code][key] for code in MARKETS[market]
    )]


def update_market(payload,today):
    calendar_problems = update_calendar(payload,today)
    windows = ranges(payload,today)
    jobs = []
    statuses = {}
    for market in MARKETS:
        for key,days in windows.items():
            target = days[-1] if days else None
            missing = [day for day in missing_days(payload,market,key,days) if day!=target]
            requested = ([target] if target else []) + missing[:7]
            jobs.extend((market,key,day) for day in requested)
            statuses[(market,key)] = {'target':target,'seen':None,'updated':0,'errors':[]}

    def collect(job):
        market,key,day = job
        try:
            rows = daily(market,key,day)
            require(rows,f'{market} 未回傳可用的 {LABELS[key]}')
            return rows,None
        except Exception as error:
            return None,f'{day} {type(error).__name__}: {error}'

    with ThreadPoolExecutor(max_workers=4) as pool:
        for (market,key,day),(rows,error) in zip(jobs,pool.map(collect,jobs)):
            state = statuses[market,key]
            if error:
                state['errors'].append(error)
                continue
            state['seen'] = max(state['seen'] or day,day)
            state['updated'] += sum(payload['companies'][code][key].get(day) != row for code,row in rows.items())
            record_table(payload,key,day,rows)

    for (market,key),state in statuses.items():
        last = sorted({max(payload['companies'][code][key],default='') for code in MARKETS[market]})
        state['website'] = ' ～ '.join(x for x in last if x) or '—'
        state['pending'] = len(missing_days(payload,market,key,windows[key]))
    return statuses,calendar_problems


def check_result(state, calendar_problems):
    if state['seen'] != state['target'] or state['pending'] or calendar_problems or state['errors']:
        return 'waiting'
    return 'updated' if state['updated'] else 'unchanged'


def store_checks(payload,statuses,calendar_problems,checked_at):
    markets = {market:{} for market in MARKETS}
    for (market,key),state in statuses.items():
        markets[market][key] = {
            'result': check_result(state,calendar_problems),
            'officialDay': state['seen'],
            'pending': state['pending'],
        }
    payload['checks'] = {'checkedAt':checked_at, 'markets':markets}


def report(statuses,calendar_problems,check_only):
    lines = ['## 航商盤後資料查核\n\n',
             ('本次為試跑，「網站採用交易日」顯示候選結果。\n\n' if check_only else
              '「網站採用交易日」於本次 GitHub Pages 部署成功後生效。\n\n')]
    for problem in calendar_problems:
        lines.append(f'- 交易日曆查核待重試 · {problem}\n')
    if calendar_problems:
        lines.append('\n')
    lines.extend(['| 市場／來源 | 結果 | 本次核驗官方交易日 | 網站採用交易日 | 說明 |\n',
                  '|---|---|---|---|---|\n'])
    labels = {'waiting':'待補／自動重試','updated':'已更新','unchanged':'已同步'}
    for (market,key),state in statuses.items():
        errors = state['errors']
        result = labels[check_result(state,calendar_problems)]
        notes = [f"新增或修訂 {state['updated']} 筆"] if state['updated'] else []
        if state['pending']:
            notes.append(f"{state['pending']} 個交易日仍有缺項")
        if errors:
            notes.append(errors[0][:200])
        row = [market+' '+LABELS[key],result,state['seen'] or '—',state['website'],' · '.join(notes) or '—']
        lines.append('| '+' | '.join(str(s).replace('|','/').replace('\n',' ') for s in row)+' |\n')
        print(' | '.join(row),flush=True)
    if summary := os.getenv('GITHUB_STEP_SUMMARY'):
        with Path(summary).open('a',encoding='utf-8') as out:
            out.writelines(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--site',type=Path,default=SITE)
    parser.add_argument('--bootstrap',type=Path)
    parser.add_argument('--cache',type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--verify-only',action='store_true')
    modes.add_argument('--check-only',action='store_true')
    options = parser.parse_args()
    if options.bootstrap:
        require(options.cache,'Bootstrap requires a cache directory')
        payload = prepare(load(options.bootstrap))
        failures = backfill(payload,options.cache)
        print(f'{len(failures)} historical requests need retry',flush=True)
        verify(payload,seeded=True)
        write_asset(options.site,payload)
        return
    payload = load(options.site/ASSET)
    verify(payload)
    if options.verify_only:
        print('Equity market snapshot verified.')
        return
    now = datetime.now(ZoneInfo('Asia/Taipei'))
    statuses,failures = update_market(payload,now.date().isoformat())
    checked_at = datetime.now(ZoneInfo('Asia/Taipei')).isoformat(timespec='seconds')
    store_checks(payload,statuses,failures,checked_at)
    verify(payload)
    if not options.check_only:
        write_asset(options.site,payload)
    report(statuses,failures,options.check_only)


if __name__=='__main__':
    main()
