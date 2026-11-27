(() => {
  'use strict';

  const root = document.getElementById('equity-research');
  const data = window.FLOW_EQUITY_RESEARCH;
  if (!root || !data) return;

  const $ = id => root.querySelector('#' + id);
  const names = {
    '2606': '裕民', '2637': '慧洋-KY', '2612': '中航', '2605': '新興',
    '2617': '台航', '5608': '四維航', '2641': '正德',
  };
  const order = ['2606','2637','2612','2605','2617','5608','2641'];
  const marketData = window.FLOW_EQUITY_MARKET;
  const chipDays = (marketData?.tradingDays || []).slice(-60);
  const companies = Object.fromEntries(Object.entries(data.companies).map(([code, firm]) => {
    const series = marketData?.companies[code];
    if (!series) return [code,firm];
    const dates = Object.keys(series.valuation).sort();
    const latest = dates.at(-1);
    const sources = marketData.sources[firm.market];
    return [code,{...firm, ...series,
      quotes:Object.keys(series.quotes).sort().map(date=>({date,...series.quotes[date]})),
      valuation:latest ? {...series.valuation[latest],date:latest,source:sources.valuation} : firm.valuation,
      valuations:series.valuation, quoteSource:sources.quotes, sources,
    }];
  }));
  const monthlyData = window.FLOW_COMPANY_PERFORMANCE;
  const revenueMonths = monthlyData?.months || [];
  const financeTabs = ['earnings', 'cash', 'stock'];
  const color = 'var(--eq-accent)';
  const companySelect = $('eq-company'), quarterSelect = $('eq-quarter'), dateSlider = $('eq-trading-date');
  const monthSelect = $('eq-month'), marginSelect = $('eq-margin-type');
  const healthSelect = $('eq-health-type');
  const chipSlider = $('eq-chip-date');
  const institutionalSeries = [
    {key:'foreign',label:'外資及陸資',color:'var(--eq-foreign)'},
    {key:'trust',label:'投信',color:'var(--eq-trust)'},
    {key:'dealer',label:'自營商',color:'var(--eq-dealer)'},
  ];
  const valuationLabels = {pe:'本益比',pb:'股價淨值比'};
  const riverSteps = [10,25,50,75,90];
  const marginFields = {
    grossProfit: '毛利率',
    operatingIncome: '營益率',
    consolidatedNetIncome: '稅後淨利率',
  };
  const healthGroups = [
    {label:'償債能力', metrics:{
      currentRatio:{label:'流動比率', unit:'%'},
      interestCoverage:{label:'利息保障倍數', unit:'倍'},
    }},
    {label:'經營能力', metrics:{
      assetTurnover:{label:'總資產週轉率', unit:'次'},
      inventoryTurnover:{label:'存貨週轉率', unit:'次'},
    }},
    {label:'現金流量', metrics:{
      cashToCurrentLiabilities:{label:'營業現金對流動負債比', unit:'%'},
      cashToNetIncome:{label:'營業現金流對稅後淨利比', unit:'%'},
    }},
  ];
  const healthMetrics = Object.assign({}, ...healthGroups.map(group=>group.metrics));
  const fmt = (value, digits = 2) => Number(value).toLocaleString('zh-TW', {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  });
  const known = Number.isFinite;
  const textNum = (value, digits, unit = '') => known(value) ? fmt(value, digits) + unit : '—';
  const remapMoney = v => known(v) ? v / 100000 : null;
  const money = v => textNum(remapMoney(v), 2, ' 億');
  const difference = (now, base) => known(now) && known(base) ? now-base : null;
  const growth = (now, base) => known(now) && base > 0 ? 100*(now-base)/base : null;
  const signedChange = (value, unit, digits = 1) => known(value)
    ? (Math.abs(value) < 0.5*10**-digits ? fmt(0,digits) : (value > 0 ? '+' : '−') + fmt(Math.abs(value),digits)) + unit
    : '—';
  const profitMargin = (q, field) => q?.revenue > 0 && known(q[field]) ? 100*q[field]/q.revenue : null;
  const margin = q => profitMargin(q, 'operatingIncome');
  const date = value => value ? value.replaceAll('-', '/') : '—';
  const quarterName = value => value ? value.replace('-', ' ') : '—';
  const shortQuarter = q => q.slice(2).replace('-',' ');
  const quarterIndex = p => Number(p.slice(0,4))*4+Number(p.at(-1));
  const referenceQuarter = (rows, q, offset) => q && rows.find(
    row => quarterIndex(row.period) === quarterIndex(q.period)-offset,
  );
  const healthValue = (q, key) => {
    const value = q?.health?.[key];
    return known(value) ? value * (healthMetrics[key].unit === '%' ? 100 : 1) : null;
  };
  const recentQuarter = rows => rows.findLast(q => [q.revenue,q.operatingIncome,q.eps].some(known));
  const ttm = rows => {
    const end = rows.findLastIndex(q => [q.revenue,q.operatingIncome,q.eps].some(known));
    const list = end >= 3 ? rows.slice(end-3,end+1) : [];
    return list.length===4 && list.every((q,i) => known(q.eps) &&
      (!i || quarterIndex(q.period)===quarterIndex(list[i-1].period)+1))
      ? list.reduce((total, q) => total+q.eps, 0) : null;
  };

  let companyCode = '2606';
  let quarter = 0, selectedMonth = 0, selectedDay = 0, monthsBack = 12;
  let activeTab = 'earnings', selectedSort = 'code', sortOrder = 1;
  let stockView = 'price', selectedChip = 0;
  let callbacks = [];
  let showRevenueCursor = () => {};
  let lastWidth = 0;
  const company = () => companies[companyCode];
  let displayedQuotes = [];

  function setLink(id, url) {
    const element = $(id);
    element.hidden = !(typeof url === 'string' && url.startsWith('https://'));
    if (!element.hidden) element.href = url;
    else element.removeAttribute('href');
  }

  function card(label, value, digits, unit, detail = '', changes = []) {
    return `<div class="eq-metric"><span>${label}</span><strong${value<0?' class="eq-negative"':''}>
      ${known(value)?fmt(value,digits):'—'}${known(value)&&unit?`<span class="eq-unit">${unit}</span>`:''}</strong>
      ${detail?`<small>${detail}</small>`:''}
      ${changes.length ? `<dl class="eq-changes">${changes.map(([label, value]) =>
        `<div><dt>${label}</dt><dd>${value}</dd></div>`).join('')}</dl>` : ''}</div>`;
  }

  function epsChange(now, base) {
    if (!known(now) || !known(base) || base === 0) return '—';
    if (base > 0) return signedChange(growth(now,base),'%');
    if (now > 0) return '轉盈';
    if (now === 0) return '損益兩平';
    if (now === base) return '0.0%';
    const change = 100*Math.abs(now-base)/Math.abs(base);
    return (now > base ? '虧損縮小 ' : '虧損擴大 ') + fmt(change,1) + '%';
  }

  function monthReading(index) {
    const byMonth = monthlyData?.companies?.[companyCode];
    const row = byMonth?.[revenueMonths[index]];
    const priorMonth = row?.previousMonth ?? byMonth?.[revenueMonths[index-1]]?.revenue;
    return {row, mom:growth(row?.revenue,priorMonth), yoy:growth(row?.revenue,row?.previousYear)};
  }

  for (const code of order) companySelect.add(new Option(names[code]+' '+code, code));
  for (let i=revenueMonths.length-1; i>=0; i--) {
    monthSelect.add(new Option(date(revenueMonths[i]), String(i)));
  }
  monthSelect.disabled = !revenueMonths.length;
  for (const {label,metrics} of healthGroups) {
    const group = document.createElement('optgroup');
    group.label = label;
    for (const [key,metric] of Object.entries(metrics)) group.append(new Option(metric.label,key));
    healthSelect.append(group);
  }
  const quarterStart = data.financialWindow?.[0];
  const quarterEnd = data.financialWindow?.[1];
  const priceStart = Object.values(companies).map(firm=>firm.quotes[0]?.date).filter(Boolean).sort()[0];
  const priceEnd = Object.values(companies).map(firm=>firm.quotes.at(-1)?.date).filter(Boolean).sort().at(-1);
  $('eq-data-window').textContent = [
    quarterStart ? '財報 '+quarterName(quarterStart)+'–'+quarterName(quarterEnd) : '',
    priceStart ? '行情 '+date(priceStart)+'–'+date(priceEnd) : '',
  ].filter(Boolean).join(' · ');

  const valuationDays = [...new Set(order.map(code => companies[code].valuation?.date).filter(Boolean))].sort();
  const valuationRange = valuationDays.length > 1 ? [valuationDays[0], valuationDays.at(-1)] : valuationDays;
  $('eq-comparison-price-date').textContent = '估值採用股價日 ' + (valuationRange.map(date).join('–') || '—');

  function renderComparison() {
    const rows = order.map(code => {
      const firm = companies[code];
      const q = recentQuarter(firm.quarters);
      const v = firm.valuation || {};
      return {code:Number(code), period:q?.period, grossMargin:profitMargin(q,'grossProfit'),
        margin:margin(q), netMargin:profitMargin(q,'consolidatedNetIncome'), eps:q?.eps,
        ttm:ttm(firm.quarters), pe:v.pe, pb:v.pb, yield:v.yield};
    });
    const value = row => selectedSort === 'period' && row.period ? quarterIndex(row.period) : row[selectedSort];
    rows.sort((a, b) => {
      const av = value(a), bv = value(b);
      if (known(av) && known(bv) && av !== bv) return sortOrder * (av-bv);
      return Number(known(bv))-Number(known(av)) || a.code-b.code;
    });
    root.querySelectorAll('[data-eq-sort]').forEach(button => {
      const column = button.closest('th');
      if (button.dataset.eqSort === selectedSort) column.setAttribute('aria-sort',sortOrder<0?'descending':'ascending');
      else column.removeAttribute('aria-sort');
    });
    $('eq-compare-rows').innerHTML = rows.map(r => `<tr${r.code===Number(companyCode)?' class="eq-selected"':''}>
      <th scope="row"><button class="eq-company-link" type="button" data-eq-company="${r.code}">${names[r.code]}<small>${r.code}</small></button></th>
      <td>${quarterName(r.period)}</td><td>${textNum(r.grossMargin,2,'%')}</td><td>${textNum(r.margin,1,'%')}</td>
      <td>${textNum(r.netMargin,2,'%')}</td><td>${textNum(r.eps,2,' 元')}</td><td>${textNum(r.ttm,2,' 元')}</td>
      <td>${textNum(r.pe,2,' 倍')}</td><td>${textNum(r.pb,2,' 倍')}</td>
      <td>${textNum(r.yield,2,'%')}</td></tr>`).join('');
  }

  function renderEarningsTable() {
    $('eq-earnings-table').innerHTML = `<table class="eq-table"><thead><tr><th scope="col">財報期別</th>
      <th scope="col">單季營收</th><th scope="col">營業利益</th><th scope="col">營益率</th>
      <th scope="col">歸母淨利</th><th scope="col">EPS</th></tr></thead><tbody>
      ${[...company().quarters].reverse().map(q => `<tr><th scope="row">${quarterName(q.period)}</th>
      <td>${money(q.revenue)}</td><td>${money(q.operatingIncome)}</td><td>${textNum(margin(q),1,'%')}</td>
      <td>${money(q.netIncome)}</td><td>${textNum(q.eps,2,' 元')}</td></tr>`).join('')}</tbody></table>`;
  }

  function updateEarningsMetrics() {
    const rows = company().quarters;
    const q = rows[quarter];
    const asOf = quarterName(q?.period);
    const prior = referenceQuarter(rows,q,1), lastYear = referenceQuarter(rows,q,4);
    const {row, mom, yoy} = monthReading(selectedMonth);
    $('eq-earnings-metrics').innerHTML =
      card('月營收',remapMoney(row?.revenue),2,'億元',date(revenueMonths[selectedMonth]),[
        ['月增',signedChange(mom,'%')], ['年增',signedChange(yoy,'%')],
      ]) +
      Object.entries(marginFields).map(([field, label]) => {
        const value = profitMargin(q,field);
        return card(label,value,2,'%',asOf,[
          ['季增',signedChange(difference(value,profitMargin(prior,field)),' 百分點')],
          ['年增',signedChange(difference(value,profitMargin(lastYear,field)),' 百分點')],
        ]);
      }).join('') +
      card('單季 EPS',q?.eps,2,'元',asOf,[
        ['季增',epsChange(q?.eps,prior?.eps)], ['年增',epsChange(q?.eps,lastYear?.eps)],
      ]) +
      card('累計 EPS',q?.epsYTD,2,'元',asOf,[
        ['年增',epsChange(q?.epsYTD,lastYear?.epsYTD)],
      ]);
    const metric = marginSelect.value;
    $('eq-margin-readout').textContent = asOf + ' · ' + marginFields[metric] + ' ' +
      textNum(profitMargin(q,metric),2,'%');
    setLink('eq-monthly-source', row?.source);
  }

  function pickMonth(index) {
    selectedMonth = index;
    monthSelect.value = String(index);
    updateEarningsMetrics();
    showRevenueCursor(index);
  }

  function updateHealthReadout() {
    const rows = company().quarters;
    const q = rows[quarter];
    const health = q?.health || {};
    const priorYear = referenceQuarter(rows,q,4);
    const metricNote = key => {
      if (key === 'inventoryTurnover' && health.inventoryUnlisted) return '財報未單獨列報存貨';
      if (key === 'cashToNetIncome' && health.nonpositiveNetIncome) return '近四季稅後淨利不為正';
      return '';
    };
    $('eq-health-metrics').innerHTML = healthGroups.map(({label,metrics}) =>
      `<section class="eq-health-group"><h4>${label}</h4><div class="eq-health-pair">${Object.entries(metrics).map(([key,metric]) => {
        const value = healthValue(q,key);
        const change = difference(value,healthValue(priorYear,key));
        const percent = metric.unit === '%';
        return card(metric.label,value,percent?1:2,metric.unit,metricNote(key),[
          ['較去年同期',signedChange(change,percent?' 百分點':' '+metric.unit,percent?1:2)],
        ]);
      }).join('')}</div></section>`).join('');

    const key = healthSelect.value;
    const metric = healthMetrics[key];
    const value = healthValue(q,key);
    const note = metricNote(key);
    $('eq-health-readout').textContent = quarterName(q?.period) + ' · ' + metric.label + ' ' +
      textNum(value,metric.unit === '%' ? 1 : 2,metric.unit === '%' ? '%' : ' '+metric.unit) +
      (note ? ' · '+note : '');

    setLink('eq-health-balance-source',health.balanceSource);
    setLink('eq-health-cash-source',q?.cashSource);
    const capexNote = health.capexNeedsReview ? '近四季含待核對的資本支出' : '';
    $('eq-health-cash-metrics').innerHTML =
      card('近四季營業現金流',remapMoney(health.operatingCashFlow),2,'億元') +
      card('近四季資本支出',remapMoney(health.capitalExpenditure),2,'億元',capexNote) +
      card('資本支出覆蓋倍數',health.capexCoverage,2,'倍');
  }

  function updateFinancialReadout() {
    const q = company().quarters[quarter] || {};
    quarterSelect.value = String(quarter);
    $('eq-published').textContent = q.published ? '公告日 '+date(q.published) : '公告日未核驗';
    setLink('eq-filing', q.source);
    setLink('eq-publication-source', q.publicationSource);
    updateEarningsMetrics();
    updateHealthReadout();
  }

  function renderStockReadout() {
    const q = displayedQuotes[selectedDay];
    dateSlider.value = String(selectedDay);
    dateSlider.disabled = !q;
    dateSlider.setAttribute('aria-valuetext',q ? date(q.date) : '資料暫缺');
    const detail = stockView in valuationLabels
      ? valuationLabels[stockView]+' '+textNum(company().valuations?.[q?.date]?.[stockView],2,' 倍')
      : q && (q.volumeApproximate?'約 ':'')+fmt(q.volume/1000,2)+' 張';
    $('eq-stock-readout').textContent = q ? `${date(q.date)} · ${fmt(q.close)} 元 · ${detail}` : '行情暫缺';
  }

  const lastRecordedDay = records => Object.keys(records || {}).sort().at(-1);
  const signedLots = shares => known(shares)
    ? (shares > 0 ? '+' : '') + fmt(shares/1000,2) : '—';

  function updateChipTable() {
    const {institutions, margin, sources} = company();
    const last = lastRecordedDay(institutions);
    const index = chipDays.indexOf(last);
    selectedChip = index >= 0 ? index : Math.max(0,chipDays.length-1);
    chipSlider.max = String(Math.max(0,chipDays.length-1));
    chipSlider.disabled = !chipDays.length;
    const cumulative = (key,n) => {
      if (index<n-1) return null;
      const rows = chipDays.slice(index+1-n,index+1).map(day=>institutions?.[day]?.[key]);
      return rows.every(known) ? rows.reduce((a,b)=>a+b,0) : null;
    };
    const all = [...institutionalSeries,{key:'total',label:'三大法人合計'}];
    $('eq-chip-summary').innerHTML = `<table class="eq-table eq-chip-table">
      <caption>法人資料 ${date(last)} · 信用交易 ${date(lastRecordedDay(margin))}</caption>
      <thead><tr><th scope="col">買賣超（張）</th><th scope="col">最新一日</th>
      <th scope="col">近 5 日累計</th><th scope="col">近 20 日累計</th></tr></thead>
      <tbody>${all.map(({key,label})=>`<tr><th scope="row">${label}</th>
        <td>${signedLots(institutions?.[last]?.[key])}</td><td>${signedLots(cumulative(key,5))}</td>
        <td>${signedLots(cumulative(key,20))}</td></tr>`).join('')}</tbody>
    </table>`;
    $('eq-chip-legend').innerHTML = institutionalSeries.map(({label,color})=>
      `<span><i class="eq-swatch" style="background:${color}"></i>${label}</span>`).join('');
    setLink('eq-chip-link',sources?.institutions);
    setLink('eq-credit-link',sources?.margin);
    renderChipReadout();
  }

  function renderChipReadout() {
    const day = chipDays[selectedChip];
    const {institutions,margin} = company();
    chipSlider.value = String(selectedChip);
    chipSlider.setAttribute('aria-valuetext',date(day));
    const item = institutions?.[day], credit = margin?.[day];
    const breakdown = institutionalSeries.map(({key,label})=>label+' '+signedLots(item?.[key]));
    $('eq-chip-readout').textContent = day
      ? [date(day),...breakdown,'合計 '+signedLots(item?.total),
        '融資 '+textNum(credit?.long,0),'融券 '+textNum(credit?.short,0)].join(' · ')+'（張）'
      : '籌碼暫缺';
  }

  function pickChip(index) {
    selectedChip = index;
    renderChipReadout();
    callbacks.forEach(render=>render(index));
  }

  function pickPoint(index) {
    if (activeTab === 'stock') {
      selectedDay = Math.min(displayedQuotes.length-1,Math.max(0,index));
      renderStockReadout();
    } else {
      quarter = Math.min(company().quarters.length-1,Math.max(0,index));
      updateFinancialReadout();
    }
    const selected = activeTab==='stock' ? selectedDay : quarter;
    callbacks.forEach(render => render(selected));
  }

  function bounds(values, zero) {
    const min = Math.min(...values);
    const max = Math.max(...values);
    const low = zero ? Math.min(0,min) : min;
    const high = zero ? Math.max(0,max) : max;
    const target = (high-low)/4 || Math.abs(high)*.05 || 1;
    const magnitude = 10**Math.floor(Math.log10(target));
    const step = [1,2,5,10].find(n=>n*magnitude>=target)*magnitude;
    const bottom = Math.floor(low/step)*step;
    const top = Math.max(bottom+step,Math.ceil(high/step)*step);
    return {bottom,top,step};
  }

  function plot(id, labels, series, options = {}) {
    const mount = $(id);
    const values = series.filter(s=>!s.rightAxis).flatMap(s=>s.values.filter(known));
    const rightValues = series.filter(s=>s.rightAxis).flatMap(s=>s.values.filter(known));
    if (!values.length || !labels.length) {
      mount.innerHTML = '<div class="eq-empty">這個期間的資料暫缺</div>';
      return () => {};
    }
    const w = Math.max(220,mount.clientWidth), h = options.height || 158;
    const guide = bounds(values,options.zero !== false);
    const tickText = value => Number(value.toFixed(2))+(options.tickSuffix||'');
    const leftInset = Math.max(48, 10+7*Math.max(tickText(guide.top).length,tickText(guide.bottom).length));
    const u = {x:leftInset, right:w-(rightValues.length ? 48 : 14), top:9, bottom:h-27};
    const rightGuide = rightValues.length ? bounds(rightValues,true) : null;
    const y = (value, scale = guide) => u.top + (scale.top-value)/(scale.top-scale.bottom)*(u.bottom-u.top);
    const dx = (u.right-u.x)/labels.length;
    const x = i => u.x + dx*(i+.5);
    const ticks = [];
    for (let i=guide.bottom;i<=guide.top+guide.step*.01;i+=guide.step) {
      const yy=y(i);
      ticks.push(`<path class="eq-gridline${Math.abs(i)<guide.step*.01?' eq-zero':''}" d="M${u.x} ${yy}H${u.right}"/>
        <text class="eq-axis" x="${u.x-6}" y="${yy+4}" text-anchor="end">${tickText(i)}</text>`);
    }
    if (rightGuide) {
      for (let i=rightGuide.bottom;i<=rightGuide.top+rightGuide.step*.01;i+=rightGuide.step) {
        ticks.push(`<text class="eq-axis" x="${u.right+6}" y="${y(i,rightGuide)+4}">${Number(i.toFixed(2))}${options.rightSuffix ?? '%'}</text>`);
      }
    }
    const count = Math.min(labels.length,w<380?3:w<590?4:6);
    const indices = Array.from({length:count},(_,i)=>count===1?0:Math.round(i*(labels.length-1)/(count-1)));
    const tickLabels = indices.map(i => `<text class="eq-axis" x="${x(i)}" y="${h-7}"
      text-anchor="${i===0?'start':i===labels.length-1?'end':'middle'}">${labels[i]}</text>`).join('');

    const shaded = (options.bands || []).map(({lower,upper,color}) => {
      let top = [], bottom = [], paths = '';
      const close = () => {
        if (top.length>1) {
          paths += `<path class="eq-river-band" d="M${top.join('L')}L${bottom.reverse().join('L')}Z" fill="${color}"/>`;
        }
        top = [];
        bottom = [];
      };
      upper.forEach((value,i)=>{
        if (!known(value) || !known(lower[i])) { close(); return; }
        top.push(x(i)+' '+y(value));
        bottom.push(x(i)+' '+y(lower[i]));
      });
      close();
      return paths;
    }).join('');
    const bars = series.filter(s=>s.type==='bar');
    const barWidth = Math.max(1,Math.min(20,.66*dx/Math.max(1,bars.length)));
    const marks = series.map(s => {
      const pointY = value => y(value,s.rightAxis ? rightGuide : guide);
      if (s.type==='bar') return s.values.map((v,i) => {
        if (!known(v)) return '';
        if (!v) return '';
        const start = x(i)+barWidth*(bars.indexOf(s)-bars.length/2);
        return `<rect x="${start}" y="${Math.min(y(v),y(0))}" width="${barWidth}" height="${Math.max(.65,Math.abs(y(v)-y(0)))}" fill="${s.color}" opacity="${s.opacity||.85}"/>`;
      }).join('');
      let started = false;
      const curves = s.values.map((v,i)=>{
        if (!known(v)) { started=false;return ''; }
        const p = (started?'L':'M')+x(i)+' '+pointY(v);
        started=true;
        return p;
      }).join(' ');
      const dots = labels.length<40 ? s.values.map((v,i)=>known(v)
        ? `<circle cx="${x(i)}" cy="${pointY(v)}" r="2.6" fill="${s.color}"/>` : '').join('') : '';
      return `<path d="${curves}" fill="none" stroke="${s.color}" stroke-width="${s.width || 2.1}" stroke-linejoin="round"${s.dash?' stroke-dasharray="5 4"':''}/>${dots}`;
    }).join('');

    mount.innerHTML = `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${options.label}">
      ${ticks.join('')}${tickLabels}<rect class="eq-highlight" y="${u.top}" width="${dx}" height="${u.bottom-u.top}"/>
      ${shaded}${marks}<path class="eq-cursor"/>
    </svg>`;
    const svg = mount.querySelector('svg');
    const band = svg.querySelector('.eq-highlight');
    const cursor = svg.querySelector('.eq-cursor');
    let selected = -1;
    function selectAt(event) {
      const r = svg.getBoundingClientRect();
      const position = (event.clientX-r.left)*w/r.width;
      const next = Math.min(labels.length-1,Math.max(0,Math.floor((position-u.x)/dx)));
      if (selected!==next) (options.onSelect || pickPoint)(next);
    }
    svg.addEventListener('click',selectAt);
    if (activeTab==='stock') svg.addEventListener('pointermove',event=>{
      if(event.pointerType==='mouse') selectAt(event);
    });
    return i => {
      selected = i;
      band.setAttribute('x',x(i)-dx/2);
      cursor.setAttribute('d','M'+x(i)+' '+u.top+'V'+u.bottom);
    };
  }

  function quoteWindowStart(end,months) {
    if (!end) return null;
    const cutoff = new Date(end+'T00:00:00Z');
    const day = cutoff.getUTCDate();
    cutoff.setUTCDate(1);
    cutoff.setUTCMonth(cutoff.getUTCMonth()-months);
    const limit = new Date(Date.UTC(cutoff.getUTCFullYear(),cutoff.getUTCMonth()+1,0)).getUTCDate();
    cutoff.setUTCDate(Math.min(day,limit));
    return cutoff.toISOString().slice(0,10);
  }

  function updateStockPanel() {
    const q = company().quotes.at(-1);
    const v = company().valuation || {};
    const beginning = quoteWindowStart(q?.date,monthsBack);
    displayedQuotes = company().quotes.filter(row=>beginning && row.date>=beginning);
    selectedDay = Math.max(0,displayedQuotes.length-1);
    dateSlider.max = String(selectedDay);
    $('eq-valuation-date').textContent = '行情 '+date(q?.date)+' · 估值 '+date(v.date);
    $('eq-stock-metrics').innerHTML = card('最近收盤價',q?.close,2,'元')+
      card('本益比',v.pe,2,'倍')+card('股價淨值比',v.pb,2,'倍')+card('殖利率',v.yield,2,'%');
    const approximate = displayedQuotes.some(row=>row.volumeApproximate);
    $('eq-stock-basis').textContent = '股價採官方未還原權息收盤價。'+
      (approximate?'此區間部分成交量由櫃買中心歷史仟股欄轉換，約數已標示。':'');
    setLink('eq-quote-link', company().quoteSource);
    setLink('eq-valuation-link', v.source);
    renderStockReadout();
  }

  function drawRiver(labels) {
    const metric = stockView;
    const valuations = company().valuations || {};
    const start = quoteWindowStart(company().quotes.at(-1)?.date,12);
    const values = company().quotes.filter(row=>start && row.date>=start).map(row=>valuations[row.date]?.[metric])
      .filter(v=>known(v) && v > 0).sort((a,b)=>a-b);
    const stops = values.length ? riverSteps.map(p=>{
      const rank = (values.length-1)*p/100;
      const low = Math.floor(rank);
      return values[low] + (values[Math.ceil(rank)]-values[low])*(rank-low);
    }) : [];
    const close = displayedQuotes.map(q=>q.close);
    const basis = displayedQuotes.map(q=>{
      const multiple = valuations[q.date]?.[metric];
      return multiple>0 ? q.close/multiple : null;
    });
    const bandLines = stops.map((mark,i)=>({
      values:basis.map(value=>known(value) ? value*mark : null),
      color:i===2 ? '#537b91' : '#8baab8', width:i===2?1.6:1,
    }));
    const fills = ['#edf5f9','#d9eaf3','#cbe0ec','#e1eff7'];
    const bands = bandLines.slice(1).map(({values},i)=>({lower:bandLines[i].values,upper:values,color:fills[i]}));
    const title = valuationLabels[metric]+'河流圖';
    $('eq-river-title').textContent = title;
    $('eq-river-legend').innerHTML = '<span><i class="eq-swatch eq-price-swatch"></i>收盤價</span>' +
      stops.map((value,i)=>'<span>第 '+riverSteps[i]+' 百分位 · '+fmt(value,2)+' 倍</span>').join('') +
      (stops.length ? '' : '<span>歷史倍數暫缺</span>');
    return plot('eq-river-plot',labels,[...bandLines,{values:close,color:'#173a52',width:2.7}],
      {zero:false,height:275,label:title,bands});
  }

  function drawChips() {
    const labels = chipDays.map(day=>date(day).slice(2));
    const {institutions,margin} = company();
    const series = institutionalSeries.map(({key,color})=>({
      values:chipDays.map(day=>known(institutions?.[day]?.[key])?institutions[day][key]/1000:null),color,type:'bar',
    }));
    callbacks = [
      plot('eq-chip-plot',labels,series,{height:200,label:'三大法人每日買賣超',onSelect:pickChip}),
      plot('eq-credit-plot',labels,[
        {values:chipDays.map(day=>margin?.[day]?.long),color:'var(--eq-long)'},
        {values:chipDays.map(day=>margin?.[day]?.short),color:'var(--eq-short)',rightAxis:true},
      ],{height:172,zero:false,rightSuffix:'',label:'融資融券餘額',onSelect:pickChip}),
    ];
    callbacks.forEach(render=>render(selectedChip));
  }

  function setStockView(view) {
    stockView = view;
    const chips = view==='chips';
    const river = view in valuationLabels;
    $('eq-stock-views').querySelectorAll('button').forEach(button=>
      button.setAttribute('aria-pressed',String(button.dataset.eqStockView===view)));
    $('eq-stock-price-view').hidden = view!=='price';
    $('eq-stock-river-view').hidden = !river;
    $('eq-stock-chips-view').hidden = !chips;
    for (const id of ['eq-quote-inspect','eq-stock-basis','eq-stock-links','eq-intervals','eq-valuation-date','eq-stock-metrics']) {
      $(id).hidden = chips;
    }
    renderStockReadout();
    draw();
  }

  function draw() {
    lastWidth = $('eq-detail').clientWidth;
    if (!lastWidth) return;
    if (activeTab==='stock') {
      if (stockView==='chips') {
        drawChips();
        return;
      }
      const labels = displayedQuotes.map(q=>date(q.date).slice(2));
      callbacks = stockView in valuationLabels ? [drawRiver(labels)] : [
        plot('eq-price-plot',labels,[{values:displayedQuotes.map(q=>q.close),color}],
          {zero:false,height:200,label:'每日收盤價折線圖'}),
        plot('eq-volume-plot',labels,[{values:displayedQuotes.map(q=>q.volume/1000),color,type:'bar'}],
          {height:112,label:'每日成交量長條圖'}),
      ];
      callbacks.forEach(f=>f(selectedDay));
      return;
    }
    const rows=company().quarters, labels=rows.map(q=>shortQuarter(q.period));
    if (activeTab==='earnings') {
      const months = revenueMonths.map((_,index)=>monthReading(index));
      showRevenueCursor = plot('eq-revenue-plot',revenueMonths.map(p=>date(p).slice(2)),[
        {values:months.map(m=>remapMoney(m.row?.revenue)),color:'var(--eq-revenue)',type:'bar'},
        {values:months.map(m=>m.mom),color:'var(--eq-mom)',rightAxis:true,dash:true},
        {values:months.map(m=>m.yoy),color:'var(--eq-yoy)',rightAxis:true},
      ],{height:205,label:'單月營收、月增率與年增率',onSelect:pickMonth});
      showRevenueCursor(selectedMonth);
      const metric = marginSelect.value;
      callbacks = [plot('eq-margin-plot',labels,[{values:rows.map(q=>profitMargin(q,metric)),color}],
        {height:205,tickSuffix:'%',label:'各季'+marginFields[metric]})];
    } else {
      const key = healthSelect.value;
      const metric = healthMetrics[key];
      callbacks = [plot('eq-health-plot',labels,[{values:rows.map(q=>healthValue(q,key)),color}],
        {height:215,zero:false,label:metric.label+'歷季走勢',tickSuffix:metric.unit})];
    }
    callbacks.forEach(f=>f(quarter));
  }

  function setCompany(code, jump=false) {
    if (!companies[code]) return;
    companyCode=code;
    companySelect.value=code;
    $('eq-company-title').textContent=names[code];
    $('eq-company-code').textContent=code+' · '+(company().market==='TPEx'?'上櫃':'上市');
    const rows=company().quarters;
    quarter=Math.max(0,rows.findLastIndex(q=>[q.revenue,q.operatingIncome,q.eps].some(known)));
    quarterSelect.replaceChildren();
    for (let i=rows.length-1;i>=0;i--) quarterSelect.add(new Option(quarterName(rows[i].period),String(i)));
    quarterSelect.disabled=!rows.length;
    selectedMonth = Math.max(0,revenueMonths.findLastIndex(month => monthlyData?.companies?.[code]?.[month]));
    monthSelect.value = String(selectedMonth);
    renderComparison();
    renderEarningsTable();
    updateFinancialReadout();
    updateStockPanel();
    updateChipTable();
    draw();
    if (jump) $('eq-detail').scrollIntoView({block:'start',behavior:'smooth'});
  }

  function setTab(tab) {
    activeTab=tab;
    for(const key of financeTabs) {
      const current=key===tab;
      $('eq-tab-'+key).setAttribute('aria-selected',String(current));
      $('eq-tab-'+key).tabIndex=current?0:-1;
      $('eq-panel-'+key).hidden=!current;
    }
    $('eq-financial-period').hidden=tab==='stock';
    draw();
  }

  $('eq-compare-table').addEventListener('click', event => {
    const sort = event.target.closest('[data-eq-sort]');
    const use = event.target.closest('[data-eq-company]');
    if (sort) {
      if (selectedSort===sort.dataset.eqSort) sortOrder *= -1;
      else { selectedSort=sort.dataset.eqSort;sortOrder=selectedSort==='code'?1:-1; }
      renderComparison();
    } else if (use) setCompany(use.dataset.eqCompany,true);
  });
  companySelect.addEventListener('change',()=>setCompany(companySelect.value));
  quarterSelect.addEventListener('change',()=>pickPoint(Number(quarterSelect.value)));
  monthSelect.addEventListener('change',()=>pickMonth(Number(monthSelect.value)));
  marginSelect.addEventListener('change',()=>{
    updateEarningsMetrics();
    draw();
  });
  healthSelect.addEventListener('change',()=>{
    updateHealthReadout();
    draw();
  });
  dateSlider.addEventListener('input',()=>pickPoint(Number(dateSlider.value)));
  chipSlider.addEventListener('input',()=>pickChip(Number(chipSlider.value)));
  $('eq-stock-views').addEventListener('click',event=>{
    const button = event.target.closest('[data-eq-stock-view]');
    if (button) setStockView(button.dataset.eqStockView);
  });
  root.querySelector('.eq-tabs').addEventListener('click',event=>{
    const tab=event.target.closest('[data-eq-tab]');
    if(tab) setTab(tab.dataset.eqTab);
  });
  root.querySelector('.eq-tabs').addEventListener('keydown',event=>{
    if (!['ArrowRight','ArrowLeft','Home','End'].includes(event.key)) return;
    event.preventDefault();
    const current=financeTabs.indexOf(activeTab);
    const next=event.key==='Home'?0:event.key==='End'?2:
      (current+(event.key==='ArrowRight'?1:2))%financeTabs.length;
    setTab(financeTabs[next]); $('eq-tab-'+financeTabs[next]).focus();
  });
  $('eq-intervals').addEventListener('click',event=>{
    const button=event.target.closest('[data-eq-range]');
    if (!button) return;
    monthsBack=Number(button.dataset.eqRange);
    $('eq-intervals').querySelectorAll('button').forEach(control=>control.setAttribute('aria-pressed',String(control===button)));
    updateStockPanel();
    draw();
  });
  root.querySelector('.eq-jump').addEventListener('click',event=>{
    event.preventDefault();
    $('eq-sources').open=true;
    $('eq-sources').scrollIntoView({behavior:'smooth',block:'start'});
  });

  setCompany(companyCode);
  new ResizeObserver(()=>{
    const width=$('eq-detail').clientWidth;
    if(width && width!==lastWidth) draw();
  }).observe($('eq-detail'));
})();
