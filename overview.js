(() => {
  'use strict';
  const D = window.FLOW_DATA;
  const grain = window.FLOW_GRAIN_DEMAND;
  const outlook = window.FLOW_SUPPLY_OUTLOOK.bimcoLatest;
  const put = (id, html) => { document.getElementById(id).innerHTML = html; };
  const date = period => period.replaceAll('-', '/');
  const format = (value, digits = 1) => value.toLocaleString('zh-TW', {
    minimumFractionDigits: digits, maximumFractionDigits: digits,
  });
  const percent = value => value == null ? '—' : `${value > 0 ? '+' : value < 0 ? '−' : ''}${format(Math.abs(value))}%`;
  const change = (value, prior) => value == null || prior == null || prior === 0 ? null : (value / prior - 1) * 100;
  const tonnage = (value, digits = 1) => value == null ? '—' : format(value / 10000, digits);
  const rate = (label, value) => `<span>${label} <b>${percent(value)}</b></span>`;
  const row = (name, period, value, rates, digits = 1) => `<div class="market-row">
    <div class="market-row-top"><h5>${name}</h5><span>${date(period)}</span></div>
    <div class="market-row-bottom"><strong>${tonnage(value, digits)}<small>萬公噸</small></strong><div class="market-rates">${rates.join('')}</div></div>
  </div>`;
  const ironRow = (name, point) => row(name, point.period, point.tonnes, [
    rate('MoM', change(point.tonnes, point.previousMonth)),
    rate('YoY', change(point.tonnes, point.previousYear)),
  ], 2);

  const iron = D.ironFlowSnapshot;
  const steel = D.steelProduction;
  put('market-iron-supply', ironRow('澳洲 Port Hedland 鐵礦砂出口', iron.portHedland)
    + ironRow('巴西鐵礦砂海運出口', iron.brazil));
  put('market-iron-demand', ironRow('中國鐵礦砂及精礦進口', iron.china)
    + row('中國生鐵產量', steel.period, steel.pigIron.value * 10000, [
      rate('MoM', change(steel.pigIron.value, steel.pigIron.previousMonth)),
      rate('YoY', steel.pigIron.yoyPct),
    ], 0));

  const keys = [['soy', '黃豆'], ['corn', '玉米'], ['wheat', '小麥']];
  const group = (label, period, description, items) => `<div class="market-row">
    <div class="market-row-top"><h5>${label}</h5><span>${period}</span></div>
    <p class="market-units">${description}</p><ul class="market-compact-list">${items.join('')}</ul>
  </div>`;
  const token = (name, amount, comparison) => `<li><span>${name}</span> <strong>${amount}</strong>${comparison ? ` <small>${comparison}</small>` : ''}</li>`;
  put('market-grain-supply', group('美國船運出口檢驗', `${date(D.usPeriod)} 當週`, '萬公噸 · 較 52 週前', keys.map(([key, name]) =>
    token(name, tonnage(D.us[key], 2), percent(change(D.us[key], D.usPrevious[key])))))
    + group('巴西海運出口', date(D.brazilPeriod), '萬公噸 · 較去年同月', keys.slice(0, 2).map(([key, name]) => {
      const values = D.brazil[key];
      const last = values.at(-1);
      return token(name, tonnage(last, 2), percent(change(last, D.brazilPrevious[key][values.length - 1])));
    })));

  const recent = grain.actual.rows.at(-1);
  const previousYear = `${Number(recent.period.slice(0, 4)) - 1}${recent.period.slice(4)}`;
  const comparable = grain.actual.rows.find(point => point.period === previousYear && point.sourceGroup === recent.sourceGroup);
  const forecast = grain.forecast;
  put('market-grain-demand', row('中國黃豆進口', recent.period, recent.tonnes, [rate('YoY', change(recent.tonnes, comparable?.tonnes))])
    + group('全球進口預測', `${forecast.season} 年度`, `USDA ${date(forecast.reportDate)} 版 · 較上期同年度預測`, forecast.commodities.map(c =>
      token(c.name, percent(change(c.imports, c.previousVintageImports))))));

  const range = bounds => `${bounds.join('–')}%`;
  const closed = outlook.scenarios.closed.years;
  const [year, scenario] = Object.entries(closed)[0];
  const years = Object.keys(closed);
  put('market-bimco', `<div class="market-row-top"><h4>BIMCO 散裝展望</h4><span>${date(outlook.published)} 版</span></div>
    <p>${years[0]}–${years.at(-1)} 年貨量成長有限、新船交付加快，BIMCO 預期散裝供需平衡將自高位逐步轉弱。</p>
    <p>若荷姆茲海峽持續受阻，${year} 年船舶需求估增 ${range(scenario.demand)}，有效供給估增 ${range(scenario.supply)}。</p>
    <a class="market-source" href="${outlook.publicReleaseUrl}" target="_blank" rel="noopener noreferrer">BIMCO 公開聲明轉載 ↗</a>`);
})();
