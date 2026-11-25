"""Parse USDA WASDE World supply and use tables."""
from __future__ import annotations
from pathlib import Path
from decimal import Decimal
from datetime import datetime
from pypdf import PdfReader
import io
import re
MONTHS='Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split()
MONTH_RX='(?:'+'|'.join(MONTHS)+')'
NUM_RX=r'-?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}'
ROW_RX=re.compile(r'^\s*('+NUM_RX+r')(?:\s+('+NUM_RX+r')){6}\s*$')

def values(t):
    parts=re.findall(NUM_RX,t)
    if len(parts)!=7: raise ValueError(f'Expected exactly7numericcells: {t!r}')
    if re.sub(NUM_RX,'',t).strip(): raise ValueError(f'Unexpected nonnumeric cells: {t!r}')
    return [int(Decimal(x.replace(',',''))*1000) for x in parts]

def parse(pdf):
    raw=Path(pdf).read_bytes() if isinstance(pdf,(str,Path)) else pdf
    if not raw.startswith(b'%PDF'):raise ValueError('Not an actual PDF')
    reader=PdfReader(io.BytesIO(raw));first=reader.pages[0].extract_text()
    # Cover reportdate governs freshness; filename/schedule never suffices.
    meta=re.search(r'WASDE\s*[-–]\s*(\d+)\s+Approved by the World Agricultural Outlook Board\s+([A-Za-z]+\s+\d{1,2},\s+20\d{2})',first)
    if not meta:raise ValueError('Cannot identify WASDE cover/date')
    date=datetime.strptime(re.sub(r'\s+',' ',meta[2]),'%B %d, %Y').date()
    page_texts=[p.extract_text() for p in reader.pages]
    out={'reportId':'WASDE '+meta[1],'reportDate':date.isoformat(),'reportMonthAbbr':MONTHS[date.month-1],'unit':'1000 metric tonnes','commodities':{}}
    for key,name in [('soy','Soybean'),('corn','Corn'),('wheat','Wheat')]:
        selected=[]
        title=re.compile(r'^\s*World\s+'+name+r'\s+Supply\s+and\s+Use\s*(?:\d+/)?\s*(?:\(Cont.d\.\))?\s*$',re.I|re.M)
        for pn,text in enumerate(page_texts,1):
            if title.search(text):selected.append((pn,text))
        if not selected:raise ValueError('Missing exact World table '+name)
        season=None;status=None;rows=[]
        for pn,text in selected:
            waiting=None
            for line in text.splitlines():
                if m:=re.match(r'^\s*(20\d{2}/\d{2})(?:\s+(Est\.?|Proj\.?))?(?:\s|$)',line):
                    season=m[1];status={'Est.':'estimate','Est':'estimate','Proj.':'forecast','Proj':'forecast',None:'historical'}[m[2]];waiting=None
                if not season:continue
                if m:=re.match(r'^\s*(World\s+\d+/|China)\s+(?:('+MONTH_RX+r')\s+)?('+NUM_RX+r'.*)$',line):
                    entity='World' if m[1].startswith('World') else 'China'
                    v=values(m[3]);cols=['beginningStocks','production','imports','globalCrush' if key=='soy' else 'feedResidual','domesticConsumption','exports','endingStocks']
                    row=dict(zip(cols,v));row.update(season=season,status=status,entity=entity,month=m[2],page=pn);row['stocksUsePct']=row['endingStocks']/row['domesticConsumption']*100
                    rows.append(row);waiting=(entity,season,status) if m[2] else None
                elif waiting and (m:=re.match(r'^\s*('+MONTH_RX+r')\s+('+NUM_RX+r'.*)$',line)):
                    entity,season,status=waiting;v=values(m[2]);row=dict(zip(cols,v));row.update(season=season,status=status,entity=entity,month=m[1],page=pn);row['stocksUsePct']=row['endingStocks']/row['domesticConsumption']*100;rows.append(row);waiting=None
                elif line.strip():
                    waiting=None
        if not rows:raise ValueError('No rows parsed '+key)
        target=max(row['season'] for row in rows)
        current=[r for r in rows if r['entity']=='World' and r['season']==target and r['month']==MONTHS[date.month-1]]
        if len(current)!=1:raise ValueError('Not exactly one current forecast '+key)
        for row in rows:
            if row['entity']=='China' and key=='soy':row['chinaCrush']=row.pop('globalCrush')
        out['commodities'][key]={'targetSeason':target,'pages':[p for p,_ in selected],'rows':rows}
    return out

if __name__=='__main__':
    for filename in sys.argv[1:]:
        d=parse(filename)
        print(json.dumps(d,ensure_ascii=False,indent=2))
