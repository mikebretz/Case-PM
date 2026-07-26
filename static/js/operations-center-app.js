(function () {
  'use strict';

  const ctx = window.CASEPM_OPS_CTX || {};
  const shell = window.CasePMModuleShell;
  const state = {
    categories: [],
    categoryId: null,
    moduleKey: null,
    schema: null,
    records: [],
    stats: {},
    editingId: null,
    advancedOpen: false,
  };

  const $ = id => document.getElementById(id);

  async function api(path, opts) {
    const url = path + (path.includes('?') ? '' : (ctx.projectId ? `?project_id=${ctx.projectId}` : ''));
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
      credentials: 'same-origin',
      ...opts,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || res.statusText);
    return data;
  }

  function renderSidebar() {
    const host = $('opsSidebar');
    if (!host) return;
    host.innerHTML = state.categories.map(cat => {
      const mods = (cat.modules || []).map(m => `
        <button type="button" class="ops-mod-btn ${state.moduleKey === m.key ? 'active' : ''}" data-mod="${m.key}" data-readonly="${m.read_only ? '1' : '0'}">
          ${shell.esc(m.label)}
        </button>`).join('');
      return `
        <button type="button" class="ops-cat-btn ${state.categoryId === cat.id ? 'active' : ''}" data-cat="${cat.id}">
          <i class="fa-solid ${cat.icon || 'fa-folder'} w-4"></i>${shell.esc(cat.label)}
        </button>
        <div class="${state.categoryId === cat.id ? '' : 'hidden'}" data-cat-mods="${cat.id}">${mods}</div>`;
    }).join('');
    host.querySelectorAll('[data-cat]').forEach(btn => {
      btn.addEventListener('click', () => {
        state.categoryId = btn.dataset.cat;
        renderSidebar();
      });
    });
    host.querySelectorAll('[data-mod]').forEach(btn => {
      btn.addEventListener('click', () => selectModule(btn.dataset.mod, btn.dataset.readonly === '1'));
    });
  }

  async function selectModule(key, readOnly) {
    state.moduleKey = key;
    state.editingId = null;
    renderSidebar();
    const mod = findModule(key);
    $('opsModuleTitle').textContent = mod?.label || key;
    $('opsModuleHint').textContent = readOnly ? 'Live report — no records to manage' : 'Click a row to edit · Quick Add for essentials only';

    if (key === 'wip_snapshot') {
      $('opsListHost').classList.add('hidden');
      $('opsWipHost').classList.remove('hidden');
      $('opsQuickAdd').classList.add('hidden');
      await renderWip();
      return;
    }
    $('opsListHost').classList.remove('hidden');
    $('opsWipHost').classList.add('hidden');
    $('opsQuickAdd').classList.remove('hidden');
    await loadRecords();
  }

  function findModule(key) {
    for (const cat of state.categories) {
      const m = (cat.modules || []).find(x => x.key === key);
      if (m) return m;
    }
    return null;
  }

  async function loadRecords() {
    if (!state.moduleKey) return;
    const data = await api(`/api/operations/${state.moduleKey}`);
    state.records = data.records || [];
    state.schema = data.schema || {};
    state.stats = data.stats || {};
    renderStats();
    renderList();
  }

  function renderStats() {
    const s = state.stats;
    $('opsStats').innerHTML = `
      <div><div class="text-xs text-zinc-500">Total</div><div class="text-xl font-semibold">${s.total || 0}</div></div>
      <div><div class="text-xs text-zinc-500">Open</div><div class="text-xl font-semibold text-amber-400">${s.open || 0}</div></div>
      <div><div class="text-xs text-zinc-500">Done</div><div class="text-xl font-semibold text-emerald-400">${s.closed || 0}</div></div>`;
  }

  function renderList() {
    const host = $('opsListHost');
    if (!state.records.length) {
      host.innerHTML = `<div class="p-8 text-center text-zinc-500">
        <i class="fa-solid fa-inbox text-3xl mb-3 opacity-40"></i>
        <p>No items yet. Use <strong>Quick Add</strong> to create one in three fields.</p>
      </div>`;
      return;
    }
    host.innerHTML = state.records.map(r => `
      <div class="ops-row" data-id="${r.id}">
        <div class="flex-1 min-w-0">
          <div class="font-medium text-white truncate">${shell.esc(r.title || r.number || 'Untitled')}</div>
          <div class="text-xs text-zinc-500">${shell.esc(r.record_date || '')} ${r.amount ? '· $' + Number(r.amount).toLocaleString() : ''}</div>
        </div>
        ${shell.statusChip(r.status)}
      </div>`).join('');
    host.querySelectorAll('.ops-row').forEach(row => {
      row.addEventListener('click', () => openModal(parseInt(row.dataset.id, 10)));
    });
  }

  async function renderWip() {
    const host = $('opsWipHost');
    host.innerHTML = '<div class="text-zinc-400 p-4">Loading WIP…</div>';
    const data = await api('/api/operations/wip');
    const w = data.wip || data;
    if (w.projects) {
      const rows = w.projects.map(p => `
        <tr class="border-b border-zinc-800">
          <td class="py-2 pr-4">${shell.esc(p.project_name)}</td>
          <td class="py-2 pr-4 text-right">$${Number(p.revised_contract).toLocaleString()}</td>
          <td class="py-2 pr-4 text-right">$${Number(p.actual_cost).toLocaleString()}</td>
          <td class="py-2 pr-4 text-right">${p.percent_complete}%</td>
          <td class="py-2 text-right ${p.over_under_billing >= 0 ? 'text-amber-400' : 'text-sky-400'}">$${Number(p.over_under_billing).toLocaleString()}</td>
        </tr>`).join('');
      host.innerHTML = `
        <h3 class="text-lg font-semibold mb-3">Portfolio WIP</h3>
        <table class="w-full text-sm"><thead><tr class="text-zinc-500 text-left">
          <th class="pb-2">Project</th><th class="pb-2 text-right">Revised</th><th class="pb-2 text-right">Actual</th><th class="pb-2 text-right">% Complete</th><th class="pb-2 text-right">Over/(Under)</th>
        </tr></thead><tbody>${rows}</tbody></table>
        <div class="mt-4 text-xs text-zinc-500">As of ${shell.esc(w.as_of || '')}</div>`;
      return;
    }
    host.innerHTML = `
      <h3 class="text-lg font-semibold mb-4">Work in Progress — ${shell.esc(w.project_name || '')}</h3>
      <div class="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
        ${wipCard('Original Contract', w.original_contract)}
        ${wipCard('Revised Contract', w.revised_contract)}
        ${wipCard('Committed', w.committed)}
        ${wipCard('Actual Cost', w.actual_cost)}
        ${wipCard('% Complete', w.percent_complete + '%')}
        ${wipCard('Earned Revenue', w.earned_revenue)}
        ${wipCard('Billed', w.billed_to_date)}
        ${wipCard('Over/(Under) Billing', w.over_under_billing, true)}
        ${wipCard('Gross Profit %', w.gross_profit_pct + '%')}
      </div>
      <p class="text-xs text-zinc-500 mt-4">RedTeam-style live WIP computed from budget, commitments, and pay apps.</p>`;
  }

  function wipCard(label, val, highlight) {
    const cls = highlight ? 'text-amber-400' : 'text-white';
    const display = typeof val === 'number' ? '$' + Number(val).toLocaleString() : val;
    return `<div class="bg-zinc-800/50 rounded-lg p-3 border border-zinc-700"><div class="text-xs text-zinc-500">${label}</div><div class="text-lg font-semibold ${cls} mt-1">${display}</div></div>`;
  }

  function openModal(recordId) {
    const record = recordId ? state.records.find(r => r.id === recordId) : null;
    state.editingId = recordId || null;
    state.advancedOpen = false;
    const mod = findModule(state.moduleKey);
    $('opsModalTitle').textContent = record ? 'Edit' : 'Quick Add';
    $('opsModalBody').innerHTML = shell.buildFormHtml(state.schema, 'ops', record);
    if (record) {
      const statusRow = `<div><label class="block text-xs text-zinc-400 mb-1">Status</label><select id="ops_status" class="ops-input">${(state.schema.statuses || []).map(s => `<option ${record.status === s ? 'selected' : ''}>${s}</option>`).join('')}</select></div>`;
      $('opsModalBody').insertAdjacentHTML('afterbegin', statusRow);
    }
    renderActionButtons(record);
    $('opsModal').showModal();
  }

  function renderActionButtons(record) {
    let actions = '';
    if (state.moduleKey === 'correspondence' && record) {
      actions += `<button type="button" id="opsPromoteRfi" class="text-sm text-sky-400">Promote to RFI</button>`;
    }
    if (state.moduleKey === 'tm_tickets' && record) {
      actions += `<button type="button" id="opsPromoteCe" class="text-sm text-sky-400">Promote to Change Event</button>`;
    }
    if (state.moduleKey === 'vendor_invoices' && record) {
      actions += `<button type="button" id="opsValidateInv" class="text-sm text-violet-400">Validate vs SOV</button>`;
    }
    if (state.moduleKey === 'ai_insights') {
      actions += `<button type="button" id="opsAiAsk" class="text-sm text-emerald-400">Generate insight</button>`;
    }
    if (state.moduleKey === 'timesheets' && record) {
      actions += `<button type="button" id="opsPostTs" class="text-sm text-emerald-400">Post to job cost</button>`;
    }
    if (state.moduleKey === 'payment_batches' && record) {
      actions += `<button type="button" id="opsProcessPay" class="text-sm text-emerald-400">Mark processed</button>`;
    }
    const existing = $('opsModalActions');
    if (existing) existing.remove();
    if (actions) {
      $('opsModalBody').insertAdjacentHTML('beforeend', `<div id="opsModalActions" class="flex flex-wrap gap-3 pt-2 border-t border-zinc-800 mt-2">${actions}</div>`);
      $('opsPromoteRfi')?.addEventListener('click', () => runAction('promote_rfi'));
      $('opsPromoteCe')?.addEventListener('click', () => runAction('promote_change_event'));
      $('opsValidateInv')?.addEventListener('click', () => runAction('validate_invoice'));
      $('opsAiAsk')?.addEventListener('click', () => runAction('ai_ask'));
      $('opsPostTs')?.addEventListener('click', () => runAction('post_timesheet'));
      $('opsProcessPay')?.addEventListener('click', () => runAction('process_payment'));
    }
  }

  async function runAction(action) {
    const data = await api(`/api/operations/${state.moduleKey}/${state.editingId}/action`, {
      method: 'POST',
      body: JSON.stringify({ action, question: $('ops_title')?.value }),
    });
    if (data.validation) alert((data.validation.messages || []).join('\n') || 'Validation complete');
    if (data.response) alert(data.response.replace(/\*\*/g, ''));
    if (data.message) alert(data.message);
    if (data.rfi_number) alert('RFI created: ' + data.rfi_number);
    if (data.change_event_number) alert('Change event: ' + data.change_event_number);
    await loadRecords();
    $('opsModal').close();
  }

  async function saveModal() {
    const fields = shell.readFields($('opsModalBody'), state.schema, 'ops');
    const title = fields.simple.title || fields.advanced.title || $('ops_title')?.value || 'New item';
    const body = {
      title,
      project_id: ctx.projectId,
      simple: fields.simple,
      advanced: fields.advanced,
      status: $('ops_status')?.value,
      amount: fields.simple.amount,
      record_date: fields.simple.work_date || fields.simple.due_date || fields.simple.invoice_date || fields.simple.cost_date,
    };
    if (state.editingId) {
      await api(`/api/operations/${state.moduleKey}/${state.editingId}`, { method: 'PUT', body: JSON.stringify(body) });
    } else {
      await api(`/api/operations/${state.moduleKey}`, { method: 'POST', body: JSON.stringify(body) });
    }
    $('opsModal').close();
    await loadRecords();
  }

  function bindUi() {
    $('opsQuickAdd')?.addEventListener('click', () => openModal(null));
    $('opsModalClose')?.addEventListener('click', () => $('opsModal').close());
    $('opsModalCancel')?.addEventListener('click', () => $('opsModal').close());
    $('opsModalSave')?.addEventListener('click', () => saveModal().catch(e => alert(e.message)));
    $('opsToggleAdvanced')?.addEventListener('click', () => {
      state.advancedOpen = !state.advancedOpen;
      const adv = $('opsAdvanced');
      if (adv) adv.classList.toggle('hidden', !state.advancedOpen);
      $('opsToggleAdvanced').innerHTML = state.advancedOpen
        ? '<i class="fa-solid fa-chevron-up mr-1"></i> Fewer options'
        : '<i class="fa-solid fa-chevron-down mr-1"></i> More options';
    });
  }

  async function init() {
    bindUi();
    const data = await api('/api/operations/catalog');
    state.categories = data.categories || [];
    if (state.categories.length) {
      state.categoryId = state.categories[0].id;
      const firstMod = state.categories[0].modules?.[0];
      if (firstMod) await selectModule(firstMod.key, firstMod.read_only);
    }
    renderSidebar();
  }

  init().catch(err => {
    console.error(err);
    $('opsListHost').innerHTML = `<div class="p-6 text-red-400">${shell.esc(err.message)}</div>`;
  });
})();
