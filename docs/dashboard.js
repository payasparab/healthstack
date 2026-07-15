// healthstack dashboard renderer

const COLORS = {
  text: '#e8e6e0',
  muted: '#8a8880',
  dim: '#5c5a54',
  ember: '#e2604d',
  sage: '#7db988',
  gold: '#d4b46a',
  rule: '#2a2a2e',
};

async function main() {
  const res = await fetch('data.json', { cache: 'no-store' });
  if (!res.ok) {
    document.body.innerHTML = '<pre style="color:#e2604d;padding:40px">Could not load data.json. Has the ingest run yet?</pre>';
    return;
  }
  const data = await res.json();

  renderHeader(data);
  renderRail(data);
  renderWeekStats(data);
  renderProgress(data);
  renderNutrition(data);
  renderWeightChart(data);
  renderStreaks(data);
  renderLifts(data);
  renderRuns(data);
  renderBriefing(data);
}

function fmt(n, d = 1) {
  if (n === null || n === undefined) return '—';
  return typeof n === 'number' ? n.toFixed(d).replace(/\.0$/, '') : n;
}

function fmtDate(iso) {
  if (!iso) return '—';
  const [y, m, d] = iso.split('-');
  return `${m}/${d}`;
}

function renderHeader(data) {
  document.getElementById('generated').textContent = `updated ${data.generated_at}`;
  const wk = data.this_week?.week_start;
  document.getElementById('week-start').textContent = wk ? fmtDate(wk) : '—';
}

function renderRail(data) {
  const rail = document.getElementById('rail');
  const status = document.getElementById('rail-status');
  const schedule = data.weight_schedule || [];
  const daily = data.daily || [];

  // Build actual-weight-by-week map (Sunday-anchored)
  // For each schedule row, find the closest actual weight within that week (Sun-Sat)
  const actualByWeek = {};
  for (const s of schedule) {
    const start = new Date(s.week_start + 'T00:00:00');
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    const inWeek = daily.filter(d => {
      if (!d.weight_lb) return false;
      const dd = new Date(d.date + 'T00:00:00');
      return dd >= start && dd <= end;
    });
    if (inWeek.length) {
      // last recorded weight in the week (or closest to Sunday)
      actualByWeek[s.week_start] = inWeek[inWeek.length - 1].weight_lb;
    }
  }

  rail.innerHTML = schedule.map(s => {
    const actual = actualByWeek[s.week_start];
    const today = new Date();
    const wkStart = new Date(s.week_start + 'T00:00:00');
    const wkEnd = new Date(wkStart);
    wkEnd.setDate(wkEnd.getDate() + 6);
    const isCurrent = today >= wkStart && today <= wkEnd;

    let actualClass = '';
    if (actual !== undefined) {
      // "behind" means weight is HIGHER than target for that week
      actualClass = actual > s.target_lb + 0.5 ? 'behind' : 'on-pace';
    }

    return `
      <div class="rail-week ${isCurrent ? 'current' : ''}">
        <div class="rail-week-date">${fmtDate(s.week_start)}</div>
        <div class="rail-week-target">${fmt(s.target_lb)}</div>
        <div class="rail-week-actual ${actualClass}">${actual !== undefined ? fmt(actual) : '·'}</div>
      </div>
    `;
  }).join('');

  // Overall status message
  const currentWeek = schedule.find(s => {
    const start = new Date(s.week_start + 'T00:00:00');
    const end = new Date(start);
    end.setDate(end.getDate() + 6);
    const t = new Date();
    return t >= start && t <= end;
  });
  if (currentWeek && data.current_weight) {
    const delta = data.current_weight - currentWeek.target_lb;
    if (delta > 0.5) {
      status.textContent = `${fmt(delta)} lb behind`;
      status.className = 'rail-status behind';
    } else if (delta < -0.5) {
      status.textContent = `${fmt(-delta)} lb ahead`;
      status.className = 'rail-status ahead';
    } else {
      status.textContent = 'on pace';
      status.className = 'rail-status on-pace';
    }
  }
}

function renderWeekStats(data) {
  const cw = data.current_weight;
  const tw = data.this_week_target?.target_lb;

  document.getElementById('current-weight').textContent = fmt(cw);
  document.getElementById('target-weight').textContent = fmt(tw);

  const deltaEl = document.getElementById('delta');
  const deltaUnitEl = document.getElementById('delta-unit');
  if (cw !== null && tw !== null && tw !== undefined) {
    const delta = cw - tw;
    deltaEl.textContent = (delta > 0 ? '+' : '') + fmt(delta);
    deltaEl.classList.remove('ember', 'sage');
    if (delta > 0.5) deltaEl.classList.add('ember');
    else if (delta < -0.5) deltaEl.classList.add('sage');
    deltaUnitEl.textContent = delta > 0.5 ? 'behind' : delta < -0.5 ? 'ahead' : 'lb';
  }
}

function renderProgress(data) {
  const wk = data.this_week || {};
  const t = data.targets || {};

  const items = [
    { id: 'exercise', current: wk.exercise_days || 0, target: 6 },
    { id: 'runs', current: wk.run_count || 0, target: 3 },
    { id: 'mobility', current: wk.mobility_min || 0, target: 30 },
    { id: 'hydration', current: wk.hydration_days || 0, target: 5 },
    { id: 'meditation', current: wk.meditation_days || 0, target: 5 },
  ];

  for (const item of items) {
    const bar = document.getElementById('bar-' + item.id);
    const count = document.getElementById('count-' + item.id);
    const pct = Math.min(100, (item.current / item.target) * 100);
    bar.style.width = pct + '%';
    if (item.current >= item.target) bar.classList.add('complete');
    count.textContent = `${fmt(item.current, 0)}/${item.target}`;
  }
}

function renderNutrition(data) {
  // Find yesterday's row (most recent day with any nutrition data)
  const daily = (data.daily || []).slice().reverse();
  const yday = daily.find(d => d.calories != null || d.protein_g != null || d.carbs_g != null);

  const calories = yday?.calories;
  const protein = yday?.protein_g;
  const carbs = yday?.carbs_g;

  const CAL_CAP = 2500;
  const PROTEIN_MIN = 220;
  const CARB_CAP = 50;

  function paint(id, current, target, kind) {
    // kind: 'cap' = under target is good, over is bad
    //       'min' = at/over target is good, under is muted
    const valueEl = document.getElementById(`nut-${id}`);
    const barEl = document.getElementById(`nut-${id}-bar`);
    if (current == null) {
      valueEl.textContent = '—';
      barEl.style.width = '0%';
      return;
    }
    valueEl.textContent = fmt(current, id === 'calories' ? 0 : 1);
    const pct = Math.min(100, (current / target) * 100);
    barEl.style.width = pct + '%';
    valueEl.classList.remove('over', 'on', 'under');
    barEl.classList.remove('over', 'on');
    if (kind === 'cap') {
      if (current > target) { valueEl.classList.add('over'); barEl.classList.add('over'); }
      else { valueEl.classList.add('on'); barEl.classList.add('on'); }
    } else {
      if (current >= target) { valueEl.classList.add('on'); barEl.classList.add('on'); }
      else { valueEl.classList.add('under'); }
    }
  }

  paint('calories', calories, CAL_CAP, 'cap');
  paint('protein', protein, PROTEIN_MIN, 'min');
  paint('carbs', carbs, CARB_CAP, 'cap');
}

function renderWeightChart(data) {
  const ctx = document.getElementById('weight-chart');
  if (!ctx) return;
  const daily = (data.daily || []).filter(d => d.weight_lb !== null);
  const schedule = data.weight_schedule || [];

  // Build a unified set of dates (sorted) so both series align on category axis
  const allDates = new Set();
  daily.forEach(d => allDates.add(d.date));
  schedule.forEach(s => allDates.add(s.week_start));
  const labels = Array.from(allDates).sort();

  const dailyMap = Object.fromEntries(daily.map(d => [d.date, d.weight_lb]));
  const scheduleMap = Object.fromEntries(schedule.map(s => [s.week_start, s.target_lb]));

  const actualData = labels.map(d => dailyMap[d] ?? null);
  const scheduledData = labels.map(d => scheduleMap[d] ?? null);

  Chart.defaults.font.family = 'JetBrains Mono, monospace';
  Chart.defaults.color = COLORS.muted;
  Chart.defaults.borderColor = COLORS.rule;

  new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [
        {
          label: 'Actual',
          data: actualData,
          borderColor: COLORS.text,
          backgroundColor: 'transparent',
          borderWidth: 2,
          pointRadius: 3,
          pointBackgroundColor: COLORS.text,
          tension: 0.2,
          spanGaps: true,
        },
        {
          label: 'Scheduled',
          data: scheduledData,
          borderColor: COLORS.dim,
          backgroundColor: 'transparent',
          borderWidth: 1.5,
          borderDash: [4, 4],
          pointRadius: 0,
          tension: 0,
          spanGaps: true,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: COLORS.muted, font: { size: 11 } } },
      },
      scales: {
        x: {
          grid: { color: COLORS.rule, drawTicks: false },
          ticks: {
            color: COLORS.muted,
            font: { size: 10 },
            maxTicksLimit: 8,
            callback: function(val) {
              const label = this.getLabelForValue(val);
              return label ? label.slice(5) : '';  // MM-DD
            },
          },
        },
        y: {
          grid: { color: COLORS.rule },
          ticks: { color: COLORS.muted, font: { size: 10 } },
        },
      },
    },
  });
}

function renderStreaks(data) {
  const s = data.streaks || {};
  document.getElementById('streak-hydration').textContent = s.hydration ?? 0;
  document.getElementById('streak-meditation').textContent = s.meditation ?? 0;
  document.getElementById('streak-steps').textContent = s.steps ?? 0;
}

function renderLifts(data) {
  const grid = document.getElementById('lifts-grid');
  const prs = data.lift_prs || [];
  const target_lifts = data.target_lifts || {};

  grid.innerHTML = prs.map(pr => {
    const history = target_lifts[pr.exercise] || [];
    const current = pr.current_best_lb;
    const target = pr.target_lb;
    const pct = current ? Math.min(100, (current / target) * 100) : 0;

    let sparklineHTML = '';
    if (history.length >= 2) {
      const weights = history.map(h => h.weight_lb);
      const min = Math.min(...weights);
      const max = Math.max(...weights);
      const range = max - min || 1;
      const w = 100 / (history.length - 1);
      const points = history.map((h, i) => {
        const x = i * w;
        const y = 100 - ((h.weight_lb - min) / range) * 100;
        return `${x},${y}`;
      }).join(' ');
      sparklineHTML = `
        <svg class="lift-sparkline" viewBox="0 0 100 100" preserveAspectRatio="none">
          <polyline points="${points}" fill="none" stroke="${COLORS.text}" stroke-width="1.5" vector-effect="non-scaling-stroke"/>
        </svg>
      `;
    } else if (history.length === 1) {
      sparklineHTML = `<div class="lift-empty">1 session — need more data for trend</div>`;
    } else {
      sparklineHTML = `<div class="lift-empty">no sessions yet</div>`;
    }

    return `
      <div class="lift-card">
        <div class="lift-name">${pr.exercise}</div>
        <div class="lift-current-row">
          <span class="lift-current">${current ? fmt(current, 0) : '—'}</span>
          <span class="lift-current-unit">lb</span>
        </div>
        <div class="lift-target">target ${fmt(target, 0)} lb</div>
        <div class="lift-progress-bar">
          <div class="lift-progress-fill" style="width:${pct}%"></div>
        </div>
        ${sparklineHTML}
      </div>
    `;
  }).join('');
}

function renderRuns(data) {
  const tbody = document.querySelector('#runs-table tbody');
  const runs = data.recent_runs || [];
  if (runs.length === 0) {
    tbody.innerHTML = '<tr><td colspan="4" style="color:#5c5a54;padding:20px 0">no runs yet</td></tr>';
    return;
  }
  tbody.innerHTML = runs.slice().reverse().map(r => {
    const pace = r.pace_min_per_km;
    let paceStr = '—';
    if (pace) {
      const min = Math.floor(pace);
      const sec = Math.round((pace - min) * 60);
      paceStr = `${min}:${String(sec).padStart(2, '0')}/km`;
    }
    return `
      <tr>
        <td>${r.date}</td>
        <td class="num">${r.distance_km ? fmt(r.distance_km) + ' km' : '—'}</td>
        <td class="num">${r.duration_min ? fmt(r.duration_min, 0) + ' min' : '—'}</td>
        <td class="num">${paceStr}</td>
      </tr>
    `;
  }).join('');
}

function renderBriefing(data) {
  const b = data.last_briefing;
  const dateEl = document.getElementById('briefing-date');
  const contentEl = document.getElementById('briefing-content');
  if (b) {
    dateEl.textContent = `— ${b.date} (${b.kind})`;
    contentEl.textContent = b.content;
  } else {
    dateEl.textContent = '— none yet';
    contentEl.textContent = 'No briefings have been generated yet.';
  }
}

main().catch(err => {
  console.error(err);
  document.body.insertAdjacentHTML('afterbegin',
    `<pre style="color:#e2604d;padding:20px 40px;background:#17171a;margin:20px">Error: ${err.message}</pre>`);
});
