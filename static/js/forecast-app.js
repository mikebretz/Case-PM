/**
 * Financial Forecast — monthly progress report and escalating trend chart.
 * Styled to match Budget / Pay Apps module aesthetics.
 */
(function (global) {
  'use strict';

  let trendChart = null;
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

  function fmtDate(iso) {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch {
      return iso;
    }
  }

  function esc(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
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
      kpiContract: data.contract_amount,
      kpiOriginal: data.original_budget,
      kpiApprovedCo: data.approved_changes,
      kpiRevised: data.revised_budget,
      kpiActual: data.actual_cost,
      kpiFtc: data.forecast_to_complete,
      kpiEac: data.estimated_cost_at_completion,
      kpiPct: `${data.percent_complete || 0}%`,
    };
    Object.entries(map).forEach(([id, val]) => {
      const el = document.getElementById(id);
      if (!el) return;
      el.textContent = id === 'kpiPct' ? val : fmt(val);
    });
    const badge = document.getElementById('forecastAsOfBadge');
    if (badge && data.progress_report) {
      badge.textContent = fmtDate(data.progress_report.as_of_date);
    }
    const status = document.getElementById('forecastStatusText');
    if (status) {
      status.textContent = `Financial Forecast · Revised ${fmt(data.revised_budget)} · EAC ${fmt(data.estimated_cost_at_completion)} · Variance ${fmt(data.projected_over_under)}`;
    }
  }

  function renderProjection(data) {
    const proj = (data.projections || {})[horizon] || {};
    const el = document.getElementById('projectionPanel');
    if (!el) return;
    const label = {
      week: '1-week',
      two_weeks: '2-week',
      four_weeks: '4-week',
      full_job: 'full-job',
    }[horizon] || '';
    const varClass = (proj.projected_variance || 0) >= 0 ? 'text-emerald-400' : 'text-red-400';
    el.innerHTML = `
      <span class="text-zinc-500">${label} projection:</span>
      <span class="text-sky-400 font-mono ml-1">${fmt(proj.projected_cost)}</span>
      <span class="text-zinc-600 mx-1">·</span>
      <span class="text-zinc-500">variance</span>
      <span class="${varClass} font-mono ml-1">${fmt(proj.projected_variance)}</span>
      <span class="text-zinc-600 mx-1">·</span>
      <span class="text-zinc-500">${proj.projected_percent_complete || 0}% est.</span>`;
  }

  function renderProgressTable(data) {
    const tbody = document.getElementById('progressReportBody');
    if (!tbody) return;
    const rows = data.monthly_trends || (data.progress_report ? [data.progress_report] : []);
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="12" class="px-6 py-8 text-center text-zinc-500">No progress history yet.</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map((r, i) => {
      const isLatest = i === rows.length - 1;
      const rowClass = isLatest ? 'bg-zinc-800/40' : 'hover:bg-zinc-800/60';
      return `<tr class="${rowClass} transition-colors">
        <td class="px-4 py-2 font-medium text-white forecast-sticky-0">${esc(r.month)}</td>
        <td class="px-4 py-2 text-zinc-400 text-xs forecast-sticky-1">${fmtDate(r.as_of_date)}</td>
        <td class="px-4 py-2 text-right font-mono">${fmt(r.subtotal_budget)}</td>
        <td class="px-4 py-2 text-right font-mono text-orange-300">${fmt(r.subtotal_projected)}</td>
        <td class="px-4 py-2 text-right font-mono text-sky-400">${fmt(r.cost_to_date)}</td>
        <td class="px-4 py-2 text-right font-mono text-amber-400">${fmt(r.approved_changes)}</td>
        <td class="px-4 py-2 text-right font-mono text-emerald-400">${fmt(r.revised_contract)}</td>
        <td class="px-4 py-2 text-right font-mono text-indigo-400">${fmt(r.payments_received)}</td>
        <td class="px-4 py-2 text-right font-mono text-orange-400">${fmt(r.payments_pending)}</td>
        <td class="px-4 py-2 text-right font-mono font-semibold">${fmt(r.total_payments)}</td>
        <td class="px-4 py-2 text-center font-mono text-xs">${r.pct_complete || 0}%</td>
        <td class="px-6 py-2 text-xs text-zinc-500">${esc(r.notes || '')}</td>
      </tr>`;
    }).join('');
  }

  function renderTrendChart(data) {
    const canvas = document.getElementById('forecastTrendChart');
    if (!canvas || typeof Chart === 'undefined') return;
    const rows = data.monthly_trends || [];
    const labels = rows.map(r => r.month || fmtDate(r.as_of_date));

    const datasets = [
      { label: 'Cost to Date', key: 'cost_to_date', border: '#38bdf8', bg: 'rgba(56,189,248,0.12)' },
      { label: 'Approved Changes', key: 'approved_changes', border: '#fbbf24', bg: 'rgba(251,191,36,0.08)' },
      { label: 'Revised Contract', key: 'revised_contract', border: '#34d399', bg: 'rgba(52,211,153,0.06)' },
      { label: 'Payments Received', key: 'payments_received', border: '#818cf8', bg: 'rgba(129,140,248,0.06)' },
      { label: 'Payments Pending', key: 'payments_pending', border: '#fb923c', bg: 'rgba(251,146,60,0.05)' },
      { label: 'Total Payments', key: 'total_payments', border: '#a78bfa', bg: 'rgba(167,139,250,0.05)' },
    ].map(ds => ({
      label: ds.label,
      data: rows.map(r => r[ds.key] || 0),
      borderColor: ds.border,
      backgroundColor: ds.bg,
      borderWidth: 2.5,
      pointRadius: 4,
      pointHoverRadius: 6,
      tension: 0.35,
      fill: false,
    }));

    if (trendChart) trendChart.destroy();
    trendChart = new Chart(canvas, {
      type: 'line',
      data: { labels, datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: 'index', intersect: false },
        plugins: {
          legend: {
            display: true,
            position: 'bottom',
            labels: { color: '#a1a1aa', boxWidth: 12, padding: 16, font: { size: 11 } },
          },
          tooltip: {
            backgroundColor: '#18181b',
            borderColor: '#3f3f46',
            borderWidth: 1,
            titleColor: '#fff',
            bodyColor: '#d4d4d8',
            callbacks: {
              label(ctx) {
                return `${ctx.dataset.label}: ${fmt(ctx.parsed.y)}`;
              },
            },
          },
        },
        scales: {
          x: {
            grid: { color: 'rgba(63,63,70,0.35)' },
            ticks: { color: '#a1a1aa', font: { size: 11 } },
          },
          y: {
            grid: { color: 'rgba(63,63,70,0.35)' },
            ticks: {
              color: '#a1a1aa',
              callback: v => '$' + Number(v).toLocaleString(),
            },
          },
        },
        animation: { duration: 900, easing: 'easeOutQuart' },
      },
    });
  }

  function setHorizon(h) {
    horizon = h;
    document.querySelectorAll('[data-forecast-horizon]').forEach(btn => {
      const active = btn.dataset.forecastHorizon === h;
      btn.classList.toggle('bg-emerald-900/50', active);
      btn.classList.toggle('text-emerald-400', active);
      btn.classList.toggle('ring-1', active);
      btn.classList.toggle('ring-emerald-700', active);
      btn.classList.toggle('bg-zinc-800', !active);
      btn.classList.toggle('text-zinc-300', !active);
    });
    if (summary) renderProjection(summary);
  }

  async function refresh() {
    try {
      const data = await loadSummary();
      renderKpis(data);
      renderProjection(data);
      renderProgressTable(data);
      renderTrendChart(data);
    } catch (err) {
      alert(err.message);
    }
  }

  async function printReport() {
    if (!summary) {
      try { await refresh(); } catch (err) { alert(err.message); return; }
    }
    if (typeof global.CasePMPrint === 'undefined' || !global.CasePMPrint.printHtmlInIframe) {
      alert('Print module not loaded.');
      return;
    }

    const data = summary;
    const projectName = (document.getElementById('currentProjectName')?.textContent || '').trim() || 'Project';
    const rows = data.monthly_trends || (data.progress_report ? [data.progress_report] : []);
    const asOf = data.progress_report ? fmtDate(data.progress_report.as_of_date) : '—';
    const printedOn = new Date().toLocaleDateString(undefined, { month: 'numeric', day: 'numeric', year: 'numeric' });

    const tableRows = rows.length
      ? rows.map((r) => `<tr>
          <td class="left">${esc(r.month)}</td>
          <td class="left">${esc(fmtDate(r.as_of_date))}</td>
          <td class="mono">${esc(fmt(r.subtotal_budget))}</td>
          <td class="mono">${esc(fmt(r.subtotal_projected))}</td>
          <td class="mono">${esc(fmt(r.cost_to_date))}</td>
          <td class="mono">${esc(fmt(r.approved_changes))}</td>
          <td class="mono">${esc(fmt(r.revised_contract))}</td>
          <td class="mono">${esc(fmt(r.payments_received))}</td>
          <td class="mono">${esc(fmt(r.payments_pending))}</td>
          <td class="mono"><strong>${esc(fmt(r.total_payments))}</strong></td>
          <td class="center">${esc(r.pct_complete || 0)}%</td>
          <td class="left notes">${esc(r.notes || '')}</td>
        </tr>`).join('')
      : '<tr><td colspan="12" class="center" style="padding:16px;">No progress history yet.</td></tr>';

    let chartBlock = '';
    const canvas = document.getElementById('forecastTrendChart');
    if (canvas && trendChart && rows.length) {
      try {
        chartBlock = `
          <div class="section">
            <h2>Cost to Date vs Payments Over Time</h2>
            <p class="subtitle">Monthly escalation trend</p>
            <img src="${canvas.toDataURL('image/png')}" alt="Forecast trend chart" class="chart-img">
          </div>`;
      } catch (_) { /* ignore canvas export errors */ }
    }

    const printHTML = `<!DOCTYPE html><html><head><title>Financial Forecast — ${esc(projectName)}</title>
      <style>
        @page { size: letter landscape; margin: 0.3in 0.35in; }
        html, body { margin: 0; padding: 0; width: 100%; box-sizing: border-box; }
        body { font-family: Arial, Helvetica, sans-serif; font-size: 8pt; color: #111; padding: 10px 12px; }
        @media print { body { -webkit-print-color-adjust: exact; print-color-adjust: exact; } }
        .header { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #222; padding-bottom: 8px; margin-bottom: 12px; }
        .header h1 { font-size: 14pt; margin: 0 0 4px; }
        .header .meta { text-align: right; font-size: 8pt; line-height: 1.4; }
        .section h2 { font-size: 11pt; margin: 0 0 4px; }
        .subtitle { font-size: 8pt; color: #555; margin: 0 0 8px; }
        table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 7pt; }
        th, td { border: 1px solid #333; padding: 3px 4px; vertical-align: top; word-wrap: break-word; overflow-wrap: anywhere; }
        th { background: #ececec; font-weight: 700; text-align: center; font-size: 6.5pt; line-height: 1.15; }
        td.mono { font-family: "Courier New", Courier, monospace; text-align: right; }
        td.left, th.left { text-align: left; }
        td.center, th.center { text-align: center; }
        td.notes { font-size: 6.5pt; color: #444; }
        .chart-img { width: 100%; max-width: 100%; height: auto; display: block; margin-top: 6px; }
        .footer { margin-top: 10px; padding-top: 6px; border-top: 1px solid #999; font-size: 7pt; color: #555; display: flex; justify-content: space-between; }
      </style>
      </head><body>
        <div class="header">
          <div>
            <h1>Monthly Financial Progress</h1>
            <div class="subtitle">Cost to date, contract changes, and payments over time</div>
          </div>
          <div class="meta">
            <div><strong>Project:</strong> ${esc(projectName)}</div>
            <div><strong>As of:</strong> ${esc(asOf)}</div>
            <div><strong>Printed:</strong> ${esc(printedOn)}</div>
          </div>
        </div>
        <table>
          <thead>
            <tr>
              <th class="left" style="width:7%;">Month</th>
              <th class="left" style="width:7%;">As of</th>
              <th style="width:8%;">Subtotal<br>Budget</th>
              <th style="width:8%;">Subtotal<br>Projected</th>
              <th style="width:8%;">Cost to<br>Date</th>
              <th style="width:7%;">Approved<br>COs</th>
              <th style="width:8%;">Revised<br>Contract</th>
              <th style="width:8%;">Payments<br>Received</th>
              <th style="width:7%;">Payments<br>Pending</th>
              <th style="width:8%;">Total<br>Payments</th>
              <th style="width:5%;">%<br>Complete</th>
              <th class="left" style="width:19%;">Notes</th>
            </tr>
          </thead>
          <tbody>${tableRows}</tbody>
        </table>
        ${chartBlock}
        <div class="footer">
          <span>Confidential</span>
          <span>Financial Forecast</span>
          <span>${esc(printedOn)}</span>
        </div>
      </body></html>`;

    if (global.CasePMOutput) {
      await global.CasePMOutput.deliverHtml({
        title: 'Financial Forecast',
        html: printHTML,
        filenameBase: `Financial_Forecast_${projectId() || 'project'}`,
        sourceModule: 'forecast',
        systemFolderKey: 'printed-output',
        onPrint: async () => {
          global.CasePMPrint.printHtmlInIframe(printHTML, { landscape: true, delay: 500 });
        },
      });
      return;
    }
    global.CasePMPrint.printHtmlInIframe(printHTML, { landscape: true, delay: 500 });
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
    document.querySelectorAll('[data-forecast-horizon]').forEach(btn => {
      btn.addEventListener('click', () => setHorizon(btn.dataset.forecastHorizon));
    });
    setHorizon(horizon);
    await refresh();
  }

  global.CasePMForecast = { init, refresh, loadSummary, setHorizon, printReport };
  document.addEventListener('DOMContentLoaded', init);
})(window);
