(() => {
  'use strict';

  const root = document.getElementById('company-performance');
  const perf = window.FLOW_COMPANY_PERFORMANCE;
  const fleets = window.FLOW_COMPANIES?.companies;
  const freight = window.FLOW_FREIGHT_INDICES;
  if (!root || !perf || !fleets || !freight) return;

  const $ = id => root.querySelector('#' + id);
  const codes = {'裕民':'2606', '慧洋-KY':'2637', '中航':'2612', '新興':'2605',
    '台航':'2617', '四維航':'5608', '正德':'2641'};
  const benchmarks = [
    {code: 'BCI', label: '海岬型', columns: [1]},
    {code: 'BPI', label: 'Panamax／Kamsarmax', columns: [2]},
    {code: 'BSI', label: 'Supramax／Ultramax', columns: [3, 4]},
    {code: 'BHSI', label: 'Handysize', columns: [5]},
  ];
  const companies = new Map(fleets.map(fleet => [codes[fleet.name], fleet]));
  const months = perf.months;
  const fmt = (n, decimals = 1) => Number(n).toLocaleString('zh-TW', {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals,
  });
  const percent = value => value == null ? '—' : (value > .049 ? '+' : '') + fmt(Math.abs(value) < .05 ? 0 : value) + '%';
  const yoy = (current, prior) => current == null || !prior ? null : 100 * (current / prior - 1);
  const monthName = month => month.replace('-', '/');
  const referenceYear = month => String(Number(month.slice(0, 4)) - 1) + month.slice(4);
  const monthlyMarkets = new Map();
  for (const [code, series] of Object.entries(freight)) {
    const accumulators = new Map();
    for (const point of series.rows) {
      const month = point.date.slice(0, 7);
      const group = accumulators.get(month) || {sum: 0, count: 0};
      group.sum += point.value;
      group.count += 1;
      accumulators.set(month, group);
    }
    const average = new Map([...accumulators].map(([month, group]) =>
      [month, {value: group.sum / group.count, days: group.count}]));
    monthlyMarkets.set(code, average);
  }

  const picker = $('cp-company');
  const slider = $('cp-timeline');
  const choices = $('cp-markets');
  const chartRevenue = $('cp-revenue-chart');
  const chartFreight = $('cp-freight-chart');
  for (const [code, company] of companies) picker.add(new Option(company.name + ' ' + code, code));
  picker.value = '2606';
  slider.max = String(months.length - 1);
  $('cp-date-range').textContent = monthName(months[0]) + '–' + monthName(months.at(-1));

  let company = companies.get(picker.value);
  let market;
  let selected = months.length - 1;
  let pointers = [];
  let plotWidth = 0;
  const trackedRevenue = () => perf.companies[picker.value] || {};
  const marketPeriod = month => monthlyMarkets.get(market.code)?.get(month);
  const marketChange = month => yoy(marketPeriod(month)?.value, marketPeriod(referenceYear(month))?.value);

  function link(id, url) {
    const anchor = $(id);
    anchor.hidden = !url;
    if (url) anchor.href = url;
    else anchor.removeAttribute('href');
  }

  function updateReadout() {
    const month = months[selected];
    const revenue = trackedRevenue()[month];
    const point = marketPeriod(month);
    slider.value = String(selected);
    slider.setAttribute('aria-valuetext', monthName(month));
    $('cp-month').textContent = monthName(month);
    $('cp-revenue').textContent = revenue ? fmt(revenue.revenue / 100000, 2) + ' 億元' : '—';
    $('cp-revenue-yoy').textContent = 'YoY ' + percent(yoy(revenue?.revenue, revenue?.previousYear));
    $('cp-current-freight').textContent = point ? fmt(point.value) + ' 點' : '—';
    $('cp-freight-yoy').textContent = point ? 'YoY ' + percent(marketChange(month)) + ' · ' + point.days + ' 日' : '歷史資料暫缺';
    link('cp-revenue-source', revenue?.source);
    for (const position of pointers) position(selected);
  }

  function setMonth(index) {
    const next = Math.max(0, Math.min(months.length - 1, Math.round(index)));
    if (next === selected) return;
    selected = next;
    updateReadout();
  }

  function gridExtent(values) {
    const min = Math.min(0, ...values);
    const max = Math.max(0, ...values);
    const target = (max - min) / 4 || 1;
    const magnitude = 10 ** Math.floor(Math.log10(target));
    const step = [1, 2, 5, 10].find(v => v * magnitude >= target) * magnitude;
    return {step, bottom: Math.floor(min / step) * step,
      top: Math.max(Math.ceil(max / step) * step, min + step)};
  }

  function plot(container, values, color, label, emptyMessage) {
    const available = values.filter(Number.isFinite);
    if (!available.length) {
      const empty = document.createElement('div');
      empty.textContent = emptyMessage;
      empty.className = 'cp-empty';
      container.replaceChildren(empty);
      return () => {};
    }

    const w = Math.max(215, container.clientWidth);
    const h = 150;
    const left = 49, right = 20, top = 10, bottom = 27;
    const {step, bottom: lower, top: upper} = gridExtent(available);
    const x = i => left + i * (w - left - right) / (months.length - 1);
    const y = v => top + (upper - v) * (h - top - bottom) / (upper - lower);
    const grid = [];
    for (let t = lower; t <= upper + step * 0.01; t += step) {
      const p = y(t);
      const zero = Math.abs(t) < step * .01 ? ' zero' : '';
      const ticks = Number(t.toFixed(2));
      grid.push(`<line class="cp-gridline${zero}" x1="${left}" y1="${p}" x2="${w-right}" y2="${p}"/>
        <text class="cp-axis" x="${left-7}" y="${p+4}" text-anchor="end">${ticks}%</text>`);
    }

    const tickCount = w < 360 ? 3 : w < 600 ? 4 : 6;
    const labels = Array.from({length: tickCount}, (_, i) => Math.round(i * (months.length-1) / (tickCount-1)));
    const text = labels.map(i => `<text class="cp-axis" x="${x(i)}" y="${h-7}"
      text-anchor="${i===0?'start':i===months.length-1?'end':'middle'}">${monthName(months[i]).slice(2)}</text>`);

    let connects = false;
    const points = values.map((value, i) => {
      if (!Number.isFinite(value)) {
        connects = false;
        return '';
      }
      const segment = (connects ? 'L' : 'M') + x(i) + ' ' + y(value);
      connects = true;
      return segment;
    });
    const circles = values.map((value, i) => Number.isFinite(value)
      ? `<circle cx="${x(i)}" cy="${y(value)}" r="2.25" fill="${color}"/>` : '').join('');
    container.innerHTML = `<svg viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" role="img" aria-label="${label}">
      ${grid.join('')}${text.join('')}
      <path d="${points.join(' ')}" fill="none" stroke="${color}" stroke-width="2.5" stroke-linejoin="round"/>
      ${circles}<line class="cp-cursor" y1="${top}" y2="${h-bottom}"/>
      <circle class="cp-focus-dot" r="4.7" fill="${color}" stroke="white" stroke-width="2"/>
    </svg>`;
    const svg = container.querySelector('svg');
    const cursor = svg.querySelector('.cp-cursor');
    const dot = svg.querySelector('.cp-focus-dot');

    function selectAt(event) {
      const box = svg.getBoundingClientRect();
      if (!box.width) return;
      const coordinate = (event.clientX - box.left) * w / box.width;
      setMonth((coordinate-left) * (months.length-1) / (w-left-right));
    }
    svg.addEventListener('click', selectAt);
    svg.addEventListener('pointermove', event => {
      if (event.pointerType === 'mouse') selectAt(event);
    });

    return index => {
      const horizontal = x(index);
      cursor.setAttribute('x1', horizontal);
      cursor.setAttribute('x2', horizontal);
      const value = values[index];
      dot.setAttribute('visibility', value == null ? 'hidden' : 'visible');
      if (value != null) {
        dot.setAttribute('cx', horizontal);
        dot.setAttribute('cy', y(value));
      }
    };
  }

  function updateCharts() {
    plotWidth = chartRevenue.clientWidth;
    if (!plotWidth) return;
    const revenue = trackedRevenue();
    pointers = [
      plot(chartRevenue, months.map(m => yoy(revenue[m]?.revenue, revenue[m]?.previousYear)),
        'var(--cp-revenue)', company.name + '月營收年增率折線圖', '目前未取得這家公司的歷史月營收。'),
      plot(chartFreight, months.map(marketChange), 'var(--cp-freight)',
        market.code + '月均運價年增率折線圖', market.code + ' 歷史運價暫缺，可從船型列表選擇其他指數。'),
    ];
    updateReadout();
  }

  function setMarket(option) {
    market = option;
    choices.querySelectorAll('button').forEach(button =>
      button.setAttribute('aria-pressed', String(button.dataset.market === market.code)));
    $('cp-freight-title').textContent = market.code + ' 運價月均值';
    $('cp-freight-label').textContent = market.code + ' 月均';
    link('cp-freight-source', freight[market.code]?.sourceUrl);
    updateCharts();
  }

  function setCompany() {
    company = companies.get(picker.value);
    const total = company.bulk.reduce((n, value) => n + (value || 0), 0);
    const markets = benchmarks.map(benchmark => ({...benchmark,
      count: benchmark.columns.reduce((n, column) => n + (company.bulk[column] || 0), 0),
    })).filter(benchmark => benchmark.count > 0).sort((a, b) => b.count - a.count);

    $('cp-revenue-title').textContent = company.name + '月營收';
    $('cp-fleet-summary').textContent = '官網列示乾散貨船 ' + total + ' 艘';
    $('cp-fleet-basis').textContent = company.basis + '。船型比例按已列示乾散貨船艘數計算。' +
      (company.name === '裕民' ? '船隊含合資及在建。' : '');
    link('cp-fleet-source', company.url);
    choices.replaceChildren();
    markets.forEach((option, i) => {
      const button = document.createElement('button');
      button.className = 'cp-market';
      button.type = 'button';
      button.dataset.market = option.code;
      button.innerHTML = `<strong>${option.code}</strong><span class="cp-market-share">${fmt(100*option.count/total, 0)}%</span>
        <small>${option.label} · ${option.count} 艘${i===0?' · 艘數最多':''}${freight[option.code]?'':' · 暫缺歷史資料'}</small>`;
      button.addEventListener('click', () => setMarket(option));
      choices.append(button);
    });
    setMarket(markets[0]);
  }

  picker.addEventListener('change', setCompany);
  slider.addEventListener('input', () => setMonth(Number(slider.value)));
  setCompany();
  new ResizeObserver(() => {
    if (chartRevenue.clientWidth && chartRevenue.clientWidth !== plotWidth) updateCharts();
  }).observe(chartRevenue);
})();
