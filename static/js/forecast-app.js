/**
 * Financial Forecast — progress projection and category bar chart.
 */
(function (global) {
  'use strict';

  let chart = null;
  let summary = null;
  let horizon = 'full_job';

  function projectId() {
    if (global.CASEPM_ACTIVE_PROJECT_ID) return global.CASEPM_ACTIVE_PROJECT_ID;
    if (typeof CasePMWorkflow !== 'undefined' && CasePMWorkflow.projectId) return CasePMWorkflow.projectId();
    const raw = localStorage.getItem('casepm_current_project_id');
    return raw ? parseInt(raw, 10) : null;
  }

  function fmt(n) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(n || 0);
  }

  async function loadSummary() {
    const pid = projectId();
    if (!pid) throw new Error('Select a project first.');
    const res = await fetch(`/api/forecast/summary?project_id=${pid}`, { credentials: 'same-origin' });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Failed to load forecast');
    summary = json;
    return json;
  }

  function renderKpis(data) {
    const map = {
      kpiRevised: data.revised_budget,
      kpiActual: data.actual_cost,
      kpiVariance: data.variance,
      kpiPaid: data.paid_out,
      kpiPending: data.pending_changes,
      kpiCommitted: data.committed,
      kpiPct: `${data.percent_complete || 0}%`,
    };
    Object.keys(map).forEach(id => {
      const el = document.getElementById(id);
      if (!el) return;
      el.textContent = id === 'kpiPct' ? map[id] : fmt(map[id]);
      if (id === 'kpiVariance') {
        el.classList.toggle('text-emerald-400', (data.variance || 0) >= 0);
        el.classList.toggle('text-red-400', (data.variance || 0) < 0);
      }
    });
  }

  function renderProjection(data) {
    const proj = (data.projections || {})[horizon] || {};
    const el = document.getElementById('projectionPanel');
    if (!el) return;
    const label = {
      week: 'Next 1 Week',
      two_weeks: 'Next 2 Weeks',
      four_weeks: 'Next 4 Weeks',
      full_job: 'Through Expected Completion',
    }[horizon] || 'Projection';
    el.innerHTML = `
      <div class="text-sm text-zinc-400 mb-1">${label}</div>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div><div class="text-xs text-zinc-500">Projected Cost</div><div class="text-xl font-semibold text-sky-400">${fmt(proj.projected_cost)}</div></div>
        <div><div class="text-xs text-zinc-500">Projected Variance</div><div class="text-xl font-semibold ${(proj.projected_variance || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}">${fmt(proj.projected_variance)}</div></div>
        <div><div class="text-xs text-zinc-500">Est. % Complete</div><div class="text-xl font-semibold text-violet-400">${proj.projected_percent_complete || 0}%</div></div>
      </div>
      <div class="text-xs text-zinc-500 mt-3">Based on ${fmt(data.burn_rate_weekly || 0)}/week burn rate · ${data.days_remaining || 0} days remaining on schedule</div>`;
  }

  function renderChart(data) {
    const canvas = document.getElementById('forecastChart');
    if (!canvas || typeof Chart === 'undefined') return;
    const cats = data.categories || [];
    const labels = cats.map(c => c.label);
    const amounts = cats.map(c => Math.abs(c.amount || 0));
    const colors = cats.map(c => c.color);

    if (chart) chart.destroy();
    chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [{
          label: 'Amount',
          data: amounts,
          backgroundColor: colors.map(c => c + 'cc'),
          borderColor: colors,
          borderWidth: 1,
          borderRadius: 10,
          borderSkipped: false,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label(ctx) {
                const raw = cats[ctx.dataIndex];
                const sign = raw && raw.key === 'variance' && (raw.amount || 0) < 0 ? '-' : '';
                return `${ctx.label}: ${sign}${fmt(ctx.parsed.y)}`;
              },
            },
          },
        },
        scales: {
          x: {
            grid: { color: 'rgba(63,63,70,0.4)' },
            ticks: { color: '#a1a1aa', maxRotation: 45, minRotation: 0, font: { size: 11 } },
          },
          y: {
            grid: { color: 'rgba(63,63,70,0.4)' },
            ticks: {
              color: '#a1a1aa',
              callback: v => '$' + Number(v).toLocaleString(),
            },
          },
        },
        animation: { duration: 800, easing: 'easeOutQuart' },
      },
    });
  }

  function setHorizon(h) {
    horizon = h;
    document.querySelectorAll('[data-forecast-horizon]').forEach(btn => {
      btn.classList.toggle('bg-emerald-600', btn.dataset.forecastHorizon === h);
      btn.classList.toggle('text-white', btn.dataset.forecastHorizon === h);
      btn.classList.toggle('bg-zinc-800', btn.dataset.forecastHorizon !== h);
    });
    if (summary) renderProjection(summary);
  }

  async function init() {
    if (!projectId()) {
      alert('Select a project to view financial forecast.');
      return;
    }
    if (typeof CasePMAccountingReconcile !== 'undefined') {
      await CasePMAccountingReconcile.initAndReconcile().catch(() => {});
    } else if (typeof CasePMBudgetSync !== 'undefined') {
      await CasePMBudgetSync.init().catch(() => {});
    }
    try {
      const data = await loadSummary();
      renderKpis(data);
      renderProjection(data);
      renderChart(data);
    } catch (err) {
      alert(err.message);
    }
    document.querySelectorAll('[data-forecast-horizon]').forEach(btn => {
      btn.addEventListener('click', () => setHorizon(btn.dataset.forecastHorizon));
    });
    setHorizon(horizon);
  }

  global.CasePMForecast = { init, loadSummary, setHorizon };
  document.addEventListener('DOMContentLoaded', init);
})(window);
