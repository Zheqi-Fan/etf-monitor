/* ETF 资金流监测 · FOMC 子页渲染 */
(function () {
  const F = window.FOMC_DATA;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  const RED = '#c7000b', GREEN = '#0d7a63', BLUE = '#000066', GOLD = '#a8890a';

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
  const study = F.event_study || [];
  const srng = $('#fomcStudyRange');
  if (srng && study.length) {
    srng.textContent = study[0].date.slice(0, 4) + ' – ' + study[study.length - 1].date.slice(0, 4)
      + ' · ' + study.length + ' 场';
  }

  const bp = v => {
    if (v === null || v === undefined) return '<span class="muted">—</span>';
    if (Math.abs(v) < 0.001) return '不变';
    return (v > 0 ? '+' : '−') + Math.abs(v) + ' bp';
  };

  if (evTb) {
    const rows = study.slice().reverse().map(r => {
      const usCls = r.us_change_bp > 0 ? 'pos' : r.us_change_bp < 0 ? 'neg' : 'muted';
      const cnTxt = r.cn_lpr_1y === null || r.cn_lpr_1y === undefined
        ? '<span class="muted">—</span>'
        : `${r.cn_lpr_1y.toFixed(2)}%`
          + (r.cn_between_bp === null || r.cn_between_bp === undefined
            ? ''
            : `<span class="muted" style="font-size:11px"> · ${r.cn_between_bp === 0 ? '不变'
              : (r.cn_between_bp > 0 ? '+' : '−') + Math.abs(r.cn_between_bp) + 'bp'}</span>`);
      const td = (v, d) => v === null || v === undefined
        ? '<td class="num muted">—</td>'
        : `<td class="num ${cls(v)}">${num(v, d)}%</td>`;
      return `<tr>
        <td class="mono">${r.date}</td>
        <td class="num ${usCls}">${bp(r.us_change_bp)}</td>
        <td class="mono">${r.us_level ? r.us_level + '%' : '—'}</td>
        <td class="num">${cnTxt}</td>
        ${td(r.hs300_pct, 2)}
        ${td(r.HSI, 2)}
        ${td(r.HSTECH, 2)}
        <td class="num ${cls(r.pool_flow)}">${r.pool_flow === null || r.pool_flow === undefined
          ? '—' : num(r.pool_flow, 1) + ' 亿'}</td>
        <td class="mono" style="font-size:11px">${r.trade_date_a || '—'} / ${r.trade_date_hk || '—'}</td>
      </tr>`;
    });
    evTb.innerHTML = rows.length ? rows.join('')
      : '<tr><td colspan="9" class="muted">尚无已开会议可用于统计</td></tr>';
  }
})();
