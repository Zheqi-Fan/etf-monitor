/* 国家队 ETF 资金流监测 · 前端逻辑 */
(function () {
  const D = window.DASHBOARD_DATA;
  if (!D) { document.body.innerHTML = '<div style="padding:60px;font:16px sans-serif">数据未生成，请先运行 python3 fetch_data.py</div>'; return; }

  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => Array.from(el.querySelectorAll(s));
  const idx = D.dates.length - 1;
  const latest = D.latest;

  const RED = '#c0362c', GREEN = '#0f7a5a', BLUE = '#1f4e79', GOLD = '#b07a24';
  const FAM_COLORS = {
    '沪深300': '#c0362c', '上证50': '#d9863f', '中证500': '#2f6f9f',
    '中证1000': '#6b4f9e', '创业板': '#0f7a5a', '科创50': '#b07a24'
  };

  function num(v, d = 1, sign = true) {
    if (v === null || v === undefined || Number.isNaN(v)) return '—';
    const s = Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: d, maximumFractionDigits: d });
    if (sign) return (v > 0 ? '+' : v < 0 ? '−' : '') + s;
    return (v < 0 ? '−' : '') + s;
  }
  const cls = v => v > 0 ? 'pos' : v < 0 ? 'neg' : '';
  const pctTxt = v => v === null || v === undefined ? '—' : v.toFixed(1) + '%';
  const chartText = { color: '#6b7a8c', fontSize: 11, fontFamily: '-apple-system,PingFang SC,sans-serif' };

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
  $('#sig1').textContent = num(latest.flow, 1);
  $('#sig1Date').textContent = latest.date.slice(5);
  $('#sigCum').textContent = num(latest.cum, 0);
  $('#sigAum').textContent = num(latest.aum, 0);
  $('#sigZ').textContent = '20日 z ' + num(latest.z20, 2);
  $('#sigRank').textContent = '历史分位 ' + pctTxt(latest.rank20);

  const badge = $('#signalBadge');
  const z = latest.z20 ?? 0;
  badge.textContent = z >= 1.5 ? '● 强势流入' : z >= 0.5 ? '● 温和流入' : z <= -1.5 ? '● 明显流出' : z <= -0.5 ? '● 偏流出' : '● 中性';
  badge.className = 'badge ' + (z >= 1.5 ? 'hot' : z >= 0.5 ? 'warm' : z <= -0.5 ? 'cold' : '');

  $('#tZ').textContent = num(latest.z20, 2);
  $('#tRank').textContent = pctTxt(latest.rank20);
  $('#tStreak').textContent = (latest.streak > 0 ? '连流入 ' : latest.streak < 0 ? '连流出 ' : '') + Math.abs(latest.streak) + ' 天';
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
    { label: '最新单日净申购', v: latest.flow, unit: '亿', sub: latest.date + ' 收盘 · 前一日 ' + num(D.total.flow[idx - 1], 1), spark: D.total.flow.slice(-60), tip: '最新一个已有份额数据的交易日；今天的数据要等收盘后发布。' },
    { label: '近 5 日累计', v: latest.flow5, unit: '亿', range: cur5Range,
      sub: '上期 ' + prev5Range + ' ' + num(D.total.flow5[idx - 5], 1),
      daily5: last5.map((d, j) => ({ d, v: D.total.flow[idx - 4 + j] })),
      daily5max: Math.max(1, ...last5.map((d, j) => Math.abs(D.total.flow[idx - 4 + j] || 0))),
      spark: D.total.flow5.slice(-60),
      tip: '近5日=最近5个交易日（' + cur5Range + '）合计；下方为逐日净申购，条形长度按5日内最大值等比；上期=前一个5日窗口（' + prev5Range + '），不是上一日。' },
    { label: '近 20 日累计', v: latest.flow20, unit: '亿', sub: 'z ' + num(latest.z20, 1) + ' · 分位 ' + pctTxt(latest.rank20), spark: D.total.flow20.slice(-60), accent: true, tip: '最近 20 个交易日净申购之和，是主信号。' },
    { label: '今年以来', v: latest.ytd, unit: '亿', sub: latest.date.slice(0,4) + ' 年初至今', spark: D.total.cum.slice(-60), tip: '当年 1 月 1 日至最新交易日的累计净申购。' },
    { label: '核心池总规模', v: latest.aum, unit: '亿', sub: '合计 ' + num(latest.shares, 0, false) + ' 亿份', spark: D.total.aum.slice(-60), aum: true, tip: '10 只核心宽基 ETF 的份额 × 净值之和。' },
  ];

  $('#kpis').innerHTML = kpis.map((k, i) => `
    <div class="kpi ${k.accent ? 'accent' : ''}" title="${k.tip || ''}">
      <label>${k.label}${k.range ? `<span class="krange">${k.range}</span>` : ''}<span class="mono" style="color:var(--faint)">${k.unit}</span></label>
      <div class="v ${cls(k.v)}">${num(k.v, k.aum ? 0 : 1)}</div>
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
      <div class="spark" id="spark${i}"></div>
    </div>`).join('');

  const charts = [];
  function mk(el, opt) {
    const c = echarts.init(el, null, { renderer: 'canvas' });
    c.setOption(opt);
    charts.push(c);
    return c;
  }

  kpis.forEach((k, i) => {
    const color = k.aum ? BLUE : (k.spark[k.spark.length - 1] >= 0 ? RED : GREEN);
    mk($('#spark' + i), {
      animation: false,
      grid: { left: 0, right: 0, top: 4, bottom: 0 },
      xAxis: { type: 'category', show: false, data: D.dates.slice(-k.spark.length), boundaryGap: false },
      yAxis: { type: 'value', show: false, scale: true },
      series: [{
        type: 'line', data: k.spark, symbol: 'none', smooth: .25,
        lineStyle: { width: 1.6, color },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: color + '33' }, { offset: 1, color: color + '00' }])
        }
      }],
      tooltip: { show: false }
    });
  });


  /* ---------------- verification ---------------- */
  (function renderVerify() {
    const zOk = latest.z20 !== null && latest.z20 !== undefined && latest.z20 >= 1.0;
    const bOk = (latest.breadth || 0) >= 4;
    const tOk = latest.etf_turnover_ratio !== null && latest.etf_turnover_ratio !== undefined && latest.etf_turnover_ratio >= 1.2;
    const checks = [
      {
        card: '#vcard1', status: '#v1status', value: '#v1', detail: '#v1s', ok: zOk,
        v: 'z ' + num(latest.z20, 2),
        d: pctTxt(latest.rank20) + ' 分位 · 20日 ' + num(latest.flow20, 0) + ' 亿'
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
    summary.style.color = passed === 3 ? '#0f7a5a' : passed === 2 ? '#b07a24' : '#b23a30';
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
      lineStyle: { color: 'rgba(176,122,36,.42)', type: 'dashed', width: 1 },
      data: evts.map(e => ({
        xAxis: e.date,
        label: {
          show: wide && e.level === 1, formatter: e.short, rotate: 90,
          position: 'insideEndTop', distance: 5, color: '#9a6a35', fontSize: 10
        }
      }))
    };
    const showLowSignal = dates[0] < D.meta.signal_start;
    const markArea = showLowSignal ? {
      silent: true,
      itemStyle: { color: 'rgba(13,27,42,.045)' },
      label: {
        show: wide, position: 'insideTopLeft', color: '#9aa7b4', fontSize: 10,
        formatter: 'ETF 代理低信号期', padding: [4, 6]
      },
      data: [[{ xAxis: dates[0] }, { xAxis: D.meta.signal_start }]]
    } : undefined;

    mainChart.setOption({
      animation: false,
      color: [BLUE, RED],
      grid: [
        { left: 58, right: 66, top: 46, height: 226 },
        { left: 58, right: 66, top: 322, height: 106 }
      ],
      legend: {
        top: 2, left: 0, itemWidth: 12, itemHeight: 8, itemGap: 18, textStyle: chartText,
        data: ['累计净申购', '20日滚动净申购']
      },
      tooltip: {
        trigger: 'axis', axisPointer: { type: 'cross', label: { backgroundColor: '#25384d' } },
        backgroundColor: 'rgba(10,26,43,.95)', borderWidth: 0, padding: [10, 14],
        textStyle: { color: '#eaf0f6', fontSize: 12 },
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
              <span style="color:#b9c6d3">${name}</span>
              <b style="font-family:monospace;color:${v >= 0 ? '#ff9a8f' : '#6fd3b4'}">${num(v, 1)} 亿</b></div>`;
          }).join('');
          return `<div style="font-family:monospace;color:#98a4b3;margin-bottom:6px">${d}</div>` + out +
            (chg ? `<div style="margin-top:6px;color:#8fa0b2;font-size:11px">沪深300 ${chg > 0 ? '+' : ''}${chg}%</div>` : '');
        }
      },
      axisPointer: { link: [{ xAxisIndex: 'all' }] },
      xAxis: [
        {
          type: 'category', data: dates, boundaryGap: true, gridIndex: 0,
          axisLine: { lineStyle: { color: '#dfe5ec' } }, axisTick: { show: false },
          axisLabel: { show: false }
        },
        {
          type: 'category', data: dates, boundaryGap: true, gridIndex: 1,
          axisLine: { lineStyle: { color: '#dfe5ec' } }, axisTick: { show: false },
          axisLabel: { ...chartText, formatter: v => v.slice(2, 7).replace('-', '/'), hideOverlap: true, interval: xInt(dates.length) }
        }
      ],
      yAxis: [
        {
          type: 'value', gridIndex: 0,
          name: '亿元', nameLocation: 'end', nameGap: 8,
          nameTextStyle: { ...chartText, fontSize: 10, color: '#a3b0be', align: 'right' },
          splitLine: { lineStyle: { color: '#eef1f5' } }, axisLabel: chartText,
          axisLine: { show: false }, axisTick: { show: false }
        },
        {
          type: 'value', gridIndex: 1,
          name: '亿元', nameLocation: 'end', nameGap: 8,
          nameTextStyle: { ...chartText, fontSize: 10, color: '#a3b0be', align: 'right' },
          splitLine: { lineStyle: { color: '#eef1f5' } }, axisLabel: chartText,
          axisLine: { show: false }, axisTick: { show: false }
        }
      ],
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1], start: 0, end: 100 },
        ...(wide ? [{ type: 'slider', xAxisIndex: [0, 1], height: 14, bottom: 10, borderColor: 'transparent', backgroundColor: '#f4f6f8', fillerColor: 'rgba(31,78,121,.10)', handleStyle: { color: '#9fb0c1' }, textStyle: { color: '#98a4b3', fontSize: 10 } }] : [])
      ],
      series: [
        {
          name: '累计净申购', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: cum, symbol: 'none',
          lineStyle: { width: 2.2, color: BLUE }, z: 5,
          areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(31,78,121,.16)' }, { offset: 1, color: 'rgba(31,78,121,0)' }]) },
          endLabel: {
            show: true, distance: 6, fontSize: 11, fontWeight: 600,
            color: BLUE, fontFamily: 'monospace',
            formatter: p => num(p.value, 0, false)
          },
          markLine: {
            silent: true, symbol: 'none', animation: false,
            lineStyle: { color: 'rgba(13,27,42,.10)', width: 1 },
            data: [{ yAxis: 0, label: { show: false } }, ...markLine.data]
          },
          markArea
        },
        {
          name: '20日滚动净申购', type: 'bar', xAxisIndex: 1, yAxisIndex: 1, data: slice(D.total.flow20, i0), barMaxWidth: 5,
          itemStyle: { color: p => p.value >= 0 ? 'rgba(192,54,44,.82)' : 'rgba(15,122,90,.78)', borderRadius: p => p.value >= 0 ? [2, 2, 0, 0] : [0, 0, 2, 2] },
          markLine: {
            silent: true, symbol: 'none', animation: false,
            lineStyle: { color: 'rgba(13,27,42,.10)', width: 1 },
            label: { show: false },
            data: [{ yAxis: 0 }]
          }
        }
      ]
    }, true);
  }
  renderMain();

  /* ---------------- family cumulative ---------------- */
  const famChart = mk($('#chartFamily'), {});
  function roll(arr, n) {
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
  function renderFamily() {
    const i0 = startIndex(state.range);
    const dates = slice(D.dates, i0);
    const names = D.meta.families;
    const series = names.map(f => ({
      name: f, type: 'line', data: slice(D.family_cum[f], i0),
      symbol: 'none', lineStyle: { width: 1.8, color: FAM_COLORS[f] }, emphasis: { focus: 'series' }
    }));
    famChart.setOption({
      animation: false,
      grid: { left: 54, right: 18, top: 42, bottom: 26 },
      legend: { top: 0, left: 0, itemWidth: 12, itemHeight: 8, itemGap: 10, textStyle: chartText, data: names },
      tooltip: {
        trigger: 'axis', backgroundColor: 'rgba(10,26,43,.95)', borderWidth: 0,
        textStyle: { color: '#eaf0f6', fontSize: 12 },
        formatter: p => `<div style="font-family:monospace;color:#98a4b3;margin-bottom:5px">${p[0].axisValue}</div>` +
          p.filter(x => x.value !== null).sort((a, b) => b.value - a.value).map(x =>
            `<div style="display:flex;justify-content:space-between;gap:22px;line-height:1.85">
             <span style="color:#b9c6d3">${x.seriesName}</span>
             <b style="font-family:monospace;color:${x.value >= 0 ? '#ff9a8f' : '#6fd3b4'}">${num(x.value, 1)}</b></div>`).join('')
      },
      xAxis: { type: 'category', data: dates, boundaryGap: false, axisTick: { show: false }, axisLine: { lineStyle: { color: '#dfe5ec' } }, axisLabel: { ...chartText, formatter: v => v.slice(2, 7).replace('-', '/'), hideOverlap: true, interval: xInt(dates.length) } },
      yAxis: { type: 'value', name: '', nameTextStyle: chartText, splitLine: { lineStyle: { color: '#eef1f5' } }, axisLabel: chartText, axisLine: { show: false }, axisTick: { show: false } },
      series
    }, true);
  }
  renderFamily();

  /* ---------------- AUM vs HS300 ---------------- */
  const aumChart = mk($('#chartAum'), {});
  function renderAum() {
    const i0 = startIndex(state.range);
    const dates = slice(D.dates, i0);
    const aum = slice(D.total.aum, i0);
    const hs = slice(D.hs300, i0);
    aumChart.setOption({
      animation: false,
      grid: { left: 50, right: 52, top: 36, bottom: 26 },
      legend: { top: 0, left: 0, itemWidth: 12, itemHeight: 8, itemGap: 14, textStyle: chartText, data: ['核心池规模', '沪深300'] },
      tooltip: {
        trigger: 'axis', backgroundColor: 'rgba(10,26,43,.95)', borderWidth: 0, textStyle: { color: '#eaf0f6', fontSize: 12 },
        formatter: p => `<div style="font-family:monospace;color:#98a4b3;margin-bottom:5px">${p[0].axisValue}</div>` +
          `<div style="display:flex;gap:24px;line-height:1.8"><span>核心池规模</span><b style="font-family:monospace">${p[0].value ? p[0].value.toFixed(0) : '—'} 亿</b></div>` +
          `<div style="display:flex;gap:24px;line-height:1.8"><span>沪深300</span><b style="font-family:monospace">${p[1].value ? p[1].value.toFixed(0) : '—'}</b></div>`
      },
      xAxis: { type: 'category', data: dates, boundaryGap: false, axisTick: { show: false }, axisLine: { lineStyle: { color: '#dfe5ec' } }, axisLabel: { ...chartText, formatter: v => v.slice(2, 7).replace('-', '/'), hideOverlap: true, interval: xInt(dates.length) } },
      yAxis: [
        { type: 'value', name: '', nameTextStyle: chartText, splitLine: { lineStyle: { color: '#eef1f5' } }, axisLabel: chartText, scale: true, axisLine: { show: false }, axisTick: { show: false } },
        { type: 'value', name: '', nameTextStyle: chartText, splitLine: { show: false }, axisLabel: chartText, scale: true, axisLine: { show: false }, axisTick: { show: false } }
      ],
      series: [
        {
          name: '核心池规模', type: 'line', data: aum, symbol: 'none', lineStyle: { width: 2.2, color: 'rgba(192,54,44,.9)' },
          markLine: state.range === 'all' ? {
            silent: true, symbol: 'none', lineStyle: { color: 'rgba(176,122,36,.5)', type: 'dashed' },
            label: { formatter: '汇金买入 ETF', color: '#9a6a35', fontSize: 10, position: 'insideEndTop' },
            data: [{ xAxis: D.meta.signal_start }]
          } : undefined
        },
        { name: '沪深300', type: 'line', yAxisIndex: 1, data: hs, symbol: 'none', lineStyle: { width: 1.4, color: '#7d93a8', type: 'dashed' } }
      ]
    }, true);
  }
  renderAum();

  /* ---------------- year ---------------- */
  const yearChart = mk($('#chartYear'), {});
  yearChart.setOption({
    animation: false,
    grid: { left: 48, right: 14, top: 28, bottom: 24 },
    tooltip: { trigger: 'axis', backgroundColor: 'rgba(10,26,43,.95)', borderWidth: 0, textStyle: { color: '#eaf0f6' }, formatter: p => `${p[0].axisValue} 年<br/>净流入 <b style="font-family:monospace">${num(p[0].value, 1)} 亿</b>` },
    xAxis: { type: 'category', data: D.yearly.map(y => y.year + ''), axisTick: { show: false }, axisLine: { lineStyle: { color: '#dfe5ec' } }, axisLabel: chartText },
    yAxis: { type: 'value', name: '', nameTextStyle: chartText, splitLine: { lineStyle: { color: '#eef1f5' } }, axisLabel: chartText, axisLine: { show: false }, axisTick: { show: false } },
    series: [{
      type: 'bar', barMaxWidth: 34,
      data: D.yearly.map(y => ({ value: y.flow, itemStyle: { color: y.flow >= 0 ? 'rgba(192,54,44,.8)' : 'rgba(15,122,90,.75)', borderRadius: y.flow >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4] } })),
      label: { show: true, position: 'top', formatter: p => num(p.value, 0), color: '#6b7a8c', fontSize: 10, fontFamily: 'monospace' }
    }]
  });

  /* ---------------- ratio ---------------- */
  const ratioChart = mk($('#chartRatio'), {});
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
  ratioChart.setOption({
    animation: false,
    grid: { left: 50, right: 16, top: 28, bottom: 24 },
    tooltip: {
      trigger: 'axis', backgroundColor: 'rgba(10,26,43,.95)', borderWidth: 0, textStyle: { color: '#eaf0f6', fontSize: 12 },
      formatter: p => `<div style="font-family:monospace;color:#98a4b3;margin-bottom:5px">${p[0].axisValue}</div>` +
        p.map(x => `<div style="display:flex;justify-content:space-between;gap:22px"><span>${x.seriesName}</span><b style="font-family:monospace">${x.value === null ? '—' : num(x.value, 2)} ‰</b></div>`).join('')
    },
    xAxis: { type: 'category', data: D.dates, boundaryGap: false, axisTick: { show: false }, axisLine: { lineStyle: { color: '#dfe5ec' } }, axisLabel: { ...chartText, formatter: v => v.slice(2, 7).replace('-', '/'), hideOverlap: true, interval: xInt(D.dates.length) } },
    yAxis: { type: 'value', name: '', nameTextStyle: chartText, splitLine: { lineStyle: { color: '#eef1f5' } }, axisLabel: chartText, axisLine: { show: false }, axisTick: { show: false } },
    series: [
      {
        name: '20日净流入 / 20日累计成交额', type: 'line', data: ratio20, symbol: 'none',
        lineStyle: { width: 1.8, color: BLUE },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: 'rgba(31,78,121,.18)' }, { offset: 1, color: 'rgba(31,78,121,0)' }]) },
        markLine: { silent: true, symbol: 'none', lineStyle: { color: 'rgba(13,27,42,.18)' }, label: { show: false }, data: [{ yAxis: 0 }] }
      }
    ]
  });

  /* ---------------- table ---------------- */
  const maxAbs20 = Math.max(...D.etfs.map(x => Math.abs(x.flow20 || 0)), 1);
  function rows() {
    let xs = D.etfs.slice();
    if (state.tier === 'core') xs = xs.filter(x => x.tier === 1);
    else xs = xs.filter(x => x.tier === 1 || x.tier === 2);
    const k = state.sort.key, dir = state.sort.dir;
    xs.sort((a, b) => {
      let va = a[k], vb = b[k];
      if (k === 'dshares_last') { va = (a.dshares || []).filter(v => v !== null).slice(-1)[0]; vb = (b.dshares || []).filter(v => v !== null).slice(-1)[0]; }
      if (k === 'code' || k === 'name' || k === 'family') return String(va).localeCompare(String(vb), 'zh') * dir;
      return ((va ?? -1e18) - (vb ?? -1e18)) * dir;
    });
    return xs;
  }
  function renderTable() {
    $('#tblDate').textContent = latest.date;
    const xs = rows();
    const tb = $('#etfTable tbody');
    tb.innerHTML = xs.map(x => {
      const dsh = (x.dshares || []).filter(v => v !== null).slice(-1)[0];
      const w = Math.min(100, Math.abs(x.flow20 || 0) / maxAbs20 * 100);
      const tag = x.tier === 1 ? '<span class="tag t1">核心</span>' : '<span class="tag t2">扩展</span>';
      return `<tr>
        <td><span class="code">${x.code}</span></td>
        <td><span class="etf-name">${x.name}</span>${tag}</td>
        <td>${x.family}</td>
        <td class="num">${num(x.shares_last, 1, false)}</td>
        <td class="num ${cls(dsh)}">${num(dsh, 2)}</td>
        <td class="num ${cls(x.flow_last)}">${num(x.flow_last, 2)}</td>
        <td class="num ${cls(x.flow5)}">${num(x.flow5, 1)}</td>
        <td class="num ${cls(x.flow20)} bar-cell ${x.flow20 < 0 ? 'neg' : ''}" style="--w:${w}%"><span>${num(x.flow20, 1)}</span></td>
        <td class="num ${cls(x.flow_ytd)}">${num(x.flow_ytd, 1)}</td>
        <td class="num">${num(x.aum_last, 0, false)}</td>
        <td class="num">${x.weight ? x.weight.toFixed(1) + '%' : '—'}</td>
        <td class="num ${x.z20 >= 1.5 ? 'pos' : x.z20 <= -1.5 ? 'neg' : ''}">${num(x.z20, 2)}</td>
        <td class="num ${x.premium_last > 0 ? 'pos' : 'neg'}">${num(x.premium_last, 0)}</td>
      </tr>`;
    }).join('');
  }
  renderTable();

  $$('#etfTable th').forEach(th => th.addEventListener('click', () => {
    const k = th.dataset.k;
    state.sort = { key: k, dir: state.sort.key === k ? -state.sort.dir : -1 };
    renderTable();
  }));
  $$('#tierSeg button').forEach(b => b.addEventListener('click', () => {
    $$('#tierSeg button').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); state.tier = b.dataset.t; renderTable();
  }));

  /* ---------------- controls ---------------- */
  $$('#rangeSeg button').forEach(b => b.addEventListener('click', () => {
    $$('#rangeSeg button').forEach(x => x.classList.remove('on'));
    b.classList.add('on'); state.range = b.dataset.r;
    renderMain(); renderFamily(); renderAum();
  }));
  $('#evtToggle').addEventListener('change', e => { state.events = e.target.checked; renderMain(); });

  /* ---------------- events ---------------- */
  $('#evtList').innerHTML = D.meta.events.map(e =>
    `<div class="evt"><time>${e.date}</time><div><b>${e.short}</b><span>${e.title}</span></div></div>`).join('');

  const news = D.meta.news || [];
  const TAG_CLS = { '汇金': 't0', '证金': 't0', '国家队': 't0', '平准': 't0', '国新诚通': 't0',
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
    rt = setTimeout(() => { charts.forEach(c => c.resize()); renderMain(); renderFamily(); renderAum(); }, 150);
  });
})();
