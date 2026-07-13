/**
 * Case PM Dashboard — live data tiles, drag-and-drop layout, settings.
 */
(function (global) {
  'use strict';

  const ctx = global.CASEPM_DASHBOARD_CTX || {};
  const STORAGE_KEY = `casepm_dashboard_layout_v3_u${ctx.userId || 0}`;
  const PORTFOLIO_PREFS_KEY = `casepm_portfolio_prefs_v1_u${ctx.userId || 0}`;
  const VIEW_MODE_KEY = `casepm_dashboard_view_u${ctx.userId || 0}`;
  const COLUMNS = 12;
  const TILE_W = 3;          // fixed width — 4 tiles across (12 / 3)
  const MIN_H = 1;           // 1 block tall
  const MAX_H = 3;           // up to 3 blocks tall

  // All tiles are a fixed width (4 across). Only the HEIGHT is adjustable (1–3 blocks).
  // h = number of blocks tall. Content is sized to fit its tile (no internal scroll).
  const TILE_DEFS = {
    kpis:          { label: 'KPI Summary',        icon: 'fa-chart-simple',        default: true,  h: 2 },
    weather:       { label: 'Weather',            icon: 'fa-cloud-sun',           default: true,  h: 2 },
    assigned:      { label: 'Assigned to Me',     icon: 'fa-inbox',               default: true,  h: 2 },
    financial:     { label: 'Financial Snapshot', icon: 'fa-dollar-sign',         default: true,  h: 2 },
    forecast_chart:{ label: 'Forecast Trend',     icon: 'fa-chart-line',          default: true,  h: 2 },
    open_items:    { label: 'Open Items',         icon: 'fa-triangle-exclamation',default: true,  h: 2 },
    daily_logs:    { label: 'Recent Daily Logs',  icon: 'fa-clipboard-list',      default: true,  h: 2 },
    schedule:      { label: 'Key Tasks',          icon: 'fa-calendar-week',       default: true,  h: 2 },
    commitments:   { label: 'Commitments',        icon: 'fa-file-contract',       default: true,  h: 1 },
    estimating:    { label: 'Estimating',         icon: 'fa-calculator',            default: true,  h: 1 },
    change_orders: { label: 'Change Orders',      icon: 'fa-arrows-rotate',       default: true,  h: 1 },
    safety:        { label: 'Safety This Week',   icon: 'fa-hard-hat',            default: true,  h: 1 },
    progress:      { label: 'Schedule Progress',  icon: 'fa-bars-progress',       default: true,  h: 2 },
    activity:      { label: 'Recent Activity',    icon: 'fa-clock-rotate-left',   default: true,  h: 2 },
    quick_actions: { label: 'Quick Actions',      icon: 'fa-bolt',                default: true,  h: 2 },
    project_info:  { label: 'Project Info',       icon: 'fa-circle-info',         default: false, h: 1 },
    submittals:    { label: 'Submittals',         icon: 'fa-file-arrow-up',       default: false, h: 1 },
    budget_breakdown:{ label: 'Budget Breakdown', icon: 'fa-table-cells',         default: false, h: 2 },
    contract:      { label: 'Contract Summary',   icon: 'fa-file-signature',      default: false, h: 1 },
  };

  const DEFAULT_ORDER = Object.keys(TILE_DEFS);

  let state = {
    data: null,
    weather: null,
    portfolio: null,
    viewMode: loadViewMode(),
    portfolioPrefs: loadPortfolioPrefs(),
    layout: loadLayout(),
    grid: null,
    forecastChart: null,
    suppressSave: false,
  };

  function loadViewMode() {
    try {
      const v = localStorage.getItem(VIEW_MODE_KEY);
      return v === 'portfolio' ? 'portfolio' : 'project';
    } catch (_) {
      return 'project';
    }
  }

  function saveViewMode(mode) {
    localStorage.setItem(VIEW_MODE_KEY, mode);
  }

  function loadPortfolioPrefs() {
    const defaults = { filter: 'all_active', customIds: [] };
    try {
      const raw = localStorage.getItem(PORTFOLIO_PREFS_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        return {
          filter: parsed.filter || 'all_active',
          customIds: Array.isArray(parsed.customIds) ? parsed.customIds.map(Number) : [],
        };
      }
    } catch (_) { /* ignore */ }
    return defaults;
  }

  function savePortfolioPrefs() {
    localStorage.setItem(PORTFOLIO_PREFS_KEY, JSON.stringify(state.portfolioPrefs));
  }

  function loadLayout() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        return {
          tiles: mergeTiles(parsed.tiles),
          order: Array.isArray(parsed.order) ? parsed.order : DEFAULT_ORDER.slice(),
          locked: parsed.locked !== false,
        };
      }
    } catch (_) { /* ignore */ }
    return { tiles: defaultTiles(), order: DEFAULT_ORDER.slice(), locked: true };
  }

  function clampH(h, def) {
    const val = parseInt(h, 10);
    if (!Number.isFinite(val)) return def;
    return Math.max(MIN_H, Math.min(MAX_H, val));
  }

  function defaultTiles() {
    const t = {};
    Object.keys(TILE_DEFS).forEach((id) => {
      const def = TILE_DEFS[id];
      t[id] = { visible: def.default, w: TILE_W, h: def.h, x: undefined, y: undefined };
    });
    return t;
  }

  function mergeTiles(saved) {
    const base = defaultTiles();
    if (saved && typeof saved === 'object') {
      Object.keys(base).forEach((id) => {
        if (saved[id]) {
          const def = TILE_DEFS[id];
          base[id] = {
            visible: saved[id].visible !== undefined ? saved[id].visible !== false : base[id].visible,
            w: TILE_W,
            h: clampH(saved[id].h, def.h),
            x: saved[id].x,
            y: saved[id].y,
          };
        }
      });
    }
    return base;
  }

  function saveLayout() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state.layout));
  }

  function projectId() {
    const fromCtx = ctx.projectId;
    if (fromCtx) return fromCtx;
    try {
      const raw = localStorage.getItem('casepm_current_project_id');
      return raw ? parseInt(raw, 10) : null;
    } catch (_) {
      return null;
    }
  }

  function fmtMoney(n) {
    const v = Number(n);
    if (!Number.isFinite(v)) return '—';
    return v.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
  }

  function fmtDate(iso) {
    if (!iso) return '—';
    try {
      return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    } catch (_) {
      return iso;
    }
  }

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  function tileHead(title, linkUrl, linkLabel) {
    const link = linkUrl
      ? `<a href="${esc(linkUrl)}" class="text-xs text-emerald-400 hover:text-emerald-300">${esc(linkLabel || 'Open')} <i class="fa-solid fa-arrow-right text-[10px]"></i></a>`
      : '';
    return `<div class="dash-tile-head">
      <span class="text-sm font-medium text-zinc-300">${esc(title)}</span>
      ${link}
    </div>`;
  }

  function renderKpis(d) {
    const k = d.kpis || {};
  const u = ctx.urls || {};
    const items = [
      { label: 'Active Projects', value: k.active_projects ?? 0, sub: k.total_projects === 1 ? '1 total project' : `${k.total_projects ?? 0} total`, color: 'text-white', url: null },
      { label: 'Open RFIs', value: k.open_rfis ?? 0, sub: k.overdue_rfis ? `${k.overdue_rfis} overdue` : 'On track', color: 'text-yellow-400', url: u.rfis },
      { label: 'Pending COs', value: k.open_change_orders ?? 0, sub: k.pending_co_amount ? fmtMoney(k.pending_co_amount) : 'No pending $', color: 'text-orange-400', url: u.changeOrders },
      { label: 'Open Punch', value: k.open_punch_items ?? 0, sub: k.high_priority_punch ? `${k.high_priority_punch} high priority` : 'All priorities', color: 'text-red-400', url: u.punchList },
      { label: 'Week Hours', value: k.week_hours ?? 0, sub: 'Manpower this week', color: 'text-sky-400', url: u.dailyLog },
      { label: 'Progress', value: k.overall_progress != null ? `${k.overall_progress}%` : '—', sub: 'Schedule overall', color: 'text-emerald-400', url: u.schedule },
    ];
    return `<div class="dash-tile-body dash-kpi-grid">${items.map((it) => `
      <div class="dash-kpi" data-href="${esc(it.url || '')}">
        <div class="text-[10px] text-zinc-400 truncate">${esc(it.label)}</div>
        <div class="text-lg font-semibold leading-tight ${it.color}">${esc(it.value)}</div>
        <div class="text-[9px] text-zinc-500 truncate">${esc(it.sub)}</div>
      </div>`).join('')}</div>`;
  }

  function renderWeather() {
    const w = state.weather;
    if (!w || !w.ok) {
      return `<div class="dash-tile-body text-sm text-zinc-500 text-center py-8">
        <i class="fa-solid fa-cloud text-2xl mb-2 block text-zinc-600"></i>
        ${w && w.error ? esc(w.error) : 'Set project city/state for live weather'}
      </div>`;
    }
    return `<div class="dash-tile-body">
      <div class="flex items-start justify-between mb-2">
        <div>
          <div class="font-semibold">${esc(w.location)}</div>
          <div class="text-xs text-zinc-500">Live · Open-Meteo</div>
        </div>
        <i class="fa-solid fa-cloud-sun text-3xl text-emerald-400"></i>
      </div>
      <div class="flex items-end gap-2">
        <div class="text-5xl font-semibold">${w.temperature}°</div>
        <div class="text-zinc-400 mb-1">/ ${w.low}°</div>
      </div>
      <div class="text-sm text-emerald-400 mt-1">${esc(w.description)} · ${w.precip_chance}% rain</div>
      <div class="mt-3 pt-3 border-t border-zinc-700 text-xs text-zinc-400 flex justify-between">
        <span>Humidity: ${w.humidity}%</span>
        <span>Wind: ${w.wind_mph} mph</span>
        <span>High: ${w.high}°</span>
      </div>
    </div>`;
  }

  function renderAssigned(d) {
    const items = d.assigned_items || [];
    const u = ctx.urls || {};
    if (!items.length) {
      return `<div class="dash-tile-body text-sm text-zinc-500 text-center py-6">No pending items — you're caught up.</div>`;
    }
    return `<div class="dash-tile-body space-y-1.5">${items.map((it) => `
      <a href="${esc(it.action_url || u.email)}" class="flex items-center gap-2 p-1.5 bg-zinc-950 hover:bg-zinc-800 border border-zinc-800 rounded-md transition-colors">
        <i class="fa-solid ${it.source === 'approval' ? 'fa-circle-check text-amber-400' : 'fa-envelope text-emerald-400'} text-xs shrink-0"></i>
        <div class="min-w-0 flex-1">
          <div class="text-xs truncate ${it.unread ? 'text-white font-medium' : 'text-zinc-300'}">${esc(it.subject)}</div>
          <div class="text-[10px] text-zinc-500 truncate">${esc(it.module || it.preview)}</div>
        </div>
        ${it.requires_action ? '<span class="text-[9px] px-1.5 py-0.5 bg-amber-500/20 text-amber-400 rounded-full shrink-0">!</span>' : ''}
      </a>`).join('')}</div>`;
  }

  function renderFinancial(d) {
    const f = d.financial || {};
    const u = ctx.urls || {};
    return `<div class="dash-tile-body space-y-3">
      <div class="grid grid-cols-2 gap-3">
        <div><div class="text-xs text-zinc-400">Contract</div><div class="text-lg font-semibold">${fmtMoney(f.contract_amount)}</div></div>
        <div><div class="text-xs text-zinc-400">Revised Budget</div><div class="text-lg font-semibold text-emerald-400">${fmtMoney(f.revised_budget)}</div></div>
        <div><div class="text-xs text-zinc-400">Cost to Date</div><div class="text-lg font-semibold text-sky-400">${fmtMoney(f.actual_cost)}</div></div>
        <div><div class="text-xs text-zinc-400">Variance</div><div class="text-lg font-semibold ${(f.variance || 0) >= 0 ? 'text-emerald-400' : 'text-red-400'}">${fmtMoney(f.variance)}</div></div>
      </div>
      <div class="text-xs text-zinc-500 flex justify-between pt-2 border-t border-zinc-700">
        <span>Committed: ${fmtMoney(f.committed)}</span>
        <span>Paid: ${fmtMoney(f.paid_out)}</span>
        <span>${f.pct_complete != null ? f.pct_complete + '% complete' : ''}</span>
      </div>
      <div class="flex gap-2">
        <a href="${esc(u.budget)}" class="text-xs text-emerald-400 hover:text-emerald-300">Budget →</a>
        <a href="${esc(u.forecast)}" class="text-xs text-emerald-400 hover:text-emerald-300">Forecast →</a>
      </div>
    </div>`;
  }

  function renderForecastChart(d) {
    return `<div class="dash-tile-body"><div style="position:relative;height:100%;min-height:140px"><canvas id="dashForecastCanvas"></canvas></div></div>`;
  }

  function renderOpenItems(d) {
    const o = d.open_items || {};
    const u = ctx.urls || {};
    return `<div class="dash-tile-body grid grid-cols-1 gap-2">
      <div class="flex justify-between items-center p-2 bg-zinc-950 border border-zinc-800 rounded-md">
        <div><div class="text-[10px] text-zinc-400">RFIs Awaiting</div><div class="text-lg font-semibold text-yellow-400 leading-tight">${o.rfis_awaiting ?? 0}</div></div>
        <a href="${esc(u.rfis)}" class="text-xs text-emerald-400">Review →</a>
      </div>
      <div class="flex justify-between items-center p-2 bg-zinc-950 border border-zinc-800 rounded-md">
        <div><div class="text-[10px] text-zinc-400">Change Orders</div><div class="text-lg font-semibold text-orange-400 leading-tight">${o.change_orders_pending ?? 0}</div></div>
        <a href="${esc(u.changeOrders)}" class="text-xs text-emerald-400">Review →</a>
      </div>
      <div class="flex justify-between items-center p-2 bg-zinc-950 border border-zinc-800 rounded-md">
        <div><div class="text-[10px] text-zinc-400">High Priority Punch</div><div class="text-lg font-semibold text-red-400 leading-tight">${o.high_priority_punch ?? 0}</div></div>
        <a href="${esc(u.punchList)}" class="text-xs text-emerald-400">View →</a>
      </div>
    </div>`;
  }

  function renderDailyLogs(d) {
    const logs = d.daily_logs || [];
    const u = ctx.urls || {};
    if (!logs.length) {
      return `<div class="dash-tile-body text-sm text-zinc-500 text-center py-6">No daily logs yet for this project.</div>`;
    }
    return `<div class="dash-tile-body space-y-1.5">${logs.map((log) => `
      <a href="${esc(u.dailyLog)}?id=${log.id}" class="flex items-center gap-2.5 p-1.5 bg-zinc-950 hover:bg-zinc-800 border border-zinc-800 rounded-md">
        <div class="text-center w-8 shrink-0">
          <div class="text-[9px] text-zinc-500">${fmtDate(log.date).split(' ')[0]}</div>
          <div class="text-base font-semibold leading-tight">${log.date ? new Date(log.date).getDate() : '—'}</div>
        </div>
        <div class="min-w-0 flex-1">
          <div class="text-xs truncate">${esc(log.work_performed || 'Daily log entry')}</div>
          <div class="text-[10px] text-zinc-500 truncate">${esc(log.user_name)} · ${log.manpower_count} workers · ${log.hours} hrs</div>
        </div>
      </a>`).join('')}</div>`;
  }

  function renderSchedule(d) {
    const tasks = d.upcoming_tasks || [];
    const u = ctx.urls || {};
    if (!tasks.length) {
      return `<div class="dash-tile-body text-sm text-zinc-500 text-center py-6">No upcoming tasks scheduled.</div>`;
    }
    return `<div class="dash-tile-body space-y-1.5">${tasks.map((t) => {
      const st = t.status || 'Not Started';
      const cls = st === 'Delayed' ? 'bg-red-500/20 text-red-400' : st === 'In Progress' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-emerald-500/20 text-emerald-400';
      return `<a href="${esc(u.schedule)}" class="flex items-center justify-between gap-2 p-1.5 bg-zinc-950 border border-zinc-800 rounded-md hover:bg-zinc-800">
        <div class="min-w-0">
          <div class="text-xs truncate">${esc(t.description)}</div>
          <div class="text-[10px] text-zinc-500 truncate">${esc(t.phase)} · Due ${fmtDate(t.end_date)}</div>
        </div>
        <span class="text-[9px] px-1.5 py-0.5 rounded-full shrink-0 ${cls}">${esc(st)}</span>
      </a>`;
    }).join('')}</div>`;
  }

  function renderCommitments(d) {
    const c = d.commitments || {};
    const u = ctx.urls || {};
    return `<div class="dash-tile-body space-y-3">
      <div class="grid grid-cols-2 gap-3 text-center">
        <div class="p-3 bg-zinc-950 rounded-md border border-zinc-800"><div class="text-2xl font-semibold">${c.total_count ?? 0}</div><div class="text-xs text-zinc-400">Total</div></div>
        <div class="p-3 bg-zinc-950 rounded-md border border-zinc-800"><div class="text-2xl font-semibold text-amber-400">${c.pending_count ?? 0}</div><div class="text-xs text-zinc-400">Pending</div></div>
      </div>
      <div class="text-sm flex justify-between"><span class="text-zinc-400">Approved value</span><span class="font-medium">${fmtMoney(c.approved_total)}</span></div>
      <div class="text-sm flex justify-between"><span class="text-zinc-400">Pending value</span><span class="font-medium text-orange-400">${fmtMoney(c.pending_total)}</span></div>
      <a href="${esc(u.commitments)}" class="text-xs text-emerald-400">Open commitments →</a>
    </div>`;
  }

  function renderEstimating(d) {
    const e = d.estimating || {};
    const u = ctx.urls || {};
    return `<div class="dash-tile-body space-y-3">
      <div class="grid grid-cols-2 gap-3 text-center">
        <div class="p-3 bg-zinc-950 rounded-md border border-zinc-800"><div class="text-lg font-semibold font-mono">${esc(e.active_estimate || '—')}</div><div class="text-xs text-zinc-400">Active est.</div></div>
        <div class="p-3 bg-zinc-950 rounded-md border border-zinc-800"><div class="text-2xl font-semibold text-sky-400">${e.open_packages ?? 0}</div><div class="text-xs text-zinc-400">Open RFPs</div></div>
      </div>
      <div class="text-sm flex justify-between"><span class="text-zinc-400">Loaded total</span><span class="font-medium">${fmtMoney(e.active_total)}</span></div>
      <div class="text-sm flex justify-between"><span class="text-zinc-400">Quotes / due week</span><span>${e.quotes_received ?? 0} · ${e.due_this_week ?? 0}</span></div>
      <a href="${esc(u.estimating)}" class="text-xs text-emerald-400">Open estimating →</a>
    </div>`;
  }

  function renderChangeOrders(d) {
    const c = d.change_orders || {};
    const erp = d.erp_queue || {};
    const variance = d.billing_variance || {};
    const u = ctx.urls || {};
    const erpPending = erp.pending_review_count ?? 0;
    const varCount = variance.flagged_count ?? 0;
    const varTotal = variance.total_variance ?? 0;
    return `<div class="dash-tile-body space-y-3">
      <div class="grid grid-cols-2 gap-3">
        <div class="p-3 bg-zinc-950 rounded-md border border-zinc-800 text-center"><div class="text-2xl font-semibold text-emerald-400">${c.approved_count ?? 0}</div><div class="text-xs text-zinc-400">Approved</div></div>
        <div class="p-3 bg-zinc-950 rounded-md border border-zinc-800 text-center"><div class="text-2xl font-semibold text-amber-400">${c.pending_count ?? 0}</div><div class="text-xs text-zinc-400">Pending</div></div>
      </div>
      <div class="text-sm flex justify-between"><span class="text-zinc-400">Approved $</span><span>${fmtMoney(c.approved_amount)}</span></div>
      <div class="text-sm flex justify-between"><span class="text-zinc-400">Pending $</span><span class="text-orange-400">${fmtMoney(c.pending_amount)}</span></div>
      ${erpPending ? `<div class="text-sm flex justify-between border-t border-zinc-800 pt-2"><span class="text-zinc-400">ERP pending review</span><span class="font-medium text-violet-400">${erpPending}</span></div>` : ''}
      ${varCount ? `<div class="text-sm flex justify-between"><span class="text-zinc-400">Sub CO billing variance</span><span class="font-mono ${varTotal >= 0 ? 'text-amber-400' : 'text-red-400'}">${varCount} · ${fmtMoney(varTotal)}</span></div>` : ''}
      <a href="${esc(u.changeOrders)}${erpPending ? '?tab=erp' : ''}" class="text-xs text-emerald-400">Open change orders →</a>
    </div>`;
  }

  function renderSafety(d) {
    const s = d.safety || {};
    const u = ctx.urls || {};
    const status = s.incidents > 0 ? 'Needs attention' : s.near_misses > 0 ? 'Caution' : 'Good week';
    const statusCls = s.incidents > 0 ? 'text-red-400' : s.near_misses > 0 ? 'text-yellow-400' : 'text-emerald-400';
    return `<div class="dash-tile-body">
      <div class="text-xs ${statusCls} mb-3 font-medium">${status}</div>
      <div class="grid grid-cols-3 gap-2 text-center mb-4">
        <div><div class="text-2xl font-semibold ${s.incidents ? 'text-red-400' : 'text-emerald-400'}">${s.incidents ?? 0}</div><div class="text-[10px] text-zinc-400">Incidents</div></div>
        <div><div class="text-2xl font-semibold text-yellow-400">${s.near_misses ?? 0}</div><div class="text-[10px] text-zinc-400">Near Miss</div></div>
        <div><div class="text-2xl font-semibold text-emerald-400">${s.observations ?? 0}</div><div class="text-[10px] text-zinc-400">Observations</div></div>
      </div>
      <div class="text-xs text-zinc-500">${s.week_reports ?? 0} reports this week</div>
      <a href="${esc(u.safety)}" class="mt-3 inline-block text-xs text-emerald-400">Safety log →</a>
    </div>`;
  }

  function renderProgress(d) {
    const rows = d.schedule_progress || [];
    const u = ctx.urls || {};
    if (!rows.length) {
      return `<div class="dash-tile-body text-sm text-zinc-500 text-center py-6">Import schedule to see progress.</div>`;
    }
    return `<div class="dash-tile-body space-y-3">${rows.map((r) => `
      <div>
        <div class="flex justify-between text-xs mb-1"><span class="truncate pr-2">${esc(r.name)}</span><span class="font-medium shrink-0">${r.percent}%</span></div>
        <div class="dash-progress-bar"><span style="width:${Math.min(100, r.percent)}%"></span></div>
      </div>`).join('')}
      <a href="${esc(u.schedule)}" class="text-xs text-emerald-400">Full schedule →</a>
    </div>`;
  }

  function renderActivity(d) {
    const items = d.recent_activity || [];
    if (!items.length) {
      return `<div class="dash-tile-body text-sm text-zinc-500 text-center py-6">No recent activity.</div>`;
    }
    const icons = {
      rfi: 'fa-circle-question text-yellow-400',
      change_order: 'fa-arrows-rotate text-orange-400',
      daily_log: 'fa-clipboard-list text-emerald-400',
      submittal: 'fa-file-arrow-up text-blue-400',
    };
    return `<div class="dash-tile-body space-y-1.5">${items.map((a) => `
      <a href="${esc(a.url || '#')}" class="flex gap-2 text-xs hover:bg-zinc-950 p-1.5 rounded-md">
        <i class="fa-solid ${icons[a.type] || 'fa-circle-info text-zinc-400'} mt-0.5 text-[11px]"></i>
        <div class="min-w-0">
          <div class="truncate">${esc(a.message)}</div>
          <div class="text-[10px] text-zinc-500">${fmtDate(a.timestamp)} ${a.user ? '· ' + esc(a.user) : ''}</div>
        </div>
      </a>`).join('')}</div>`;
  }

  function renderQuickActions() {
    const u = ctx.urls || {};
    const actions = [
      { label: 'Daily Log', icon: 'fa-clipboard-list text-emerald-400', url: u.dailyLog },
      { label: 'New RFI', icon: 'fa-circle-question text-yellow-400', url: (u.rfis || '') + '?action=new' },
      { label: 'Change Order', icon: 'fa-arrows-rotate text-orange-400', url: (u.changeOrders || '') + '?action=new' },
      { label: 'Submittal', icon: 'fa-file-arrow-up text-blue-400', url: (u.submittals || '') + '?action=new' },
      { label: 'Punch Item', icon: 'fa-list-check text-red-400', url: (u.punchList || '') + '?action=new' },
      { label: 'Upload Photos', icon: 'fa-camera text-purple-400', url: (u.photos || '') + '?action=upload' },
    ];
    return `<div class="dash-tile-body grid grid-cols-2 gap-2">${actions.map((a) => `
      <a href="${esc(a.url)}" class="flex flex-col items-center justify-center gap-1.5 p-3 bg-zinc-950 hover:bg-zinc-800 border border-zinc-800 rounded-md text-center">
        <i class="fa-solid ${a.icon} text-lg"></i>
        <span class="text-xs">${esc(a.label)}</span>
      </a>`).join('')}</div>`;
  }

  function renderProjectInfo(d) {
    const p = d.project || {};
    const loc = d.location || {};
    const locStr = [loc.city, loc.state].filter(Boolean).join(', ') || loc.address || '—';
    return `<div class="dash-tile-body space-y-2 text-sm">
      <div class="flex justify-between"><span class="text-zinc-400">Name</span><span class="font-medium truncate ml-2">${esc(p.name || '—')}</span></div>
      <div class="flex justify-between"><span class="text-zinc-400">Number</span><span class="font-mono">${esc(p.number || '—')}</span></div>
      <div class="flex justify-between"><span class="text-zinc-400">Status</span><span class="text-emerald-400">${esc(p.status || '—')}</span></div>
      <div class="flex justify-between"><span class="text-zinc-400">Location</span><span class="truncate ml-2">${esc(locStr)}</span></div>
    </div>`;
  }

  function renderSubmittals(d) {
    const k = d.kpis || {};
    const u = ctx.urls || {};
    return `<div class="dash-tile-body flex flex-col items-center justify-center text-center gap-2 h-full">
      <i class="fa-solid fa-file-arrow-up text-3xl text-blue-400/40"></i>
      <div class="text-4xl font-semibold">${k.open_submittals ?? 0}</div>
      <div class="text-xs text-zinc-400">Open submittals</div>
      <a href="${esc(u.submittals)}" class="text-xs text-emerald-400 mt-1">Open submittals →</a>
    </div>`;
  }

  function renderBudgetBreakdown(d) {
    const f = d.financial || {};
    const rows = [
      { label: 'Original Budget', value: f.original_budget, color: 'text-white' },
      { label: 'Revised Budget', value: f.revised_budget, color: 'text-emerald-400' },
      { label: 'Committed', value: f.committed, color: 'text-sky-400' },
      { label: 'Cost to Date', value: f.actual_cost, color: 'text-amber-400' },
      { label: 'Variance', value: f.variance, color: (f.variance || 0) >= 0 ? 'text-emerald-400' : 'text-red-400' },
    ];
    return `<div class="dash-tile-body space-y-2">${rows.map((r) => `
      <div class="flex justify-between items-center text-sm py-1.5 border-b border-zinc-800 last:border-0">
        <span class="text-zinc-400">${esc(r.label)}</span>
        <span class="font-mono ${r.color}">${fmtMoney(r.value)}</span>
      </div>`).join('')}</div>`;
  }

  function renderContract(d) {
    const f = d.financial || {};
    const u = ctx.urls || {};
    const pct = f.pct_complete != null ? Math.min(100, f.pct_complete) : 0;
    return `<div class="dash-tile-body space-y-3">
      <div><div class="text-xs text-zinc-400">Contract to Date</div><div class="text-2xl font-semibold">${fmtMoney(f.contract_amount)}</div></div>
      <div>
        <div class="flex justify-between text-xs mb-1"><span class="text-zinc-400">Billed</span><span>${f.pct_complete != null ? f.pct_complete + '%' : '—'}</span></div>
        <div class="dash-progress-bar"><span style="width:${pct}%"></span></div>
      </div>
      <div class="text-sm flex justify-between"><span class="text-zinc-400">Paid out</span><span>${fmtMoney(f.paid_out)}</span></div>
      <a href="${esc(u.payApps)}" class="text-xs text-emerald-400">Pay applications →</a>
    </div>`;
  }

  const RENDERERS = {
    kpis: (d) => renderKpis(d),
    weather: () => renderWeather(),
    assigned: (d) => renderAssigned(d),
    financial: (d) => renderFinancial(d),
    forecast_chart: (d) => renderForecastChart(d),
    open_items: (d) => renderOpenItems(d),
    daily_logs: (d) => renderDailyLogs(d),
    schedule: (d) => renderSchedule(d),
    commitments: (d) => renderCommitments(d),
    estimating: (d) => renderEstimating(d),
    change_orders: (d) => renderChangeOrders(d),
    safety: (d) => renderSafety(d),
    progress: (d) => renderProgress(d),
    activity: (d) => renderActivity(d),
    quick_actions: () => renderQuickActions(),
    project_info: (d) => renderProjectInfo(d),
    submittals: (d) => renderSubmittals(d),
    budget_breakdown: (d) => renderBudgetBreakdown(d),
    contract: (d) => renderContract(d),
  };

  const TILE_LINKS = {
    assigned: { url: () => ctx.urls?.email, label: 'Internal inbox' },
    daily_logs: { url: () => ctx.urls?.dailyLog, label: 'View all' },
    schedule: { url: () => ctx.urls?.schedule, label: 'Schedule' },
    activity: { url: null, label: null },
    forecast_chart: { url: () => ctx.urls?.forecast, label: 'Forecast' },
  };

  function tileInnerHTML(id, data) {
    const def = TILE_DEFS[id];
    if (!def) return '';
    const link = TILE_LINKS[id];
    const head = tileHead(def.label, link?.url?.(), link?.label);
    const body = (RENDERERS[id] || (() => ''))(data);
    return `${head}${body}`;
  }

  function initGrid() {
    if (state.grid || !global.GridStack) return;
    const el = document.getElementById('dashboardGrid');
    if (!el) return;
    state.grid = global.GridStack.init({
      column: COLUMNS,
      cellHeight: 150,
      margin: 8,
      float: false,
      animate: true,
      staticGrid: state.layout.locked,
      handle: '.dash-tile-head',
      // Only allow vertical resize (drag the bottom edge). Width is fixed.
      resizable: { handles: 's' },
    }, el);

    state.grid.on('change', (event, items) => {
      if (state.suppressSave) return;
      (items || []).forEach((node) => {
        const id = node.id || (node.el && node.el.getAttribute('gs-id'));
        if (id && state.layout.tiles[id]) {
          state.layout.tiles[id].x = node.x;
          state.layout.tiles[id].y = node.y;
          state.layout.tiles[id].h = clampH(node.h, TILE_DEFS[id].h);
        }
      });
      saveLayout();
    });

    state.grid.on('resizestop', () => {
      if (state.forecastChart) state.forecastChart.resize();
    });
  }

  function addTile(id, data) {
    const def = TILE_DEFS[id];
    const t = state.layout.tiles[id] || {};
    if (!def || t.visible === false) return;

    const wrapper = document.createElement('div');
    wrapper.className = 'grid-stack-item';
    wrapper.setAttribute('gs-id', id);
    wrapper.setAttribute('gs-w', String(TILE_W));
    wrapper.setAttribute('gs-h', String(clampH(t.h, def.h)));
    wrapper.setAttribute('gs-min-w', String(TILE_W));
    wrapper.setAttribute('gs-max-w', String(TILE_W));
    wrapper.setAttribute('gs-min-h', String(MIN_H));
    wrapper.setAttribute('gs-max-h', String(MAX_H));
    if (Number.isInteger(t.x)) wrapper.setAttribute('gs-x', String(t.x));
    if (Number.isInteger(t.y)) wrapper.setAttribute('gs-y', String(t.y));

    const content = document.createElement('div');
    content.className = 'grid-stack-item-content';
    content.setAttribute('data-tile-id', id);
    content.innerHTML = tileInnerHTML(id, data);
    wrapper.appendChild(content);

    state.grid.el.appendChild(wrapper);
    state.grid.makeWidget(wrapper);
  }

  function renderGrid() {
    initGrid();
    if (!state.grid) return;
    const data = state.data || {};

    state.suppressSave = true;
    state.grid.removeAll();
    const order = state.layout.order.filter((id) => TILE_DEFS[id]);
    // Include any tiles not in saved order (newly added defs).
    Object.keys(TILE_DEFS).forEach((id) => { if (!order.includes(id)) order.push(id); });
    state.grid.batchUpdate();
    order.forEach((id) => addTile(id, data));
    state.grid.commit();
    state.suppressSave = false;

    document.querySelectorAll('#dashboardGrid .dash-kpi[data-href]').forEach((el) => {
      const href = el.getAttribute('data-href');
      if (href) el.addEventListener('click', () => { window.location.href = href; });
    });

    mountForecastChart();
    updateUnlockUI();
  }

  function mountForecastChart() {
    if (state.forecastChart) {
      state.forecastChart.destroy();
      state.forecastChart = null;
    }
    const canvas = document.getElementById('dashForecastCanvas');
    if (!canvas || !global.Chart) return;
    const trends = state.data?.forecast_chart?.monthly_trends || [];
    if (!trends.length) return;

    const labels = trends.map((r) => r.month || '');
    state.forecastChart = new global.Chart(canvas, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Cost to Date',
            data: trends.map((r) => r.cost_to_date || 0),
            borderColor: '#38bdf8',
            backgroundColor: 'transparent',
            tension: 0.35,
            pointRadius: 2,
          },
          {
            label: 'Payments',
            data: trends.map((r) => r.total_payments || 0),
            borderColor: '#a78bfa',
            backgroundColor: 'transparent',
            tension: 0.35,
            pointRadius: 2,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: '#a1a1aa', boxWidth: 12, font: { size: 10 } } } },
        scales: {
          x: { ticks: { color: '#71717a', font: { size: 10 } }, grid: { color: '#27272a' } },
          y: { ticks: { color: '#71717a', font: { size: 10 } }, grid: { color: '#27272a' } },
        },
      },
    });
  }

  function applyLockState() {
    if (!state.grid) return;
    const locked = state.layout.locked;
    state.grid.setStatic(locked);
    // Explicitly toggle move/resize so drag reliably re-enables after unlock.
    if (typeof state.grid.enableMove === 'function') state.grid.enableMove(!locked);
    if (typeof state.grid.enableResize === 'function') state.grid.enableResize(!locked);
    const el = document.getElementById('dashboardGrid');
    if (el) el.classList.toggle('dash-editing', !locked);
  }

  function updateUnlockUI() {
    const banner = document.getElementById('dashUnlockBanner');
    if (banner) banner.classList.toggle('visible', !state.layout.locked);
    const toggle = document.getElementById('dashUnlockToggle');
    if (toggle) toggle.checked = !state.layout.locked;
    applyLockState();
  }

  function buildChecklist() {
    const box = document.getElementById('dashTileChecklist');
    if (!box) return;
    box.innerHTML = Object.keys(TILE_DEFS).map((id) => {
      const def = TILE_DEFS[id];
      const checked = state.layout.tiles[id] ? state.layout.tiles[id].visible !== false : def.default;
      return `<label class="flex items-center gap-3 p-2 hover:bg-zinc-800 rounded-md cursor-pointer">
        <input type="checkbox" class="dash-tile-check accent-emerald-500" data-tile="${id}" ${checked ? 'checked' : ''}>
        <i class="fa-solid ${def.icon} text-zinc-500 w-4"></i>
        <span class="text-sm">${esc(def.label)}</span>
      </label>`;
    }).join('');
  }

  async function fetchPortfolio() {
    const res = await fetch('/api/dashboard/portfolio');
    if (!res.ok) throw new Error('Failed to load portfolio dashboard');
    return res.json();
  }

  function filterPortfolioProjects(projects) {
    const prefs = state.portfolioPrefs;
    const currentYear = new Date().getFullYear();
    const activeStatuses = new Set(['Active', 'Pre-Construction']);

    if (prefs.filter === 'custom' && prefs.customIds.length) {
      const idSet = new Set(prefs.customIds.map(Number));
      return projects.filter((p) => idSet.has(Number(p.id)));
    }
    if (prefs.filter === 'all_year') {
      return projects.filter((p) => Number(p.year) === currentYear);
    }
    return projects.filter((p) => activeStatuses.has(p.status || ''));
  }

  function projectUrl(path, pid) {
    const base = path || '/dashboard';
    const sep = base.includes('?') ? '&' : '?';
    return `${base}${sep}project_id=${pid}`;
  }

  function statusBadgeClass(status) {
    const s = (status || '').toLowerCase();
    if (s === 'active') return 'bg-emerald-900/60 text-emerald-400';
    if (s === 'pre-construction') return 'bg-sky-900/60 text-sky-400';
    if (s === 'completed' || s === 'closed') return 'bg-zinc-700 text-zinc-400';
    return 'bg-amber-900/60 text-amber-400';
  }

  function renderPortfolioCard(p) {
    const f = p.financial || {};
    const rfis = p.rfis || {};
    const cos = p.change_orders || {};
    const u = ctx.urls || {};
    const pct = f.pct_complete != null ? Math.min(100, Number(f.pct_complete)) : (p.schedule_pct != null ? Math.min(100, Number(p.schedule_pct)) : 0);
    const variance = Number(f.variance);
    const varianceCls = Number.isFinite(variance) && variance < 0 ? 'text-red-400' : 'text-emerald-400';
    const title = p.number ? `${p.number} · ${p.name}` : p.name;

    return `<article class="dash-portfolio-card" data-project-id="${p.id}" tabindex="0" role="button" aria-label="Open ${esc(title)}">
      <div class="dash-portfolio-card-head">
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <div class="font-semibold text-white truncate">${esc(title)}</div>
            <div class="text-xs text-zinc-500 truncate mt-0.5">${esc(p.location || p.client || '')}</div>
          </div>
          <span class="text-[10px] px-2 py-0.5 rounded-full shrink-0 ${statusBadgeClass(p.status)}">${esc(p.status || '—')}</span>
        </div>
        ${p.project_manager ? `<div class="text-[10px] text-zinc-500 mt-1">PM: ${esc(p.project_manager)}</div>` : ''}
      </div>
      <div class="dash-portfolio-card-body space-y-3">
        <div>
          <div class="flex justify-between text-xs mb-1">
            <span class="text-zinc-400">Budget / Forecast</span>
            <span class="text-zinc-300">${pct ? pct + '% billed' : '—'}</span>
          </div>
          <div class="dash-portfolio-mini-bar"><span style="width:${pct}%"></span></div>
          <div class="grid grid-cols-2 gap-2 mt-2">
            <div class="dash-portfolio-stat">
              <div class="dash-portfolio-stat-label">Revised Budget</div>
              <div class="dash-portfolio-stat-value text-emerald-400">${fmtMoney(f.revised_budget)}</div>
            </div>
            <div class="dash-portfolio-stat">
              <div class="dash-portfolio-stat-label">Cost to Date</div>
              <div class="dash-portfolio-stat-value text-sky-400">${fmtMoney(f.actual_cost)}</div>
            </div>
            <div class="dash-portfolio-stat">
              <div class="dash-portfolio-stat-label">EAC</div>
              <div class="dash-portfolio-stat-value">${fmtMoney(f.estimated_cost_at_completion)}</div>
            </div>
            <div class="dash-portfolio-stat">
              <div class="dash-portfolio-stat-label">Variance</div>
              <div class="dash-portfolio-stat-value ${varianceCls}">${fmtMoney(f.variance)}</div>
            </div>
          </div>
        </div>
        <div class="grid grid-cols-3 gap-2 text-center">
          <div class="dash-portfolio-stat">
            <div class="dash-portfolio-stat-label">Open RFIs</div>
            <div class="dash-portfolio-stat-value text-yellow-400">${rfis.open ?? 0}</div>
            ${rfis.overdue ? `<div class="text-[9px] text-red-400">${rfis.overdue} overdue</div>` : ''}
          </div>
          <div class="dash-portfolio-stat">
            <div class="dash-portfolio-stat-label">Pending COs</div>
            <div class="dash-portfolio-stat-value text-orange-400">${cos.pending_count ?? 0}</div>
            <div class="text-[9px] text-zinc-500">${fmtMoney(cos.pending_total)}</div>
          </div>
          <div class="dash-portfolio-stat">
            <div class="dash-portfolio-stat-label">Open PCOs</div>
            <div class="dash-portfolio-stat-value text-amber-300">${cos.open_pco_count ?? 0}</div>
            <div class="text-[9px] text-zinc-500">${fmtMoney(cos.pco_rom_total)} ROM</div>
          </div>
        </div>
        <div class="flex flex-wrap gap-3 text-xs text-zinc-500 pt-1 border-t border-zinc-800">
          <span><i class="fa-solid fa-check-double text-emerald-500 mr-1"></i>${cos.approved_count ?? 0} approved COs</span>
          <span><i class="fa-solid fa-list-check text-red-400 mr-1"></i>${p.open_punch ?? 0} punch</span>
          <span><i class="fa-solid fa-file-arrow-up text-blue-400 mr-1"></i>${p.open_submittals ?? 0} submittals</span>
        </div>
      </div>
    </article>`;
  }

  function renderPortfolio() {
    const container = document.getElementById('dashboardPortfolio');
    if (!container) return;
    const all = state.portfolio?.projects || [];
    const filtered = filterPortfolioProjects(all);

    if (!filtered.length) {
      container.innerHTML = `<div class="dash-portfolio-empty col-span-full">
        <i class="fa-solid fa-folder-open text-4xl text-zinc-600 mb-3"></i>
        <div class="text-lg font-medium text-zinc-400 mb-1">No projects match your filter</div>
        <div class="text-sm">Open <button type="button" id="dashEmptySettings" class="text-emerald-400 hover:underline">Settings</button> to choose which projects appear here.</div>
      </div>`;
      document.getElementById('dashEmptySettings')?.addEventListener('click', openSettings);
      return;
    }

    container.innerHTML = filtered.map(renderPortfolioCard).join('');
    container.querySelectorAll('.dash-portfolio-card').forEach((card) => {
      const pid = parseInt(card.getAttribute('data-project-id'), 10);
      const openProject = () => {
        if (typeof global.switchProject === 'function') {
          global.switchProject(pid);
        } else {
          localStorage.setItem('casepm_current_project_id', String(pid));
          window.location.href = projectUrl(ctx.urls?.dashboard || '/dashboard', pid);
        }
        setViewMode('project');
      };
      card.addEventListener('click', openProject);
      card.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          openProject();
        }
      });
    });
  }

  function setViewMode(mode) {
    state.viewMode = mode === 'portfolio' ? 'portfolio' : 'project';
    saveViewMode(state.viewMode);

    const projectPanel = document.getElementById('dashProjectPanel');
    const portfolioPanel = document.getElementById('dashPortfolioPanel');
    const unlockBanner = document.getElementById('dashUnlockBanner');
    const btnProject = document.getElementById('dashViewProject');
    const btnPortfolio = document.getElementById('dashViewPortfolio');

    if (projectPanel) projectPanel.classList.toggle('hidden', state.viewMode !== 'project');
    if (portfolioPanel) portfolioPanel.classList.toggle('hidden', state.viewMode !== 'portfolio');
    if (unlockBanner) unlockBanner.classList.toggle('visible', state.viewMode === 'project' && !state.layout.locked);
    if (btnProject) {
      btnProject.classList.toggle('active', state.viewMode === 'project');
      btnProject.setAttribute('aria-selected', state.viewMode === 'project' ? 'true' : 'false');
    }
    if (btnPortfolio) {
      btnPortfolio.classList.toggle('active', state.viewMode === 'portfolio');
      btnPortfolio.setAttribute('aria-selected', state.viewMode === 'portfolio' ? 'true' : 'false');
    }

    refresh();
  }

  function buildPortfolioProjectList() {
    const box = document.getElementById('dashPortfolioProjectList');
    if (!box || !state.portfolio?.projects) return;
    const search = (document.getElementById('dashPortfolioSearch')?.value || '').trim().toLowerCase();
    const selected = new Set((state.portfolioPrefs.customIds || []).map(Number));

    const items = state.portfolio.projects.filter((p) => {
      if (!search) return true;
      const hay = `${p.number || ''} ${p.name || ''} ${p.client || ''}`.toLowerCase();
      return hay.includes(search);
    });

    box.innerHTML = items.map((p) => {
      const label = p.number ? `${p.number} — ${p.name}` : p.name;
      const checked = selected.has(Number(p.id));
      return `<label class="flex items-center gap-2 p-2 hover:bg-zinc-800 rounded-md cursor-pointer text-sm">
        <input type="checkbox" class="dash-portfolio-project-check accent-emerald-500" data-project-id="${p.id}" ${checked ? 'checked' : ''}>
        <span class="truncate">${esc(label)}</span>
        <span class="ml-auto text-[10px] text-zinc-500 shrink-0">${esc(p.status || '')}</span>
      </label>`;
    }).join('') || '<div class="p-3 text-sm text-zinc-500 text-center">No projects found</div>';
  }

  function syncPortfolioSettingsUI() {
    const filter = state.portfolioPrefs.filter || 'all_active';
    document.querySelectorAll('input[name="dashPortfolioFilter"]').forEach((radio) => {
      radio.checked = radio.value === filter;
    });
    const picker = document.getElementById('dashPortfolioPicker');
    if (picker) picker.classList.toggle('hidden', filter !== 'custom');
    buildPortfolioProjectList();
  }

  async function fetchSummary() {
    const pid = projectId();
    const q = pid ? `?project_id=${pid}` : '';
    const res = await fetch(`/api/dashboard/summary${q}`);
    if (!res.ok) throw new Error('Failed to load dashboard');
    return res.json();
  }

  async function fetchWeather(loc) {
    const params = new URLSearchParams();
    if (loc?.city) params.set('city', loc.city);
    if (loc?.state) params.set('state', loc.state);
    const res = await fetch(`/api/dashboard/weather?${params}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      return { ok: false, error: err.error || 'Weather unavailable' };
    }
    return res.json();
  }

  async function refreshProject() {
    const status = document.getElementById('dashStatusText');
    const updated = document.getElementById('dashUpdatedAt');
    if (status) status.textContent = 'Refreshing…';

    state.data = await fetchSummary();
    state.weather = await fetchWeather(state.data.location);
    renderGrid();
    const p = state.data.project;
    const pLabel = p?.number ? `${p.number} · ${p.name}` : (p?.name || 'Current project');
    if (status) status.textContent = `This project · ${pLabel}`;
    if (updated) updated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  }

  async function refreshPortfolio() {
    const status = document.getElementById('dashStatusText');
    const updated = document.getElementById('dashUpdatedAt');
    if (status) status.textContent = 'Refreshing portfolio…';

    state.portfolio = await fetchPortfolio();
    renderPortfolio();
    const shown = filterPortfolioProjects(state.portfolio.projects || []).length;
    const total = state.portfolio.accessible_count ?? shown;
    if (status) status.textContent = `All projects · ${shown} of ${total} shown`;
    if (updated) updated.textContent = `Updated ${new Date().toLocaleTimeString()}`;
  }

  async function refresh() {
    try {
      if (state.viewMode === 'portfolio') {
        await refreshPortfolio();
      } else {
        await refreshProject();
      }
    } catch (err) {
      const status = document.getElementById('dashStatusText');
      if (status) status.textContent = `Error: ${err.message}`;
      if (global.showToast) global.showToast(err.message, 'error');
    }
  }

  async function openSettings() {
    buildChecklist();
    if (!state.portfolio) {
      try {
        state.portfolio = await fetchPortfolio();
      } catch (_) { /* picker may be empty until refresh */ }
    }
    syncPortfolioSettingsUI();
    const projectSection = document.getElementById('dashProjectSettingsSection');
    const portfolioSection = document.getElementById('dashPortfolioSettingsSection');
    if (projectSection) projectSection.classList.toggle('hidden', state.viewMode === 'portfolio');
    if (portfolioSection) portfolioSection.classList.toggle('hidden', state.viewMode !== 'portfolio');
    const modal = document.getElementById('dashSettingsModal');
    if (modal) modal.showModal();
  }

  function closeSettings() {
    const modal = document.getElementById('dashSettingsModal');
    if (modal) modal.close();
  }

  function bindEvents() {
    document.getElementById('dashBtnRefresh')?.addEventListener('click', refresh);
    document.getElementById('dashBtnSettings')?.addEventListener('click', openSettings);
    document.getElementById('dashViewProject')?.addEventListener('click', () => setViewMode('project'));
    document.getElementById('dashViewPortfolio')?.addEventListener('click', () => setViewMode('portfolio'));
    document.getElementById('dashSettingsClose')?.addEventListener('click', closeSettings);
    document.getElementById('dashSettingsSave')?.addEventListener('click', () => {
      if (state.viewMode === 'project') {
        document.querySelectorAll('.dash-tile-check').forEach((cb) => {
          const id = cb.getAttribute('data-tile');
          if (state.layout.tiles[id]) state.layout.tiles[id].visible = cb.checked;
        });
        saveLayout();
        renderGrid();
      } else {
        const selectedFilter = document.querySelector('input[name="dashPortfolioFilter"]:checked');
        state.portfolioPrefs.filter = selectedFilter ? selectedFilter.value : 'all_active';
        if (state.portfolioPrefs.filter === 'custom') {
          const ids = [];
          document.querySelectorAll('.dash-portfolio-project-check:checked').forEach((cb) => {
            const id = parseInt(cb.getAttribute('data-project-id'), 10);
            if (id) ids.push(id);
          });
          state.portfolioPrefs.customIds = ids;
        }
        savePortfolioPrefs();
        renderPortfolio();
      }
      closeSettings();
    });
    document.getElementById('dashUnlockToggle')?.addEventListener('change', (e) => {
      state.layout.locked = !e.target.checked;
      saveLayout();
      updateUnlockUI();
    });
    document.getElementById('dashResetLayout')?.addEventListener('click', () => {
      state.layout = { tiles: defaultTiles(), order: DEFAULT_ORDER.slice(), locked: true };
      saveLayout();
      buildChecklist();
      renderGrid();
      if (global.showToast) global.showToast('Layout reset to default');
    });
    document.querySelectorAll('input[name="dashPortfolioFilter"]').forEach((radio) => {
      radio.addEventListener('change', () => {
        const picker = document.getElementById('dashPortfolioPicker');
        if (picker) picker.classList.toggle('hidden', radio.value !== 'custom' || !radio.checked);
        if (radio.checked && radio.value === 'custom') buildPortfolioProjectList();
      });
    });
    document.getElementById('dashPortfolioSearch')?.addEventListener('input', buildPortfolioProjectList);

    global.addEventListener('casepm:project-changed', () => {
      if (state.viewMode === 'project') refresh();
    });
    window.onCasePmProjectChanged = function (newProjectId) {
      ctx.projectId = newProjectId;
      if (state.viewMode === 'project') refresh();
    };
  }

  function init() {
    bindEvents();
    const projectPanel = document.getElementById('dashProjectPanel');
    const portfolioPanel = document.getElementById('dashPortfolioPanel');
    const btnProject = document.getElementById('dashViewProject');
    const btnPortfolio = document.getElementById('dashViewPortfolio');
    if (projectPanel) projectPanel.classList.toggle('hidden', state.viewMode !== 'project');
    if (portfolioPanel) portfolioPanel.classList.toggle('hidden', state.viewMode !== 'portfolio');
    if (btnProject) btnProject.classList.toggle('active', state.viewMode === 'project');
    if (btnPortfolio) btnPortfolio.classList.toggle('active', state.viewMode === 'portfolio');
    refresh();
  }

  global.CasePMDashboard = { refresh, openSettings, setViewMode };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
