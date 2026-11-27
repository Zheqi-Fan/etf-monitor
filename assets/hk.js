/* ETF 资金流监测 · 港股与南向资金子页 */
(function () {
  const H = window.HK_DATA;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  if (!H) {
    $$('.hk-empty').forEach(e => { e.hidden = false; });
    return;
  }

  const RED = '#c7000b', GREEN = '#0d7a63', BLUE = '#000066', GOLD = '#a8890a';
  const chartText = { color: '#69707f', fontSize: 11, fontFamily: '-apple-system,PingFang SC,sans-serif' };
  const tipBase = {
    trigger: 'axis', backgroundColor: 'rgba(0,0,45,.95)', borderWidth: 0,
    textStyle: { color: '#e9ecf5', fontSize: 12 }
  };

  const M = H.meta || {};
  const dates = H.dates || [];
  const idx = dates.length - 1;

  function num(v, d = 1, sign = true) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const s = Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d });
    if (sign) return (v > 0 ? '+' : v < 0 ? '−' : '') + s;
    return (v < 0 ? '−' : '') + s;
  }
  const cls = v => (v > 0 ? 'pos' : v < 0 ? 'neg' : '');

  $('#hkAsOf').textContent = M.generated_at || '—';
  $('#hkFrom').textContent = M.from || '—';
  $('#hkDays').textContent = (M.days || 0).toLocaleString('zh-CN');
  if (M.top10_date) {
    const d = String(M.top10_date);
    $('#hkTopDate').textContent = `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}`;
  }

  /* ---------------- KPI ---------------- */
  const kp = $('#hkKpis');
  if (kp) {
    const items = [
      { label: '南向年内净买入', v: num(M.south_ytd, 0) + ' 亿',
        sub: (M.asof || '').slice(0, 4) + ' 年至今累计', color: BLUE },
      { label: '南向 20 日净买入', v: num(M.south_20d, 0) + ' 亿',
        sub: '滚动 20 个交易日', color: M.south_20d >= 0 ? RED : GREEN },
      { label: '恒生指数 / 恒生科技', v: num(H.hsi[idx], 0, false),
        sub: '恒生科技 ' + num(H.hstech[idx], 0, false), color: GOLD },
      { label: 'AH 溢价指数', v: M.ah === null || M.ah === undefined ? '—' : num(M.ah, 2, false),
        sub: (M.ah_chg === null || M.ah_chg === undefined ? '仅当前值' : num(M.ah_chg, 2) + '%')
          + ' · 无历史序列', color: '#5b7cc4' },
    ];
    kp.innerHTML = items.map(k => `
      <div class="kpi" style="border-top:2px solid ${k.color}">
        <label>${k.label}</label>
        <div class="v">${k.v}</div>
        <div class="sub"><span>${k.sub}</span></div>
      </div>`).join('');
  }

  /* ---------------- 区间 ---------------- */
  const state = { range: 'all' };
  const START = { '1y': 1, '3y': 3, '5y': 5 };
  function startIndex(range) {
    if (range === 'all') return 0;
    const n = START[range];
    if (!n) return 0;
    const last = new Date(dates[idx] + 'T00:00:00');
    last.setFullYear(last.getFullYear() - n);
    const iso = last.toISOString().slice(0, 10);
    const i = dates.findIndex(d => d >= iso);
    return i < 0 ? 0 : i;
  }
  const xInt = n => (window.innerWidth < 720 ? Math.max(1, Math.floor(n / 4)) : 'auto');
  const xAxisBase = ds => ({
    type: 'category', data: ds, boundaryGap: false, axisTick: { show: false },
    axisLine: { lineStyle: { color: '#e2e4e9' } },
    axisLabel: { ...chartText, formatter: v => v.slice(2, 7).replace('-', '/'), hideOverlap: true, interval: xInt(ds.length) }
  });

  const charts = [];
  function mk(el, opt) {
    if (!el) return null;
    const c = echarts.init(el, null, { renderer: 'canvas' });
    c.setOption(opt);
    charts.push(c);
    return c;
  }
  function setOpt(c, opt) { if (c) c.setOption(opt, true); }

  const cumChart = mk($('#chartHkCum'), {});
  const flowChart = mk($('#chartHkFlow'), {});
  const shareChart = mk($('#chartHkShare'), {});

  /* ---------------- 累计净买入 vs 恒指 ---------------- */
  function renderCum() {
    const i0 = startIndex(state.range);
    const ds = dates.slice(i0);
    const cum = H.cum.slice(i0);
    const hsi = H.hsi.slice(i0);
    setOpt(cumChart, {
      animation: false,
      grid: { left: 56, right: 62, top: 34, bottom: 28 },
      legend: { top: 0, left: 0, itemWidth: 12, itemHeight: 8, itemGap: 14, textStyle: chartText,
        data: ['南向累计净买入', '恒生指数'] },
      tooltip: {
        ...tipBase,
        formatter: p => `<div style="font-family:monospace;color:#b9bfd6;margin-bottom:5px">${p[0].axisValue}</div>`
          + `<div style="display:flex;justify-content:space-between;gap:22px"><span>南向累计</span><b style="font-family:monospace">${p[0].value == null ? '—' : num(p[0].value, 0, false) + ' 亿'}</b></div>`
          + `<div style="display:flex;justify-content:space-between;gap:22px"><span>恒生指数</span><b style="font-family:monospace">${p[1] && p[1].value != null ? num(p[1].value, 0, false) : '—'}</b></div>`
      },
      xAxis: xAxisBase(ds),
      yAxis: [
        {
          type: 'value', name: '亿', nameLocation: 'end', nameGap: 8,
          nameTextStyle: { ...chartText, fontSize: 10, color: '#a0a7b4', align: 'right' },
          splitLine: { lineStyle: { color: '#eef0f3' } }, axisLabel: chartText,
          scale: true, axisLine: { show: false }, axisTick: { show: false }
        },
        {
          type: 'value', name: '点', nameLocation: 'end', nameGap: 8, position: 'right',
          nameTextStyle: { ...chartText, fontSize: 10, color: '#a0a7b4', align: 'left' },
          splitLine: { show: false }, axisLabel: chartText,
          scale: true, axisLine: { show: false }, axisTick: { show: false }
        }
      ],
      series: [
        {
          name: '南向累计净买入', type: 'line', data: cum, symbol: 'none',
          lineStyle: { width: 2.2, color: BLUE },
          areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(0,0,102,.18)' }, { offset: 1, color: 'rgba(0,0,102,0)' }]) }
        },
        {
          name: '恒生指数', type: 'line', yAxisIndex: 1, data: hsi, symbol: 'none',
          lineStyle: { width: 1.4, color: '#8f97b8', type: 'dashed' }
        }
      ]
    });
  }

  /* ---------------- 日净买入 + 20 日滚动 ---------------- */
  function renderFlow() {
    const i0 = startIndex(state.range);
    const ds = dates.slice(i0);
    const net = H.net.slice(i0);
    const net20 = H.net20.slice(i0);
    setOpt(flowChart, {
      animation: false,
      grid: { left: 46, right: 12, top: 30, bottom: 24 },
      legend: { top: 0, left: 0, itemWidth: 12, itemHeight: 8, itemGap: 14, textStyle: chartText,
        data: ['日净买入', '20日滚动'] },
      tooltip: {
        ...tipBase,
        formatter: p => `<div style="font-family:monospace;color:#b9bfd6;margin-bottom:5px">${p[0].axisValue}</div>`
          + p.map(x => `<div style="display:flex;justify-content:space-between;gap:22px"><span>${x.seriesName}</span><b style="font-family:monospace">${x.value == null ? '—' : num(x.value, 1) + ' 亿'}</b></div>`).join('')
      },
      xAxis: xAxisBase(ds),
      yAxis: {
        type: 'value', name: '亿', nameLocation: 'end', nameGap: 8,
        nameTextStyle: { ...chartText, fontSize: 10, color: '#a0a7b4', align: 'right' },
        splitLine: { lineStyle: { color: '#eef0f3' } }, axisLabel: chartText,
        axisLine: { show: false }, axisTick: { show: false }
      },
      series: [
        {
          name: '日净买入', type: 'bar', data: net, barMaxWidth: 5,
          itemStyle: { color: p => (p.value >= 0 ? 'rgba(199,0,11,.45)' : 'rgba(13,122,99,.45)') }
        },
        {
          name: '20日滚动', type: 'line', data: net20, symbol: 'none',
          lineStyle: { width: 1.8, color: BLUE },
          markLine: { silent: true, symbol: 'none', lineStyle: { color: 'rgba(0,6,40,.2)' }, label: { show: false }, data: [{ yAxis: 0 }] }
        }
      ]
    });
  }

  /* ---------------- 南向成交占比 ---------------- */
  function renderShare() {
    const i0 = startIndex(state.range);
    const ds = dates.slice(i0);
    const share = H.share.slice(i0);
    // 20 日均值在整条序列上算完再切，避免窗口开头空一截
    const ma = H.share.map((v, i) => {
      if (i < 19) return null;
      let s = 0, c = 0;
      for (let j = i - 19; j <= i; j++) { if (H.share[j] != null) { s += H.share[j]; c++; } }
      return c ? +(s / c).toFixed(2) : null;
    }).slice(i0);
    setOpt(shareChart, {
      animation: false,
      grid: { left: 46, right: 12, top: 30, bottom: 24 },
      legend: { top: 0, left: 0, itemWidth: 12, itemHeight: 8, itemGap: 14, textStyle: chartText,
        data: ['南向成交占比', '20日均值'] },
      tooltip: {
        ...tipBase,
        formatter: p => `<div style="font-family:monospace;color:#b9bfd6;margin-bottom:5px">${p[0].axisValue}</div>`
          + p.map(x => `<div style="display:flex;justify-content:space-between;gap:22px"><span>${x.seriesName}</span><b style="font-family:monospace">${x.value == null ? '—' : num(x.value, 2, false) + '%'}</b></div>`).join('')
      },
      xAxis: xAxisBase(ds),
      yAxis: {
        type: 'value', name: '%', nameLocation: 'end', nameGap: 8,
        nameTextStyle: { ...chartText, fontSize: 10, color: '#a0a7b4', align: 'right' },
        splitLine: { lineStyle: { color: '#eef0f3' } }, axisLabel: chartText,
        axisLine: { show: false }, axisTick: { show: false }
      },
      series: [
        {
          name: '南向成交占比', type: 'line', data: share, symbol: 'none',
          lineStyle: { width: 1.2, color: 'rgba(0,0,102,.55)' },
          areaStyle: { color: 'rgba(0,0,102,.07)' }
        },
        { name: '20日均值', type: 'line', data: ma, symbol: 'none', lineStyle: { width: 1.6, color: GOLD } }
      ]
    });
  }

  /* ---------------- 十大成交股 ---------------- */
  const tb = $('#hkTopTable tbody');
  if (tb) {
    const rows = H.top10 || [];
    tb.innerHTML = rows.length ? rows.map(r => `<tr>
      <td class="mono">${r.code}</td>
      <td>${r.name}</td>
      <td class="num">${r.close == null ? '—' : num(r.close, 2, false)}</td>
      <td class="num ${cls(r.pct)}">${r.pct == null ? '—' : num(r.pct, 2) + '%'}</td>
      <td class="num ${cls(r.net)}">${r.net == null ? '—' : num(r.net, 2) + ' 亿'}</td>
      <td class="num">${r.turnover ? num(r.turnover, 1, false) + ' 亿' : '—'}</td>
      <td class="num">${r.rank == null ? '—' : r.rank}</td>
    </tr>`).join('') : '<tr><td colspan="7" class="muted">暂无数据</td></tr>';
  }

  /* ---------------- 区间按钮 ---------------- */
  $$('#hkRangeSeg button').forEach(b => b.addEventListener('click', () => {
    $$('#hkRangeSeg button').forEach(x => x.classList.remove('on'));
    b.classList.add('on');
    state.range = b.dataset.r;
    renderCum(); renderFlow(); renderShare();
  }));

  renderCum();
  renderFlow();
  renderShare();

  let rt;
  window.addEventListener('resize', () => {
    clearTimeout(rt);
    rt = setTimeout(() => {
      charts.forEach(c => c.resize());
      renderCum(); renderFlow(); renderShare();
    }, 150);
  });
})();
