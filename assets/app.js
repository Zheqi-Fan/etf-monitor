/* ETF 资金流监测 · 前端逻辑 */
(function () {
  const D = window.DASHBOARD_DATA;
  if (!D) { document.body.innerHTML = '<div style="padding:60px;font:16px sans-serif">数据未生成，请先运行 python3 fetch_data.py</div>'; return; }

  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const idx = D.dates.length - 1;
  const latest = D.latest;

  const RED = '#c7000b', GREEN = '#0d7a63', BLUE = '#000066', GOLD = '#a8890a';
  const FAM_COLORS = {
    '沪深300': '#000066', '上证50': '#1a1ab8', '中证500': '#5b7cc4',
    '中证1000': '#8a8f9e', '创业板': '#0d7a63', '科创50': '#9c7f00'
  };

  function num(v, d = 1, sign = true) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const s = Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d });
    if (sign) return (v > 0 ? '+' : v < 0 ? '−' : '') + s;
    return (v < 0 ? '−' : '') + s;
  }
  const cls = v => v > 0 ? 'pos' : v < 0 ? 'neg' : '';
  const pctTxt = v => v === null || v === undefined ? '—' : v.toFixed(1) + '%';
  const chartText = { color: '#69707f', fontSize: 11, fontFamily: '-apple-system,PingFang SC,sans-serif' };

  /* ---------------- hero ---------------- */
  $('#asof').textContent = latest.date;
  $('#generated').textContent = D.meta.generated_at;
  $('#footTime').textContent = D.meta.generated_at;
  $('#coverCount').textContent = D.meta.n_etf;
  $('#kpiDate').textContent = latest.date + ' 收盘';
  $('#rangeText').textContent = D.meta.start.slice(0, 7).replace('-', '.') + ' 至今';

  $('#sig20').textContent = num(latest.flow20, 1);
  const prev20 = D.total.flow20[idx - 20];
  const d20 = latest.flow20 - (prev20 ?? latest.flow20);
  $('#sigDelta').textContent = (d20 >= 0 ? '较前20日 +' : '较前20日 −') + Math.abs(d20).toFixed(1) + ' 亿';
  const rank = latest.rank20;
  const higher = (rank === null || rank === undefined) ? null : Math.max(0, Math.round((100 - rank) / 100 * 252));
  $('#sigRank').textContent = (rank === null || rank === undefined)
    ? '历史分位 —'
    : `过去一年 ${pctTxt(rank)} 分位 · 仅 ${higher} 个交易日更高`;
  $('#sigRank').title = `近 20 日累计 ${num(latest.flow20, 1)} 亿，相对自身过去 252 个交易日的 z-score 为 ${num(latest.z20, 2)}`;

  const badge = $('#signalBadge');
  const rk = rank ?? 50;
  badge.textContent = rk >= 90 ? '● 强势流入' : rk >= 65 ? '● 温和流入' : rk <= 10 ? '● 明显流出' : rk <= 35 ? '● 偏流出' : '● 中性';
  badge.className = 'badge ' + (rk >= 90 ? 'hot' : rk >= 65 ? 'warm' : rk <= 35 ? 'cold' : '');

  $('#tRank').textContent = pctTxt(rank);
  $('#tPrem').textContent = num(latest.premium, 0) + ' bp';
  $('#tTurn').textContent = latest.turnover ? (latest.turnover / 10000).toFixed(2) + ' 万亿' : '—';
  $('#turnDate').textContent = latest.date.slice(5) + ' 收盘';
  $('#ratioDate').textContent = latest.date + ' 收盘';
  $('#tCover').textContent = pctTxt(latest.coverage);

  /* ---------------- takeaway / data health / version ---------------- */
  const famNames = D.meta.families || [];
  const fam20 = famNames.map(f => {
    const arr = (D.families[f] || []).slice(-20);
    return { name: f, v: arr.reduce((a, b) => a + (b || 0), 0) };
  }).sort((a, b) => b.v - a.v);
  const top = fam20[0], second = fam20[1];
  const total20 = latest.flow20 || 0;
  const dirTxt = total20 >= 0 ? '净流入' : '净流出';
  const share = (v) => total20 ? Math.round(Math.abs(v / total20) * 100) : 0;
  if (top) {
    $('#takeawayText').innerHTML =
      `近 20 日核心池 <b class="${total20 >= 0 ? 'pos' : 'neg'}">${dirTxt} ${total20 >= 0 ? '+' : '−'}${num(Math.abs(total20), 0, false)} 亿</b>，位于过去一年 <b>${pctTxt(latest.rank20)}</b> 分位；` +
      `6 条宽基中 <b>${latest.breadth ?? '—'}</b> 条为正；结构上 <b>${top.name}</b> 贡献 <b>${num(top.v, 0)} 亿</b>（${share(top.v)}%）` +
      (second ? `，<b>${second.name}</b> ${num(second.v, 0)} 亿（${share(second.v)}%）。` : '。');
  }

  const endDate = new Date(D.meta.end + 'T00:00:00');
  const now = new Date();
  const lagDays = Math.floor((now - endDate.getTime()) / 864e5);
  const todayStr = now.toISOString().slice(0, 10);
  const tDayPending = lagDays === 1 && now.getDay() >= 1 && now.getDay() <= 5 && now.getHours() >= 16;
  if (tDayPending) {
    const b = $('#staleBanner');
    b.hidden = false;
    b.className = 'stale info';
    b.textContent = `${todayStr} 是交易日，但交易所/Tushare 的 T 日总份额通常晚间才发布；当前显示 ${D.meta.end} 收盘数据。21:30 终值会再更新一次。`;
  } else if (lagDays > 4 || latest.coverage < 95) {
    const b = $('#staleBanner');
    b.hidden = false;
    b.textContent = lagDays > 4
      ? `数据可能滞后：最新为 ${D.meta.end}（距今 ${lagDays} 天）。请检查自动更新任务是否运行。`
      : `数据覆盖率偏低：${pctTxt(latest.coverage)}，部分 ETF 份额尚未发布。`;
  }

  $('#version').textContent = D.meta.end.replace(/-/g, '') + '.' + D.meta.n_etf;

  /* ---------------- KPI ---------------- */
  const last5 = D.dates.slice(-5);
  const prev5 = D.dates.slice(-10, -5);
  const fmtRange = a => a.length ? a[0].slice(5) + '~' + a[a.length - 1].slice(5) : '—';
  const cur5Range = fmtRange(last5);
  const prev5Range = fmtRange(prev5);
  const kpis = [
    { label: '最新单日净申购', v: latest.flow, unit: '亿', sub: latest.date + ' 收盘 · 前一日 ' + num(D.total.flow[idx - 1], 1), tip: '最新一个已有份额数据的交易日；今天的数据要等收盘后发布。' },
    { label: '近 5 日累计', v: latest.flow5, unit: '亿', range: cur5Range,
      sub: '上期 ' + prev5Range + ' ' + num(D.total.flow5[idx - 5], 1),
      daily5: last5.map((d, j) => ({ d, v: D.total.flow[idx - 4 + j] })),
      daily5max: Math.max(1, ...last5.map((d, j) => Math.abs(D.total.flow[idx - 4 + j] || 0))),
      tip: '近5日=最近5个交易日（' + cur5Range + '）合计；下方为逐日净申购，条形长度按5日内最大值等比；上期=前一个5日窗口（' + prev5Range + '），不是上一日。' },
    { label: '近 20 日累计', v: latest.flow20, unit: '亿', sub: '分位 ' + pctTxt(latest.rank20), accent: true, tip: '最近 20 个交易日净申购之和，是主信号。' },
    { label: '今年以来', v: latest.ytd, unit: '亿', sub: latest.date.slice(0,4) + ' 年初至今', tip: '当年 1 月 1 日至最新交易日的累计净申购。' },
  ];

  $('#kpis').innerHTML = kpis.map((k, i) => `
    <div class="kpi ${k.accent ? 'accent' : ''}" title="${k.tip || ''}">
      <label>${k.label}${k.range ? `<span class="krange">${k.range}</span>` : ''}<span class="mono" style="color:var(--faint)">${k.unit}</span></label>
      <div class="v ${cls(k.v)}">${num(k.v, 1)}</div>
      <div class="sub"><span>${k.sub}</span></div>
      ${k.daily5 ? `<div class="k5" aria-label="近5个交易日逐日净申购">${k.daily5.map((x, j) => {
        const v = x.v;
        const txt = (v === null || v === undefined || Number.isNaN(v))
          ? '—'
          : (v < 0 ? '−' : '') + Math.abs(v).toFixed(1);
        const tip = `${x.d} 净申购 ${num(v, 1)} 亿`;
        const w = Math.round(Math.abs(v || 0) / k.daily5max * 100);
        return `<div class="k5c${j === 4 ? ' last' : ''}" title="${tip}"><i>${x.d.slice(5)}</i><b class="${cls(v)}">${txt}</b><span class="k5b"><s class="${cls(v)}" style="--w:${w}%"></s></span></div>`;
      }).join('')}</div>` : ''}
    </div>`).join('');

  const charts = [];
  function mk(el, opt) {
    const c = echarts.init(el, null, { renderer: 'canvas' });
    c.setOption(opt);
    charts.push(c);
    return c;
  }


  /* ---------------- verification ---------------- */
  (function renderVerify() {
    const rOk = latest.rank20 !== null && latest.rank20 !== undefined && latest.rank20 >= 90;
    const bOk = (latest.breadth || 0) >= 4;
    const tOk = latest.etf_turnover_ratio !== null && latest.etf_turnover_ratio !== undefined && latest.etf_turnover_ratio >= 1.2;
    const checks = [
      {
        card: '#vcard1', status: '#v1status', value: '#v1', detail: '#v1s', ok: rOk,
        v: pctTxt(latest.rank20) + ' 分位',
        d: '近 20 日 ' + num(latest.flow20, 0) + ' 亿'
      },
      {
        card: '#vcard2', status: '#v2status', value: '#v2', detail: '#v2s', ok: bOk,
        v: (latest.breadth ?? '—') + '/' + (latest.n_families ?? 6) + ' 宽基为正',
        d: (latest.top_family || '—') + ' 贡献 ' + pctTxt(latest.top_family_share)
      },
      {
        card: '#vcard3', status: '#v3status', value: '#v3', detail: '#v3s', ok: tOk,
        v: (latest.etf_turnover_ratio === null || latest.etf_turnover_ratio === undefined) ? '—' : latest.etf_turnover_ratio.toFixed(2) + '×',
        d: 'ETF 成交 ' + num(latest.etf_turnover, 0, false) + ' 亿（' + latest.date.slice(5) + ' 收盘）· 溢价 ' + num(latest.premium, 0) + ' bp'
      }
    ];
    let passed = 0;
    checks.forEach(c => {
      if (c.ok) passed++;
      const card = $(c.card);
      card.classList.add(c.ok ? 'pass' : 'fail');
      $(c.status).textContent = c.ok ? '通过' : '未通过';
      $(c.value).textContent = c.v;
      $(c.detail).textContent = c.d;
    });
    const label = passed === 3 ? '较高' : passed === 2 ? '中等' : '偏低';
    const summary = $('#verifySummary');
    summary.textContent = `${passed}/3 通过 · 信号置信度${label}`;
    summary.style.color = passed === 3 ? GREEN : passed === 2 ? GOLD : RED;
  })();

  /* ---------------- shared ---------------- */
  const state = { range: '2021', events: true, tier: 'core', sort: { key: 'flow20', dir: -1 } };

  function startIndex(range) {
    if (range === 'all') return 0;
    let iso;
    if (range === '2021') {
      iso = '2021-01-01';
    } else {
      const last = new Date(D.dates[idx] + 'T00:00:00');
      last.setFullYear(last.getFullYear() - (range === '1y' ? 1 : 3));
      iso = last.toISOString().slice(0, 10);
    }
    const i = D.dates.findIndex(d => d >= iso);
    return i < 0 ? 0 : i;
  }
  const slice = (arr, i0) => arr.slice(i0);
  const xInt = n => window.innerWidth < 720 ? Math.max(1, Math.floor(n / 4)) : 'auto';

  const mainChart = mk($('#chartMain'), {});
  function renderMain() {
    const wide = window.innerWidth >= 720;
    const i0 = startIndex(state.range);
    const dates = slice(D.dates, i0);
    const flow = slice(D.total.flow, i0);
    const cum = slice(D.total.cum, i0);
    const evts = state.events ? D.meta.events.filter(e => e.date >= dates[0] && e.date <= dates[dates.length - 1]) : [];

    const markLine = {
      silent: true, symbol: 'none', animation: false,
      lineStyle: { color: 'rgba(168,137,10,.45)', type: 'dashed', width: 1 },
      data: evts.map(e => ({
        xAxis: e.date,
        label: {
          show: wide && e.level === 1, formatter: e.short, rotate: 90,
          position: 'insideEndTop', distance: 5, color: '#a8890a', fontSize: 10
        }
      }))
    };
    const showLowSignal = dates[0] < D.meta.signal_start;
    const markArea = showLowSignal ? {
      silent: true,
      itemStyle: { color: 'rgba(0,6,40,.045)' },
      label: {
        show: wide, position: 'insideTopLeft', color: '#a0a7b4', fontSize: 10,
        formatter: 'ETF 代理低信号期', padding: [4, 6]
      },
      data: [[{ xAxis: dates[0] }, { xAxis: D.meta.signal_start }]]
    } : undefined;

    mainChart.setOption({
      animation: false,
      color: [BLUE, GOLD],
      grid: [
        { left: 58, right: 66, top: 46, height: 226 },
        { left: 58, right: 66, top: 322, height: 106 }
      ],
      legend: {
        top: 2, left: 0, itemWidth: 12, itemHeight: 8, itemGap: 18, textStyle: chartText,
        data: ['累计净申购', '20日滚动净申购']
      },
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'cross', label: { backgroundColor: '#000066' } },
        backgroundColor: 'rgba(0,0,45,.95)', borderWidth: 0, padding: [10, 14],
        textStyle: { color: '#e9ecf5', fontSize: 12 },
        formatter: p => {
          const d = p[0].axisValue;
          const i = D.dates.indexOf(d);
          const hs = D.hs300[i], hsPrev = D.hs300[i - 1];
          const vals = { '累计净申购': D.total.cum[i], '20日滚动净申购': D.total.flow20[i], '单日净申购': D.total.flow[i] };
          const chg = (hs && hsPrev) ? ((hs / hsPrev - 1) * 100).toFixed(2) : null;
          const out = ['累计净申购', '20日滚动净申购', '单日净申购'].map(name => {
            const v = vals[name];
            if (v === null || v === undefined) return '';
            return `<div style="display:flex;justify-content:space-between;gap:26px;line-height:1.9">
              <span style="color:#b9bfd6">${name}</span>
              <b style="font-family:monospace;color:${v >= 0 ? '#ffb9c2' : '#8fe0c5'}">${num(v, 1)} 亿</b></div>`;
          }).join('');
          return `<div style="font-family:monospace;color:#b9bfd6;margin-bottom:6px">${d}</div>` + out +
            (chg ? `<div style="margin-top:6px;color:#98a0b4;font-size:11px">沪深300 ${chg > 0 ? '+' : ''}${chg}%</div>` : '');
        }
      },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      xAxis: [
        {
          type: 'category', data: dates, boundaryGap: true, gridIndex: 0,
          axisLine: { lineStyle: { color: '#e2e4e9' } }, axisTick: { show: false },
          axisLabel: { show: false }
        },
        {
          type: 'category', data: dates, boundaryGap: true, gridIndex: 1,
          axisLine: { lineStyle: { color: '#e2e4e9' } }, axisTick: { show: false },
          axisLabel: { ...chartText, formatter: v => v.slice(2, 7).replace('-', '/'), hideOverlap: true, interval: xInt(dates.length) }
        }
      ],
      yAxis: [
        {
          type: 'value', gridIndex: 0,
          name: '亿元', nameLocation: 'end', nameGap: 8,
          nameTextStyle: { ...chartText, fontSize: 10, color: '#a0a7b4', align: 'right' },
          splitLine: { lineStyle: { color: '#eef0f3' } }, axisLabel: chartText,
          axisLine: { show: false }, axisTick: { show: false }
        },
        {
          type: 'value', gridIndex: 1,
          name: '亿元', nameLocation: 'end', nameGap: 8,
          nameTextStyle: { ...chartText, fontSize: 10, color: '#a0a7b4', align: 'right' },
          splitLine: { lineStyle: { color: '#eef0f3' } }, axisLabel: chartText,
          axisLine: { show: false }, axisTick: { show: false }
        }
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
        ...(wide ? [{ type: 'slider', xAxisIndex: [0, 1], height: 14, bottom: 10, borderColor: 'transparent', backgroundColor: '#f5f6fa', fillerColor: 'rgba(0,0,102,.10)', handleStyle: { color: '#9aa3c4' }, textStyle: { color: '#a0a7b4', fontSize: 10 } }] : [])
      ],
      series: [
        {
          name: '累计净申购', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: cum, symbol: 'none',
          lineStyle: { width: 2.2, color: BLUE }, z: 5,
          areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(0,0,102,.16)' }, { offset: 1, color: 'rgba(0,0,102,0)' }]) },
          endLabel: {
            show: true, distance: 6, fontSize: 11, fontWeight: 600,
            color: BLUE, fontFamily: 'monospace',
            formatter: p => num(p.value, 0, false)
          },
          markLine: {
            silent: true, symbol: 'none', animation: false,
            lineStyle: { color: 'rgba(0,6,40,.10)', width: 1 },
            data: [{ yAxis: 0, label: { show: false } }, ...markLine.data]
          },
          markArea
        },
        {
          name: '20日滚动净申购', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: slice(D.total.flow20, i0), barMaxWidth: 5,
          itemStyle: { color: p => p.value >= 0 ? 'rgba(199,0,11,.82)' : 'rgba(13,122,99,.78)', borderRadius: p => p.value >= 0 ? [2, 2, 0, 0] : [0, 0, 2, 2] },
          markLine: {
            silent: true, symbol: 'none', animation: false,
            lineStyle: { color: 'rgba(0,6,40,.10)', width: 1 },
            label: { show: false },
            data: [{ yAxis: 0 }]
          }
        }
      ]
    }, true);
  }
  renderMain();

  /* ---------------- family cumulative ---------------- */
  /* ---------------- Plotly 小图共用（区间控件统一） ---------------- */
  const PL = {};                       // key -> { gd, keys }
  const PL_BTNS = [
    { count: 1, label: '1M', step: 'month', stepmode: 'backward' },
    { count: 3, label: '3M', step: 'month', stepmode: 'backward' },
    { count: 6, label: '6M', step: 'month', stepmode: 'backward' },
    { count: 1, label: '1Y', step: 'year', stepmode: 'backward' },
    { count: 3, label: '3Y', step: 'year', stepmode: 'backward' },
    { step: 'all', label: '全部' }
  ];
  const PL_HOVER = {
    bgcolor: 'rgba(0,0,45,.95)', bordercolor: 'rgba(0,0,45,.95)',
    font: { color: '#e9ecf5', size: 11, family: 'monospace' }
  };

  function plWin() {
    const i0 = startIndex(state.range);
    return [D.dates[i0], D.dates[idx]];
  }

  /* 四张小图共用一套骨架：顶部区间按钮 + 图例，底部滑块，尺寸完全一致 */
  function plLayout(opts) {
    const o = opts || {};
    const win = plWin();
    return {
      margin: { l: 52, r: 16, t: 78, b: 56 },
      paper_bgcolor: '#fff', plot_bgcolor: '#fff',
      font: { family: '-apple-system,PingFang SC,sans-serif', size: 11, color: '#69707f' },
      hovermode: 'x unified',
      hoverlabel: PL_HOVER,
      showlegend: true,
      legend: {
        orientation: 'h', x: 0, y: 1.02, xanchor: 'left', yanchor: 'bottom',
        font: { size: 11 }, itemwidth: 30, bgcolor: 'rgba(0,0,0,0)'
      },
      xaxis: {
        type: 'date', range: o.range || win,
        showgrid: true, gridcolor: '#f5f6f9', zeroline: false,
        tickfont: { size: 10 },
        rangeslider: {
          visible: true, thickness: 0.075,
          bgcolor: '#f7f8fb', bordercolor: '#e6e8ef', borderwidth: 1
        },
        rangeselector: {
          buttons: PL_BTNS, x: 1, xanchor: 'right', y: 1.16, yanchor: 'bottom',
          bgcolor: '#fff', activecolor: '#e8eaf6',
          bordercolor: '#dfe2ea', borderwidth: 1,
          font: { size: 10, color: '#5a6072' }
        }
      },
      yaxis: {
        gridcolor: '#eef0f3', zeroline: false,
        tickfont: { size: 10 }, automargin: true,
        title: o.yTitle ? { text: o.yTitle, font: { size: 10, color: '#a0a7b4' }, standoff: 4 } : undefined
      }
    };
  }

  function plPlot(key, el, traces, layout, config) {
    if (!el || !window.Plotly) return;
    const gd = el;
    PL[key] = { gd: gd, keys: ['xaxis'].concat(el.dataset.x2 ? ['xaxis2'] : []) };
    return Plotly.newPlot(gd, traces, layout, Object.assign({
      responsive: true, displayModeBar: false, displaylogo: false, doubleClick: 'reset'
    }, config || {}));
  }

  /* 页面顶部 1年/3年/2021起/全部 按钮 → 统一改四张图的区间 */
  function plSetRange() {
    const win = plWin();
    Object.keys(PL).forEach(k => {
      const c = PL[k];
      const upd = {};
      c.keys.forEach(x => { upd[x + '.range'] = win; });
      Plotly.relayout(c.gd, upd);
    });
  }

  /* ---------------- 分指数 ---------------- */
  function plotFamily() {
    const names = D.meta.families;
    const traces = names.map(f => ({
      x: D.dates, y: D.family_cum[f], type: 'scatter', mode: 'lines', name: f,
      line: { width: 1.7, color: FAM_COLORS[f] || '#8f97b8' },
      hovertemplate: f + ' %{y:,.1f} 亿<extra></extra>'
    }));
    plPlot('family', $('#chartFamily'), traces, plLayout({ yTitle: '亿元' }));
  }

  /* ---------------- 核心池份额 vs 沪深300 ---------------- */
  function plotShares() {
    const lay = plLayout({ yTitle: '亿份' });
    lay.yaxis2 = {
      overlaying: 'y', side: 'right', showgrid: false, zeroline: false,
      tickfont: { size: 10 }, automargin: true,
      title: { text: '沪深300', font: { size: 10, color: '#a0a7b4' }, standoff: 4 }
    };
    // 右轴放沪深300，但顶部按钮与图例已经占位，所以只让左轴 automargin
    lay.yaxis.automargin = true;
    const traces = [
      {
        x: D.dates, y: D.total.shares, type: 'scatter', mode: 'lines', name: '核心池份额',
        line: { width: 2, color: BLUE }, hovertemplate: '核心池份额 %{y:,.0f} 亿份<extra></extra>'
      },
      {
        x: D.dates, y: D.hs300, type: 'scatter', mode: 'lines', name: '沪深300', yaxis: 'y2',
        line: { width: 1.4, color: '#8f97b8', dash: 'dash' },
        hovertemplate: '沪深300 %{y:,.0f}<extra></extra>'
      }
    ];
    plPlot('shares', $('#chartShares'), traces, lay);
  }

  /* ---------------- 托底强度 ---------------- */
  function rollSum(arr, n) {
    const out = new Array(arr.length).fill(null);
    let s = 0, c = 0;
    for (let i = 0; i < arr.length; i++) {
      const v = arr[i];
      if (v !== null && v !== undefined) { s += v; c++; }
      if (i >= n) { const o = arr[i - n]; if (o !== null && o !== undefined) { s -= o; c--; } }
      if (i >= n - 1 && c >= n * .6) out[i] = s;
    }
    return out;
  }
  const flow20sum = rollSum(D.total.flow, 20);
  const turn20sum = rollSum(D.turnover, 20);
  const ratio20 = flow20sum.map((v, i) => (v === null || !turn20sum[i]) ? null : +(v / turn20sum[i] * 1000).toFixed(2));

  function plotRatio() {
    const traces = [{
      x: D.dates, y: ratio20, type: 'scatter', mode: 'lines', name: '20日净流入 / 20日成交额',
      line: { width: 1.8, color: BLUE },
      fill: 'tozeroy', fillcolor: 'rgba(0,0,102,.10)',
      hovertemplate: '%{y:,.2f} ‰<extra></extra>'
    }];
    plPlot('ratio', $('#chartRatio'), traces, plLayout({ yTitle: '‰' }));
  }

  plotFamily();
  plotShares();
  plotRatio();


  /* ---------------- 两市成交额（Plotly：自带区间选择） ---------------- */
  const turnEl = $('#chartTurnover');
  // 20 日均值在整条序列上算，不受可视区间影响
  const ma20 = D.turnover.map((v, i) => {
    if (i < 19) return null;
    let s = 0;
    for (let j = i - 19; j <= i; j++) s += D.turnover[j];
    return +(s / 20).toFixed(1);
  });
  // 环比跟上一个交易日比，首日没有前一天
  const dTurn = D.turnover.map((v, i) => i === 0 ? null : +(v - D.turnover[i - 1]).toFixed(0));

  (function fillTurnNote() {
    const el = $('#turnNow');
    if (!el) return;
    const last = D.turnover[idx], d = dTurn[idx];
    el.textContent = `最新 ${num(last, 0, false)} 亿`
      + (d == null ? '' : `，环比 ${num(d, 0)} 亿（${num(d / (last - d) * 100, 1)}%）`);
  })();

  let turnGd = null;
  function turnWin() {
    const i0 = startIndex(state.range);
    return [D.dates[i0], D.dates[idx]];
  }

  function drawTurnover() {
    if (!turnEl) return;
    if (!window.Plotly) {
      turnEl.innerHTML = '<p style="padding:24px;color:#878e9d;font-size:12px">'
        + 'Plotly 未加载，成交额图不可用。请确认 assets/plotly-basic.min.js 已部署。</p>';
      return;
    }
    const dAbs = Math.max(1, ...dTurn.filter(v => v !== null).map(Math.abs));
    const barColor = dTurn.map(v => v === null ? 'rgba(0,0,0,0)'
      : v >= 0 ? 'rgba(199,0,11,.42)' : 'rgba(13,122,99,.42)');
    const [from, to] = turnWin();

    const layout = {
      margin: { l: 52, r: 16, t: 78, b: 56 },
      paper_bgcolor: '#fff', plot_bgcolor: '#fff',
      font: { family: '-apple-system,PingFang SC,sans-serif', size: 11, color: '#69707f' },
      // 图例放面板底部的 chart-note 里：顶部要留给区间按钮，窄屏会撞
      showlegend: false,
      bargap: 0.15,
      hovermode: 'x unified',
      hoverlabel: { bgcolor: 'rgba(0,0,45,.95)', bordercolor: 'rgba(0,0,45,.95)',
        font: { color: '#e9ecf5', size: 11, family: 'monospace' } },
      // 上格：成交额；下格：日环比
      xaxis: {
        type: 'date', domain: [0, 1], anchor: 'y',
        range: [from, to],
        showticklabels: false, showgrid: false, zeroline: false,
        rangeslider: { visible: false },
        rangeselector: {
          buttons: [
            { count: 1, label: '1M', step: 'month', stepmode: 'backward' },
            { count: 3, label: '3M', step: 'month', stepmode: 'backward' },
            { count: 6, label: '6M', step: 'month', stepmode: 'backward' },
            { count: 1, label: '1Y', step: 'year', stepmode: 'backward' },
            { count: 3, label: '3Y', step: 'year', stepmode: 'backward' },
            { step: 'all', label: '全部' }
          ],
          x: 1, xanchor: 'right', y: 1.16, yanchor: 'bottom',
          bgcolor: '#fff', activecolor: '#e8eaf6',
          bordercolor: '#dfe2ea', borderwidth: 1,
          font: { size: 10, color: '#5a6072' }
        }
      },
      yaxis: {
        domain: [0.46, 1], anchor: 'x', automargin: true,
        gridcolor: '#eef0f3', zeroline: false,
        title: { text: '亿', font: { size: 10, color: '#a0a7b4' }, standoff: 4 },
        tickformat: ',.0f', tickfont: { size: 10 }
      },
      xaxis2: {
        type: 'date', domain: [0, 1], anchor: 'y2',
        range: [from, to],
        showgrid: false, zeroline: false,
        tickfont: { size: 10 },
        rangeslider: {
          visible: true, thickness: 0.075,
          bgcolor: '#f7f8fb', bordercolor: '#e6e8ef', borderwidth: 1
        }
      },
      yaxis2: {
        domain: [0.14, 0.38], anchor: 'x2', automargin: true,
        gridcolor: '#f3f4f7', zeroline: true, zerolinecolor: '#d7dae3', zerolinewidth: 1,
        range: [-dAbs, dAbs], tickformat: '~s', nticks: 3, tickfont: { size: 10 },
        title: { text: 'Δ亿', font: { size: 10, color: '#a0a7b4' }, standoff: 4 }
      }
    };

    turnEl.dataset.x2 = '1';
    plPlot('turnover', turnEl, [
      {
        x: D.dates, y: dTurn, type: 'bar', name: '日环比', xaxis: 'x2', yaxis: 'y2',
        marker: { color: barColor, line: { width: 0 } },
        hovertemplate: '日环比 %{y:,} 亿<extra></extra>'
      },
      {
        x: D.dates, y: D.turnover, type: 'scatter', mode: 'lines', name: '两市成交额',
        xaxis: 'x', yaxis: 'y',
        line: { color: BLUE, width: 1.6, shape: 'linear' },
        fill: 'tozeroy', fillcolor: 'rgba(0,0,102,.07)',
        hovertemplate: '成交额 %{y:,} 亿<extra></extra>'
      },
      {
        x: D.dates, y: ma20, type: 'scatter', mode: 'lines', name: '20日均值',
        xaxis: 'x', yaxis: 'y',
        line: { color: '#8f97b8', width: 1.2, dash: 'dash' },
        hovertemplate: '20日均值 %{y:,} 亿<extra></extra>'
      }
    ], layout).then(() => {
      turnGd = turnEl;
      // xaxis 与 xaxis2 是两套坐标系，Plotly 不会自动联动，这里显式双向镜像
      bindTurnAxes();
    });
  }

  function bindTurnAxes() {
    if (!turnGd || turnGd.dataset.turnBound) return;
    turnGd.dataset.turnBound = '1';
    let busy = false;
    turnGd.on('plotly_relayout', ev => {
      if (busy) return;
      const pick = k => {
        if (ev[k + '.range']) return ev[k + '.range'];
        if (ev[k + '.range[0]'] !== undefined && ev[k + '.range[1]'] !== undefined) {
          return [ev[k + '.range[0]'], ev[k + '.range[1]']];
        }
        if (ev[k + '.autorange']) return 'auto';
        return null;
      };
      const from = pick('xaxis') !== null ? 'xaxis' : (pick('xaxis2') !== null ? 'xaxis2' : null);
      if (!from) return;
      const val = pick(from);
      const other = from === 'xaxis' ? 'xaxis2' : 'xaxis';
      if (val === 'auto') return;   // 双击复位：两侧各自回到全量，无需镜像
      busy = true;
      const upd = {};
      upd[other + '.range'] = val;
      Plotly.relayout(turnGd, upd).then(() => { busy = false; }).catch(() => { busy = false; });
    });
  }


  drawTurnover();


  /* ---------------- table ---------------- */
  const maxAbs20 = Math.max(...D.etfs.map(x => Math.abs(x.flow20 || 0)), 1);
  function rows() {
    let xs = D.etfs.slice();
    if (state.tier === 'core') xs = xs.filter(x => x.tier === 1);
    else xs = xs.filter(x => x.tier === 1 || x.tier === 2);
    const k = state.sort.key, dir = state.sort.dir;
    xs.sort((a, b) => {
      let va = a[k], vb = b[k];
      if (k === 'code' || k === 'name' || k === 'family') return String(va).localeCompare(String(vb), 'zh') * dir;
      return ((va ?? -1e18) - (vb ?? -1e18)) * dir;
    });
    return xs;
  }
  /** 昨日分时迷你图：纯 SVG，避免为 10 行各建一个 ECharts 实例 */
  function spark(x) {
    const it = x.intraday;
    if (!it || !it.c || it.c.length < 10) return '<span class="spark-na">—</span>';

    // 前一交易日收盘价作基准（用于着色与虚线）
    const i = D.dates.indexOf(it.date);
    const prev = i > 0 ? D.etfs.find(e => e.code === x.code)?.close?.[i - 1] : null;
    const base = (prev && prev > 0) ? prev : it.o;

    const W = 68, H = 24, PAD = 1.5;
    const lo = Math.min(...it.c, base), hi = Math.max(...it.c, base);
    const span = (hi - lo) || 1;
    const y = v => +(H - PAD - (v - lo) / span * (H - PAD * 2)).toFixed(2);
    const n = it.c.length;
    const pts = it.c.map((v, k) => `${(k / (n - 1) * W).toFixed(2)},${y(v)}`).join(' ');

    const last = it.c[n - 1];
    const up = last >= base;
    const stroke = up ? RED : GREEN;
    const chg = base ? (last / base - 1) * 100 : 0;
    const yb = y(base);

    const tip = `${it.date} 分时 · 开 ${it.o} 高 ${it.h} 低 ${it.l} 收 ${last}`
      + (base ? ` · 较前收 ${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%` : '');

    return `<span class="spark" title="${tip}">`
      + `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" preserveAspectRatio="none" aria-hidden="true">`
      + `<line x1="0" y1="${yb}" x2="${W}" y2="${yb}" stroke="#c9cee0" stroke-width="0.6" stroke-dasharray="2 2"/>`
      + `<polyline points="${pts}" fill="none" stroke="${stroke}" stroke-width="1.15" stroke-linejoin="round" stroke-linecap="round"/>`
      + `<circle cx="${W}" cy="${y(last)}" r="1.5" fill="${stroke}"/>`
      + `</svg></span>`;
  }

  function renderTable() {
    $('#tblDate').textContent = latest.date;
    // 列名直接标出该分时对应的交易日（即净申购统计日）
    const dShort = latest.date.slice(5);
    const th = $('#sparkTh');
    if (th) {
      th.textContent = dShort + ' 分时';
      th.title = `${latest.date} 日内 5 分钟走势`;
    }
    const dd = $('#sparkDescDate');
    if (dd) dd.textContent = latest.date;
    const xs = rows();
    const tb = $('#etfTable tbody');
    tb.innerHTML = xs.map(x => {
      const w = Math.min(100, Math.abs(x.flow20 || 0) / maxAbs20 * 100);
      const tag = x.tier === 1 ? '<span class="tag t1">核心</span>' : '<span class="tag t2">扩展</span>';
      return `<tr>
        <td><span class="code">${x.code}</span></td>
        <td><span class="etf-name">${x.name}</span>${tag}</td>
        <td class="col-spark">${spark(x)}</td>
        <td class="num">${num(x.shares_last, 1, false)}</td>
        <td class="num ${cls(x.flow_last)}">${num(x.flow_last, 2)}</td>
        <td class="num ${cls(x.flow5)}">${num(x.flow5, 1)}</td>
        <td class="num ${cls(x.flow20)} bar-cell ${x.flow20 < 0 ? 'neg' : ''}" style="--w:${w}%"><span>${num(x.flow20, 1)}</span></td>
        <td class="num ${cls(x.flow_ytd)}">${num(x.flow_ytd, 1)}</td>
        <td class="num">${num(x.aum_last, 0, false)}</td>
        <td class="num">${(x.weight === null || x.weight === undefined) ? '—' : x.weight.toFixed(1) + '%'}</td>
        <td class="num ${x.f20pct > 0 ? 'pos' : x.f20pct < 0 ? 'neg' : ''}">${(x.f20pct === null || x.f20pct === undefined) ? '—' : num(x.f20pct, 1) + '%'}</td>
        <td class="num ${cls(x.premium_last)}">${num(x.premium_last, 0)}</td>
      </tr>`;
    }).join('');
  }
  renderTable();

  $$('#etfTable th').forEach(th => {
    if (!th.dataset.k) return;              // 「昨日分时」等纯展示列不参与排序
    th.addEventListener('click', () => {
      const k = th.dataset.k;
      state.sort = { key: k, dir: state.sort.key === k ? -state.sort.dir : -1 };
      renderTable();
    });
  });
  $$('#tierSeg button').forEach(b => b.addEventListener('click', () => {
    $$('#tierSeg button').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); state.tier = b.dataset.t; renderTable();
  }));

  /* ---------------- controls ---------------- */
  $$('#rangeSeg button').forEach(b => b.addEventListener('click', () => {
    $$('#rangeSeg button').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); state.range = b.dataset.r;
    renderMain(); plSetRange();
  }));
  $('#evtToggle').addEventListener('change', e => { state.events = e.target.checked; renderMain(); });

  /* ---------------- events ---------------- */
  $('#evtList').innerHTML = D.meta.events.map(e =>
    `<div class="evt"><time>${e.date}</time><div><b>${e.short}</b><span>${e.title}</span></div></div>`).join('');

  const news = D.meta.news || [];
  const TAG_CLS = { '汇金': 't0', '证金': 't0', '国家队': 't0', '大额机构': 't0', '平准': 't0', '国新诚通': 't0',
                    '核心池': 't1', '宽基ETF': 't1', 'ETF成交': 't1', '申赎': 't1',
                    '货币宽松': 't2', '监管': 't2' };
  $('#newsList').innerHTML = news.length
    ? news.map(n => {
        const tags = (n.tags || []).slice(0, 2);
        const chips = tags.length
          ? tags.map(t => `<em class="ntag ${TAG_CLS[t] || 't2'}">${t}</em>`).join('')
          : '<em class="ntag t2">要闻</em>';
        const body = n.url
          ? `<a href="${n.url}" target="_blank" rel="noopener">${n.title}</a>`
          : `<span>${n.title}</span>`;
        return `<div class="evt"><time>${n.date}</time><div>${chips}${body}</div></div>`;
      }).join('')
    : '<div class="evt"><div></div><div><span>暂无符合条件的新闻线索</span></div></div>';

  const ver = D.meta.verification || {};
  if (ver.status && ver.status !== 'skipped') {
    const dev = ver.max_dev_pct == null ? '—' : ver.max_dev_pct + '%';
    $('#dataline').textContent = `Tushare（交叉校验 ${ver.status}，最大偏差 ${dev}）`;
  }

  /* 上次更新失败提示：数据仍是旧的，明确告诉读者 */
  const st = window.UPDATE_STATUS;
  if (st && st.status && st.status !== 'ok') {
    const el = $('#updWarn');
    const when = st.at || '—';
    const until = st.date || D.meta.end || '—';
    const reason = st.detail ? `（${String(st.detail).split('\n')[0].slice(0, 60)}）` : '';
    el.hidden = false;
    el.textContent = `⚠ 上次更新失败（${when}）${reason}，信息更新到 ${until}`;
    const hero = document.querySelector('.hero-meta');
    if (hero) {
      const badge = document.createElement('span');
      badge.className = 'pill stale-badge';
      badge.textContent = `⚠ 数据可能未更新 · 截至 ${until}`;
      hero.appendChild(badge);
    }
  }

  /* ---------------- resize ---------------- */
  let rt;
  window.addEventListener('resize', () => {
    clearTimeout(rt);
    rt = setTimeout(() => { charts.forEach(c => c.resize()); renderMain(); }, 150);
  });
})();
