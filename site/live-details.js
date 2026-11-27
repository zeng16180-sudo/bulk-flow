(() => {
  'use strict';
  const D = window.FLOW_DATA;
  const G = window.FLOW_GRAIN_DEMAND;
  const S = window.FLOW_SUPPLY_OUTLOOK;
  const C = window.FLOW_COMPANIES;
  const latest = S.bimcoLatest;
  const recycling = S.bimcoRecycling;
  const audit = window.FLOW_UPDATE_STATUS;
  const $ = selector => document.querySelector(selector);
  const esc = value => String(value ?? '—').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const date = value => value ? value.replaceAll('-', '/') : '—';
  const fmt = (n, digits = 1) => n == null ? '—' : n.toLocaleString('zh-TW', {maximumFractionDigits: digits});
  const pct = (n, prev) => n == null || prev == null || prev === 0 ? null : (n / prev - 1) * 100;
  const signed = n => n == null ? '—' : (n > 0 ? '+' : '') + fmt(n) + '%';
  const a = (url, name) => {
    try {
      const target = new URL(url);
      if (target.protocol === 'https:') return `<a href="${esc(target.href)}" target="_blank" rel="noopener noreferrer">${esc(name)} ↗</a>`;
    } catch {}
    return esc(name);
  };
  const set = (selector, value) => { $(selector).textContent = value; };
  set('.snapshot strong', date(D.snapshot));
  set('#us-summary-period', `${date(D.usPeriod)} 當週 · ${date(D.usRetrieved)} 取得`);
  set('#us-bars-note', `USDA FGIS · SHIP 海運。WoW 比較 ${date(D.usPreviousWeekPeriod)}；YoY 比較 ${date(D.usComparisonPeriod)}（52 週前）。近 4 週平均包含本週。`);
  set('#iron-page-period', '各來源資料月份分列');
  const row = (name, value) => `<div class="stat-row"><span>${esc(name)}</span><strong>${value}</strong></div>`;
  const rate = (name, value) => `<p class="change-line">${name} <b>${signed(value)}</b></p>`;
  const publish = point => point.published ? ` · ${date(point.published)} 公布` : '';
  const vale = D.vale;
  $('#vale-metrics').innerHTML = `<div class="sectionline"><h3>Vale 鐵礦砂產銷</h3><span class="badge">季度</span></div>
    <p class="meta">${esc(vale.period)} · 百萬公噸${publish(vale)}</p>
    ${row('鐵礦砂產量', fmt(vale.production))}${rate('YoY', pct(vale.production, vale.productionPreviousYear))}
    ${row('鐵礦砂銷量', fmt(vale.sales))}${rate('YoY', pct(vale.sales, vale.salesPreviousYear))}
    ${a(vale.source, 'Vale 原始資料')}`;
  const steel = D.steelProduction;
  $('#steel-metrics').innerHTML = `<div class="sectionline"><h3>中國生鐵與粗鋼產量</h3><span class="badge">月度</span></div>
    <p class="meta">${date(steel.period)} · 萬公噸${publish(steel)}</p>
    ${[['生鐵',steel.pigIron],['粗鋼',steel.crudeSteel]].map(([name,x]) =>
      row(name,fmt(x.value,0)) + `<div class="change-line"><span>MoM <b>${signed(pct(x.value,x.previousMonth))}</b></span><span>YoY <b>${signed(x.yoyPct)}</b></span></div>`).join('')}
    <p class="note">YoY 採統計局公布值。${a(steel.source,'當月報告')} · ${a(steel.previousMonthSource,'前月報告')}</p>`;

  const years = Object.keys(latest.scenarios.closed.years);
  const yearText = years.join('–');
  const ranges = year => latest.scenarios.closed.years[year];
  set('#supply-period', `預測 ${yearText} · BIMCO ${date(latest.published)} 版`);
  const first = ranges(years[0]);
  $('#supply-takeaway').innerHTML = `<div><span class="eyebrow">BIMCO · ${date(latest.published)} 版</span>
    <h3>${yearText} 年散裝市場展望</h3>
    <p>${years[0]} 年 ${esc(latest.scenarios.closed.label)}情境，船舶需求 ${first.demand.join('–')}%，有效供給 ${first.supply.join('–')}%。</p></div>
    ${a(latest.officialUrl, '官方報告')}`;
  set('#supply-balance-edition', 'BIMCO · ' + date(latest.published));
  const quantity = (id, title, vintage, values, note, links) => {
    const entries = Object.entries(values).filter(([,v]) => v != null).sort(([a],[b]) => a.localeCompare(b));
    const cards = entries.map(([y,v],index) => index === 0
      ? `<span class="meta">${esc(y)} 全年 · 全球散裝船</span><strong class="supply-big">${fmt(v/10000)}<span>萬 DWT</span></strong>`
      : `<div class="supply-fact"><span>${esc(y)} 年預測</span><strong>${fmt(v/10000)} 萬 DWT</strong></div>`).join('');
    $(id).innerHTML = `<div class="sectionline"><h3>${title}</h3><span class="supply-label forecast">BIMCO · ${date(vintage)} 版</span></div>
      ${cards || '<p>公開來源暫無已核對的年度量。</p>'}<p class="note">${esc(note)}</p><div class="supply-links">${links}</div>`;
  };
  const recycleUrl = recycling.sourceLocation?.includes('page 10') ? recycling.url + '#page=10' : recycling.url;
  quantity('#supply-recycling-card', '未來拆船預期', recycling.reportVintage,
    Object.fromEntries(Object.entries(recycling.years).map(([y,v]) => [y,v.recyclingDWT])),
    (recycling.evidenceType === 'original_pdf_verified' ? '已核對原始 PDF。' : '數字取自已核對公開說明。') +
      (recycling.reportVintage < latest.published.slice(0,7) ? '目前保留較早的量化預測。' : ''),
    a(recycleUrl, '拆船數值來源') + a(recycling.officialUrl, '官方報告'));
  const delivery = latest.deliveryEvidence;
  quantity('#supply-delivery-card', '新增運力預期', delivery?.reportVintage || latest.published.slice(0,7),
    latest.deliveriesDWT || {}, delivery?.originalPDFVerified ? '已核對原始 PDF。' : '交付預測以已核驗的公開引述為準，尚未扣除拆船。',
    (delivery?.sources || []).map(source => a(source.url, source.publisher)).join(''));
  $('#supply-balance-links').innerHTML = a(latest.officialUrl,'BIMCO 官方報告')
    + a(latest.publicReleaseUrl,'供需預測公開來源')
    + ' <a href="fleet-supply-sources.json" download>下載報告版本與數值 JSON ↓</a>';

  set('#fleet-period', '各公司資料時間分列 · 最近核驗變動 ' + date(C.checked));
  for (const key of ['bulk','other']) {
    $('#fleet-' + key + ' tbody').innerHTML = C.companies.map(c => `<tr>
      <th scope="row"><strong>${esc(c.name)}</strong>${a(c.url,c.label)}</th>
      ${c[key].map(v => `<td${v==null?' class="na"':''}>${v==null?'—':v}</td>`).join('')}
      <td class="fleet-date">${esc(c.basis)}</td></tr>`).join('');
  }
  $('#fleet-notes').innerHTML = C.companies.map(c =>
    `<li><strong>${esc(c.name)}</strong>　${esc(c.note)} ${a(c.url,'來源')}</li>`).join('');

  const equityMarket = window.FLOW_EQUITY_MARKET;
  const marketChecks = equityMarket?.checks;
  const financials = window.FLOW_EQUITY_RESEARCH;
  const monthlyRevenue = window.FLOW_COMPANY_PERFORMANCE;
  const checkedLabels = [
    audit.checked ? '貨流等來源 ' + date(audit.checked) : '',
    marketChecks?.checkedAt ? '航商交易資料 ' + date(marketChecks.checkedAt.slice(0,16)).replace('T',' ') : '',
  ].filter(Boolean);
  set('#daily-check-date', checkedLabels.length ? '最近查核 · ' + checkedLabels.join(' · ') : '等待首次查核');
  const stockReports = [
    ['quotes','收盤價與成交量'],
    ['valuation','本益比、股價淨值比與殖利率'],
    ['institutions','三大法人買賣超'],
    ['margin','融資融券餘額'],
  ];
  const stockStatuses = {updated:'已核驗更新',unchanged:'已核驗 · 已同步',waiting:'留存有效資料 · 待重試'};
  const stockRows = Object.entries(equityMarket?.sources || {}).flatMap(([market,sources]) => {
    const companyRows = Object.entries(equityMarket.companies)
      .filter(([code]) => financials?.companies?.[code]?.market===market)
      .map(([,company])=>company);
    const venue = market==='TWSE' ? '證交所' : '櫃買中心';
    return stockReports.map(([key,label])=>{
      const dates = [...new Set(companyRows.map(m=>Object.keys(m[key]).sort().at(-1)).filter(Boolean))].sort();
      const last = dates.length>1 ? date(dates[0])+' ～ '+date(dates.at(-1)) : date(dates[0]);
      const check = marketChecks?.markets?.[market]?.[key];
      const note = [
        check?.officialDay ? '本次核驗 '+date(check.officialDay) : '',
        check?.pending ? check.pending+' 個交易日待補' : '',
      ].filter(Boolean).join(' · ');
      return [market+'-'+key,'航商'+label+' · '+venue,sources[key],'交易日',last,{
        label:check ? stockStatuses[check.result] : '已核對 · 初始資料',
        issue:check?.result==='waiting',message:note,
      }];
    });
  });
  const companySnapshots = [];
  const filingDates = financials?.financialWindow;
  if (filingDates?.length===2) companySnapshots.push([
    'company-financials','航商財報與財務比率 · 公開資訊觀測站','https://mopsfin.twse.com.tw/',
    '季度',filingDates.map(period=>period.replace('-Q',' Q')).join(' ～ '),{label:'本版資料已核對'},
  ]);
  if (monthlyRevenue?.through) companySnapshots.push([
    'company-revenue','航商月營收 · 公開資訊觀測站','https://mops.twse.com.tw/mops/#/web/t21sc03',
    '月度',date(monthlyRevenue.from)+' ～ '+date(monthlyRevenue.through),{label:'本版資料已核對'},
  ]);
  const reporting = [
    ...Object.entries(window.FLOW_FREIGHT_INDICES).map(([key,x]) => [key, key + ' · 東方財富公開轉載',x.sourceUrl,'交易日',x.rows.at(-1).date]),
    ['us','美國海運出口檢驗 · USDA FGIS',D.usSource,'週度',D.usPeriod],
    ['brazil','巴西海運出口 · MDIC / Comex Stat','https://comexstat.mdic.gov.br/','月度',D.brazilPeriod],
    ['china','中國大豆／鐵礦砂進口 · 海關統計',G.actual.rows.at(-1).source,'月度',`黃豆 ${G.actual.rows.at(-1).period} · 鐵礦砂 ${D.ironFlowSnapshot.china.period}`],
    ['steel','中國生鐵與粗鋼 · 國家統計局',steel.source,'月度',steel.period],
    ['hedland','Port Hedland 鐵礦砂出口 · Pilbara Ports',window.FLOW_HEDLAND_HISTORY.source,'月度',D.ironFlowSnapshot.portHedland.period],
    ['vale','Vale 鐵礦砂產銷',vale.source,'季度',vale.period],
    ['wasde','WASDE 消耗、庫存、進口預測',G.forecast.sourceGrain,'月度',G.forecast.reportDate],
    ['bimco','BIMCO 全球散裝船展望',latest.officialUrl,'季度',latest.published],
    ...stockRows,
    ...companySnapshots,
    ...C.companies.map(c => [c.name,c.name,c.url,'不定期',c.basis])
  ];
  const statusLabel = {updated:'已核驗更新',unchanged:'已檢查 · 未見新值',review:'待查證 · 保留舊值',error:'未成功取得 · 保留舊值'};
  $('#source-rows').innerHTML = reporting.map(([key, name, url, frequency, period, customStatus]) => {
    const item = audit.sources[key];
    const issue = customStatus?.issue ?? (item && ['error','review'].includes(item.result));
    const label = customStatus?.label ?? (item ? statusLabel[item.result] : '待檢查');
    const message = customStatus?.message ?? item?.message;
    return `<tr><td>${a(url,name)}</td><td>${frequency}</td><td>${esc(period)}</td><td>
      <span class="status ${issue?'partial':''}">${esc(label)}</span>
      ${message?`<small>${esc(message)}</small>`:''}</td></tr>`;
  }).join('');
})();
