/* ETF 资金流监测 · 衍生品子页渲染（基差 / 拥挤度） */
(function () {
  const D = window.DERIV_DATA;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  const RED = '#c4262c', GREEN = '#0d7a63', BLUE = '#000066', GOLD = '#a8890a';
  const PROD_COLOR = { IF: '#000066', IH: '#1a1ab8', IC: '#5b7cc4', IM: '#0d7a63' };
  const PROD_NAME = { IF: 'IF 沪深300', IH: 'IH 上证50', IC: 'IC 中证500', IM: 'IM 中证1000' };
  const text = { color: '#69707f', fontSize: 11, fontFamily: '-apple-system,PingFang SC,sans-serif' };
  const grid = { left: 56, right: 20, top: 34, bottom: 30 };
  const tipBase = { trigger: 'axis', backgroundColor: 'rgba(0,0,45,.95)', borderWidth: 0, textStyle: { color: '#e9ecf5', fontSize: 12 } };
  const axisX = dates => ({
    type: 'category', data: dates, boundaryGap: false, axisTick: { show: false },
    axisLine: { lineStyle: { color: '#e2e4e9' } },
    axisLabel: { ...text, formatter: v => String(v).slice(2, 7).replace('-', '/'), hideOverlap: true },
  });
  const axisY = (name) => ({
    type: 'value', name, nameTextStyle: { ...text, fontSize: 10, color: '#a0a7b4' },
    splitLine: { lineStyle: { color: '#eef0f3' } }, axisLabel: text,
    axisLine: { show: false }, axisTick: { show: false },
  });

  function num(v, d = 2, sign = true) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const s = Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d });
    return (sign ? (v > 0 ? '+' : v < 0 ? '−' : '') : (v < 0 ? '−' : '')) + s;
  }
  const cls = v => v > 0 ? 'pos' : v < 0 ? 'neg' : '';

  function mk(id, opt) {
    const el = $(id);
    if (!el) return null;
    const c = echarts.init(el, null, { renderer: 'canvas' });
    if (opt) c.setOption(opt);
    window.addEventListener('resize', () => c.resize());
    return c;
  }

  if (!D) {
    $$('.deriv-empty').forEach(e => { e.hidden = false; });
    return;
  }

  /* ==================== 基差页 ==================== */
  function renderBasis() {
    const head = $('#basisAsOf');
    if (!head) return;
    const L = D.latest_basis || {};
    head.textContent = D.meta.end || '—';

    // KPI
    const kp = $('#basisKpis');
    if (kp) {
      const spread = D.spread_im_if ? D.spread_im_if[D.spread_im_if.length - 1] : null;
      const items = Object.keys(L).map(p => ({
        label: PROD_NAME[p] || p,
        v: L[p].basis_ann, unit: '%',
        sub: `基差 ${num(L[p].basis_pct, 2)}% · 剩 ${L[p].dte} 天`,
        color: PROD_COLOR[p],
      }));
      items.push({ label: 'IM − IF 价差', v: spread, unit: 'pct', sub: '小盘相对大盘对冲成本', color: GOLD });
      kp.innerHTML = items.map(k => `
        <div class="kpi" style="border-top:2px solid ${k.color}">
          <label>${k.label}<span class="mono" style="color:var(--faint)">${k.unit}</span></label>
          <div class="v ${cls(k.v)}">${num(k.v, 2)}</div>
          <div class="sub"><span>${k.sub}</span></div>
        </div>`).join('');
    }

    // 主图：四个品种年化基差
    const prods = Object.keys(D.basis);
    const c1 = mk('#chartBasis', {
      animation: false,
      grid,
      legend: { top: 0, left: 0, itemWidth: 12, itemHeight: 8, itemGap: 14, textStyle: text,
        data: prods.map(p => PROD_NAME[p] || p) },
      tooltip: { ...tipBase, valueFormatter: v => v === null ? '—' : num(v, 2) + '%' },
      xAxis: axisX(D.dates),
      yAxis: axisY('年化基差 %'),
      series: prods.map(p => ({
        name: PROD_NAME[p] || p, type: 'line', data: D.basis[p].ann, symbol: 'none',
        lineStyle: { width: 1.7, color: PROD_COLOR[p] },
        emphasis: { focus: 'series' },
      })),
    });
    if (c1) c1.setOption({
      series: prods.map(p => ({ markLine: p === prods[0] ? {
        silent: true, symbol: 'none', lineStyle: { color: 'rgba(0,6,40,.25)', type: 'dashed' },
        label: { show: false }, data: [{ yAxis: 0 }],
      } : undefined })),
    });

    // IM − IF
    mk('#chartSpread', {
      animation: false,
      grid,
      tooltip: { ...tipBase, valueFormatter: v => v === null ? '—' : num(v, 2) + ' pct' },
      xAxis: axisX(D.dates),
      yAxis: axisY('IM − IF 年化基差差 %'),
      series: [{
        name: 'IM − IF', type: 'line', data: D.spread_im_if || [], symbol: 'none',
        lineStyle: { width: 1.7, color: GOLD },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(168,137,10,.22)' }, { offset: 1, color: 'rgba(168,137,10,0)' }]) },
        markLine: { silent: true, symbol: 'none', lineStyle: { color: 'rgba(0,6,40,.25)' },
          label: { show: false }, data: [{ yAxis: 0 }] },
      }],
    });

    // 期限结构：主力 vs 次主力
    const cats = Object.keys(L);
    mk('#chartTerm', {
      animation: false,
      grid: { ...grid, top: 40 },
      legend: { top: 0, left: 0, itemWidth: 12, itemHeight: 8, textStyle: text, data: ['主力合约', '次主力合约'] },
      tooltip: { ...tipBase, valueFormatter: v => num(v, 2) + '%' },
      xAxis: { type: 'category', data: cats, axisTick: { show: false },
        axisLine: { lineStyle: { color: '#e2e4e9' } }, axisLabel: text },
      yAxis: axisY('年化基差 %'),
      series: [
        { name: '主力合约', type: 'bar', barMaxWidth: 26,
          data: cats.map(p => ({ value: L[p].basis_ann, itemStyle: { color: PROD_COLOR[p] } })),
          label: { show: true, position: 'top', formatter: p => num(p.value, 2), color: '#69707f', fontSize: 10 } },
        { name: '次主力合约', type: 'bar', barMaxWidth: 26,
          data: cats.map(p => L[p].next_ann),
          itemStyle: { color: 'rgba(105,112,127,.45)' }, borderRadius: [3, 3, 0, 0] },
      ],
    });

    // 快照表
    const tb = $('#basisTable tbody');
    if (tb) {
      tb.innerHTML = cats.map(p => {
        const x = L[p];
        return `<tr>
          <td><b>${p}</b></td>
          <td>${PROD_NAME[p].split(' ')[1]}</td>
          <td class="mono">${x.code || '—'}</td>
          <td class="num">${x.dte}</td>
          <td class="num ${cls(x.basis_pct)}">${num(x.basis_pct, 2)}%</td>
          <td class="num ${cls(x.basis_ann)}">${num(x.basis_ann, 2)}%</td>
          <td class="num ${cls(x.next_ann)}">${num(x.next_ann, 2)}%</td>
          <td class="num">${x.oi === null ? '—' : Math.round(x.oi).toLocaleString('zh-CN')}</td>
        </tr>`;
      }).join('');
    }
  }

  /* ==================== 拥挤度页 ==================== */
  function renderCrowding() {
    const C = D.crowding;
    const head = $('#crowdAsOf');
    if (!head) return;
    if (!C) { $$('.crowd-missing').forEach(e => { e.hidden = false; }); return; }
    head.textContent = C.asof || '—';

    const i = C.dates.length - 1;
    const rz = C.rz[i], rq = C.rq[i], pct = C.rz_pct[i];
    const oiTotal = (D.basis.IF ? 0 : 0) +
      ['IF', 'IH', 'IC', 'IM'].reduce((s, p) => s + ((D.basis[p] && D.basis[p].oi[i]) || 0), 0);

    const kp = $('#crowdKpis');
    if (kp) {
      const items = [
        { label: '核心池融资余额', v: rz, unit: '亿', sub: '杠杆多头存量', color: RED },
        { label: '融资余额 / 核心池规模', v: pct, unit: '%', sub: '越高越拥挤', color: RED },
        { label: '核心池融券余额', v: rq, unit: '亿', sub: '反向/对冲存量', color: GREEN },
        { label: '期货主力持仓量', v: oiTotal, unit: '手', sub: '4 品种合计，对冲盘规模', color: BLUE },
        { label: '全市场两融余额', v: C.mkt_rz[i], unit: '亿', sub: '风险偏好背景', color: '#5b7cc4' },
      ];
      kp.innerHTML = items.map(k => `
        <div class="kpi" style="border-top:2px solid ${k.color}">
          <label>${k.label}<span class="mono" style="color:var(--faint)">${k.unit}</span></label>
          <div class="v">${k.unit === '手' ? Math.round(k.v || 0).toLocaleString('zh-CN') : num(k.v, k.unit === '%' ? 2 : 1, false)}</div>
          <div class="sub"><span>${k.sub}</span></div>
        </div>`).join('');
    }

    // 融资/融券余额 + 占比
    const c1 = mk('#chartMargin', {
      animation: false,
      grid: { left: 58, right: 62, top: 34, bottom: 30 },
      legend: { top: 0, left: 0, itemWidth: 12, itemHeight: 8, itemGap: 14, textStyle: text,
        data: ['融资余额', '融券余额', '融资余额/规模'] },
      tooltip: tipBase,
      xAxis: axisX(C.dates),
      yAxis: [
        { ...axisY('亿元'), splitLine: { lineStyle: { color: '#eef0f3' } } },
        { ...axisY('占规模 %'), position: 'right', splitLine: { show: false } },
      ],
      series: [
        { name: '融资余额', type: 'line', data: C.rz, symbol: 'none', yAxisIndex: 0,
          lineStyle: { width: 1.8, color: RED },
          areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(196,38,44,.20)' }, { offset: 1, color: 'rgba(196,38,44,0)' }]) } },
        { name: '融券余额', type: 'line', data: C.rq, symbol: 'none', yAxisIndex: 0,
          lineStyle: { width: 1.4, color: GREEN } },
        { name: '融资余额/规模', type: 'line', data: C.rz_pct, symbol: 'none', yAxisIndex: 1,
          lineStyle: { width: 1.3, color: BLUE, type: 'dashed' } },
      ],
    });

    // 期货持仓量
    mk('#chartOi', {
      animation: false,
      grid,
      legend: { top: 0, left: 0, itemWidth: 12, itemHeight: 8, itemGap: 14, textStyle: text,
        data: ['IF', 'IH', 'IC', 'IM'].map(p => PROD_NAME[p]) },
      tooltip: { ...tipBase, valueFormatter: v => v === null ? '—' : Math.round(v).toLocaleString('zh-CN') },
      xAxis: axisX(D.dates),
      yAxis: axisY('手'),
      series: ['IF', 'IH', 'IC', 'IM'].filter(p => D.basis[p]).map(p => ({
        name: PROD_NAME[p], type: 'line', data: D.basis[p].oi, symbol: 'none',
        lineStyle: { width: 1.6, color: PROD_COLOR[p] },
      })),
    });

    // 全市场两融
    mk('#chartMarket', {
      animation: false,
      grid,
      tooltip: { ...tipBase, valueFormatter: v => v === null ? '—' : num(v, 0, false) + ' 亿' },
      xAxis: axisX(C.dates),
      yAxis: axisY('亿元'),
      series: [{
        name: '全市场融资余额', type: 'line', data: C.mkt_rz, symbol: 'none',
        lineStyle: { width: 1.7, color: '#5b7cc4' },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(91,124,196,.22)' }, { offset: 1, color: 'rgba(91,124,196,0)' }]) },
      }],
    });

    // 分 ETF 表
    const tb = $('#crowdTable tbody');
    if (tb) {
      tb.innerHTML = (C.etfs || []).map(x => `<tr>
        <td><span class="code">${x.code}</span></td>
        <td><span class="etf-name">${x.name}</span></td>
        <td class="num">${num(x.aum, 0, false)}</td>
        <td class="num ${cls(x.rz)}">${num(x.rz, 1, false)}</td>
        <td class="num ${x.rz_pct >= 5 ? 'pos' : ''}">${x.rz_pct === null ? '—' : num(x.rz_pct, 2, false) + '%'}</td>
        <td class="num ${cls(x.rq)}">${num(x.rq, 2, false)}</td>
        <td class="num">${x.rq && x.aum ? (x.rq / x.aum * 100).toFixed(2) + '%' : '—'}</td>
        <td class="num ${cls(x.f20pct)}">${x.f20pct === null ? '—' : num(x.f20pct, 1) + '%'}</td>
      </tr>`).join('');
    }
  }

  renderBasis();
  renderCrowding();
})();
