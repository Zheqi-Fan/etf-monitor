/* ETF 资金流监测 · FOMC 子页渲染 */
(function () {
  const F = window.FOMC_DATA;
  const D = window.DASHBOARD_DATA;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  const RED = '#c7000b', GREEN = '#0d7a63', BLUE = '#000066', GOLD = '#a8890a';
  const text = { color: '#69707f', fontSize: 11, fontFamily: '-apple-system,PingFang SC,sans-serif' };
  const tipBase = { trigger: 'axis', backgroundColor: 'rgba(0,0,45,.95)', borderWidth: 0, textStyle: { color: '#e9ecf5', fontSize: 12 } };

  const today = new Date().toISOString().slice(0, 10);
  const cls = v => v > 0 ? 'pos' : v < 0 ? 'neg' : '';
  function num(v, d = 1, sign = true) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const s = Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d });
    return (sign ? (v > 0 ? '+' : v < 0 ? '−' : '') : (v < 0 ? '−' : '')) + s;
  }
  const md = s => s ? s.slice(5) : '—';

  if (!F) {
    $$('.fomc-empty').forEach(e => { e.hidden = false; });
    return;
  }
  const meetings = F.meetings || [];
  const rates = F.rates || [];

  /* ---------------- KPI ---------------- */
  const cur = F.current || {};
  const next = F.meta.next;
  const dtn = F.meta.days_to_next;
  const yearNow = today.slice(0, 4);
  const thisYear = meetings.filter(m => m.end.slice(0, 4) === yearNow);
  const leftThisYear = thisYear.filter(m => m.end >= today).length;
  const lastRate = rates[rates.length - 1];

  const asof = $('#fomcAsOf');
  if (asof) asof.textContent = F.meta.generated_at || '—';

  const kp = $('#fomcKpis');
  if (kp) {
    const items = [
      { label: '当前目标区间', v: cur.level ? cur.level + '%' : '—',
        sub: cur.asof ? '自 ' + cur.asof + ' 起' : '', color: BLUE },
      { label: '最近一次决议', v: lastRate ? (lastRate.change > 0 ? '+' : '') + lastRate.change + ' bp' : '—',
        sub: lastRate ? lastRate.date + ' → ' + lastRate.level + '%' : '',
        color: lastRate && lastRate.change < 0 ? GREEN : RED },
      { label: '距下次会议', v: (dtn === null || dtn === undefined) ? '—' : dtn + ' 天',
        sub: next ? '决议日 ' + next : '', color: GOLD },
      { label: '年内剩余会议', v: leftThisYear + ' 次',
        sub: yearNow + ' 年共 ' + thisYear.length + ' 次', color: '#5b7cc4' },
    ];
    kp.innerHTML = items.map(k => `
      <div class="kpi" style="border-top:2px solid ${k.color}">
        <label>${k.label}</label>
        <div class="v">${k.v}</div>
        <div class="sub"><span>${k.sub}</span></div>
      </div>`).join('');
  }

  /* ---------------- 利率路径 ---------------- */
  const el = $('#chartRate');
  if (el && rates.length) {
    const dates = rates.map(r => r.date);
    const lo = rates.map(r => parseFloat(r.level.split('-')[0]));
    const hi = rates.map(r => {
      const p = r.level.split('-');
      return parseFloat(p[1] !== undefined ? p[1] : p[0]);
    });
    const c = echarts.init(el, null, { renderer: 'canvas' });
    c.setOption({
      animation: false,
      grid: { left: 52, right: 20, top: 34, bottom: 30 },
      legend: { top: 0, left: 0, itemWidth: 12, itemHeight: 8, itemGap: 14, textStyle: text, data: ['区间上限', '区间下限'] },
      tooltip: { ...tipBase, valueFormatter: v => (v === null || v === undefined) ? '—' : v.toFixed(2) + '%' },
      xAxis: {
        type: 'category', data: dates, boundaryGap: false, axisTick: { show: false },
        axisLine: { lineStyle: { color: '#e2e4e9' } },
        axisLabel: { ...text, formatter: v => v.slice(2, 7).replace('-', '/'), hideOverlap: true },
      },
      yAxis: {
        type: 'value', name: '%', nameTextStyle: { ...text, fontSize: 10, color: '#a0a7b4' },
        splitLine: { lineStyle: { color: '#eef0f3' } }, axisLabel: text,
        axisLine: { show: false }, axisTick: { show: false }, scale: true,
      },
      series: [
        { name: '区间上限', type: 'line', step: 'end', data: hi, symbol: 'none',
          lineStyle: { width: 2, color: BLUE }, areaStyle: { color: 'rgba(0,0,102,.10)' } },
        { name: '区间下限', type: 'line', step: 'end', data: lo, symbol: 'none',
          lineStyle: { width: 1.4, color: '#8f97b8', type: 'dashed' } },
      ],
    });
    window.addEventListener('resize', () => c.resize());
  }

  /* ---------------- 会议日历 ---------------- */
  const shown = meetings.filter(m => m.end.slice(0, 4) >= yearNow);
  const rng = $('#fomcRange');
  if (rng && shown.length) {
    rng.textContent = shown[0].start.slice(0, 4) + ' – ' + shown[shown.length - 1].end.slice(0, 4);
  }
  const tb = $('#fomcTable tbody');
  if (tb) {
    tb.innerHTML = shown.map(m => {
      const past = m.end < today;
      const isNext = m.end === next;
      const tag = isNext ? '<span class="tag t1">下次</span>'
        : (past ? '<span class="tag t2">已开</span>' : '<span class="tag">待开</span>');
      const links = m.statement
        ? `<a href="${m.statement}" target="_blank" rel="noopener">声明</a>`
        : '—';
      return `<tr${isNext ? ' style="background:#f4f6fd"' : ''}>
        <td>${m.start}${m.start !== m.end ? ' ~ ' + md(m.end) : ''}</td>
        <td class="mono">${m.end}</td>
        <td>${m.sep ? '<b style="color:' + GOLD + '">★</b>' : '—'}</td>
        <td>${tag}</td>
        <td class="mono">${m.minutes_release || '—'}</td>
        <td>${links}</td>
      </tr>`;
    }).join('');
  }

  /* ---------------- 事件研究 ---------------- */
  const evTb = $('#fomcEvent tbody');
  if (evTb && D) {
    const dts = D.dates, hs = D.hs300, fl = D.total.flow;
    const out = [];
    meetings.filter(m => m.end < today).slice(-10).reverse().forEach(m => {
      const i = dts.findIndex(x => x > m.end);
      if (i <= 0) return;
      const ret = (hs[i] / hs[i - 1] - 1) * 100;
      const flow = fl[i];
      const rr = rates.filter(r => r.date <= m.end).slice(-1)[0];
      const moved = rr && rr.date <= m.end && rr.date >= m.start;
      out.push(`<tr>
        <td class="mono">${m.end}</td>
        <td class="num ${rr ? (rr.change > 0 ? 'pos' : rr.change < 0 ? 'neg' : '') : ''}">${moved ? (rr.change > 0 ? '+' : '') + rr.change + ' bp' : '维持不变'}</td>
        <td class="mono">${rr ? rr.level + '%' : '—'}</td>
        <td class="num ${cls(ret)}">${num(ret, 2)}%</td>
        <td class="num ${cls(flow)}">${num(flow, 1)} 亿</td>
        <td class="mono">${dts[i]}</td>
      </tr>`);
    });
    evTb.innerHTML = out.length ? out.join('')
      : '<tr><td colspan="6" class="muted">主数据未覆盖决议日，暂无法计算</td></tr>';
  }
})();
