/* ETF 资金流监测 · 经济数据日历渲染 */
(function () {
  const E = window.ECON_DATA;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));

  const BLUE = '#000066', GOLD = '#a8890a', RED = '#c7000b', GREEN = '#0d7a63';
  const today = new Date().toISOString().slice(0, 10);

  if (!E) {
    $$('.econ-empty').forEach(e => { e.hidden = false; });
    return;
  }
  const events = E.events || [];
  const m = E.meta || {};

  const asof = $('#econAsOf');
  if (asof) asof.textContent = m.generated_at || '—';

  /* ---------------- KPI ---------------- */
  const future = events.filter(e => e.date_bj >= today);
  const nxt = future[0];
  const kp = $('#econKpis');
  if (kp) {
    const items = [
      { label: '下一项核心数据', v: nxt ? nxt.cat : '—',
        sub: nxt ? nxt.date_bj + ' ' + nxt.time_bj : '', color: BLUE },
      { label: '距今', v: (m.days_to_next === null || m.days_to_next === undefined) ? '—' : m.days_to_next + ' 天',
        sub: nxt ? nxt.title.slice(0, 22) : '', color: GOLD },
      { label: '未来已知事件', v: future.length + ' 项',
        sub: '六类核心数据合计', color: '#5b7cc4' },
      { label: '未来 7 天高影响', v: (m.week_high || 0) + ' 项',
        sub: '★ 级别', color: RED },
    ];
    kp.innerHTML = items.map(k => `
      <div class="kpi" style="border-top:2px solid ${k.color}">
        <label>${k.label}</label>
        <div class="v">${k.v}</div>
        <div class="sub"><span>${k.sub}</span></div>
      </div>`).join('');
  }

  /* ---------------- 日历 ---------------- */
  const shown = events.filter(e => e.date_bj >= today);
  const rng = $('#econRange');
  if (rng && shown.length) {
    rng.textContent = shown[0].date_bj.slice(0, 7) + ' – ' + shown[shown.length - 1].date_bj.slice(0, 7);
  }
  const tb = $('#econTable tbody');
  if (tb) {
    if (!shown.length) {
      tb.innerHTML = '<tr><td colspan="8" class="muted">暂无未来事件</td></tr>';
    } else {
      tb.innerHTML = shown.map(e => {
        const isNext = nxt && e.date === nxt.date && e.cat === nxt.cat;
        const imp = e.importance === 'High' ? '<b style="color:' + GOLD + '">★</b>' : '—';
        const src = e.confirmed ? e.source : `<span style="color:var(--faint)">${e.source}</span>`;
        return `<tr${isNext ? ' style="background:#f4f6fd"' : ''}>
          <td class="mono">${e.date_bj}</td>
          <td class="mono">${e.time_bj}</td>
          <td>${e.title}</td>
          <td>${e.cat}</td>
          <td>${imp}</td>
          <td class="num">${e.forecast || '—'}</td>
          <td class="num">${e.previous || '—'}</td>
          <td style="font-size:11px;color:var(--muted)">${src}</td>
        </tr>`;
      }).join('');
    }
  }

  /* ---------------- 来源说明 ---------------- */
  const notes = $('#econNotes');
  if (notes) {
    const cats = m.cats || {};
    const catLine = Object.keys(cats).length
      ? Object.entries(cats).map(([k, v]) => `${k} ${v} 项`).join(' · ')
      : '—';
    const base = [
      `收录范围：${catLine}。其余发布（ISM、消费者信心、JOLTS、初请等）一律不收。`,
      ...(m.notes || []),
    ];
    notes.innerHTML = base.map(t => `<li>${t}</li>`).join('');
  }
})();
