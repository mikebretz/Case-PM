/**
 * General Ledger workspace — chart of accounts, journal batches, account inquiry, fiscal options.
 */
(function (global) {
  'use strict';

  let ctx = null;

  function todayIso() {
    return new Date().toISOString().slice(0, 10);
  }

  function accountOptions(accounts, selectedId) {
    return (accounts || []).map((a) => {
      const sel = String(selectedId) === String(a.id) ? ' selected' : '';
      return `<option value="${a.id}"${sel}>${a.account_number} — ${a.description}</option>`;
    }).join('');
  }

  function openWorkspaceDialog(title, bodyHtml, actionsHtml, width) {
    const dlg = global.CasePMDialog;
    if (!dlg?.open) return null;
    if (dlg.ensureStyles) dlg.ensureStyles();
    const dialog = document.createElement('dialog');
    dialog.className = 'casepm-dialog';
    if (width) {
      dialog.style.maxWidth = width;
      dialog.style.width = width;
    } else {
      dialog.style.maxWidth = 'min(720px, 96vw)';
      dialog.style.width = 'min(720px, 96vw)';
    }
    dialog.innerHTML = `
      <div class="casepm-dialog-panel casepm-dialog-panel--dark">
        <div class="casepm-dialog-title">
          <i class="fa-solid fa-circle-info text-sky-400"></i>
          <span class="flex-1 min-w-0">${ctx.esc(title)}</span>
        </div>
        <div class="casepm-dialog-body casepm-dialog-body--form text-zinc-200">${bodyHtml}</div>
        <div class="casepm-dialog-actions">${actionsHtml || ''}</div>
      </div>`;
    document.body.appendChild(dialog);
    dlg.makeDraggable(dialog, '.casepm-dialog-title');
    dlg.open(dialog);
    return dialog;
  }

  function closeWorkspaceDialog(dialog) {
    if (!dialog) return;
    dialog.close();
    dialog.remove();
  }

  async function openJournalEditor(batchId) {
    const { api, esc, money, switchModule, AD } = ctx;
    const [acctRes, locRes] = await Promise.all([
      api('/api/accounting/gl/accounts'),
      api('/api/accounting/platform/locations').catch(() => ({ locations: [] })),
    ]);
    const accounts = acctRes.accounts || [];
    const locations = locRes.locations || [];
    const locOpts = (selected) => `<option value="">—</option>${locations.map((l) =>
      `<option value="${l.id}"${String(selected) === String(l.id) ? ' selected' : ''}>${esc(l.code)}</option>`).join('')}`;
    let batch = {
      description: '',
      batch_date: todayIso(),
      source: 'GL',
      lines: [
        { account_id: accounts[0]?.id, debit: 0, credit: 0, description: '' },
        { account_id: accounts[1]?.id || accounts[0]?.id, debit: 0, credit: 0, description: '' },
      ],
    };
    if (batchId) {
      const detail = await api(`/api/accounting/gl/batches/${batchId}`);
      batch = { ...detail.batch, lines: detail.batch.lines || [] };
      if (batch.status !== 'Open') {
        await AD().alert('Only open batches can be edited.', 'warning');
        return;
      }
    }

    const renderLines = () => (batch.lines || []).map((ln, idx) => {
      const segVal = Array.isArray(ln.segments) ? ln.segments.join('-') : (ln.segments || '');
      return `
      <tr class="border-t border-zinc-800 acct-je-line" data-idx="${idx}">
        <td class="p-1"><select class="acct-je-acct w-full bg-zinc-800 border border-zinc-700 rounded px-1 py-1 text-xs">${accountOptions(accounts, ln.account_id)}</select></td>
        <td class="p-1"><input type="text" class="acct-je-seg w-full bg-zinc-800 border border-zinc-700 rounded px-1 py-1 text-xs font-mono" value="${esc(segVal)}" placeholder="seg-seg-seg" title="Segments"></td>
        <td class="p-1"><select class="acct-je-loc w-full bg-zinc-800 border border-zinc-700 rounded px-1 py-1 text-xs">${locOpts(ln.location_id)}</select></td>
        <td class="p-1"><input type="text" class="acct-je-desc w-full bg-zinc-800 border border-zinc-700 rounded px-1 py-1 text-xs" value="${esc(ln.description || '')}"></td>
        <td class="p-1 w-24"><input type="number" step="0.01" class="acct-je-debit w-full bg-zinc-800 border border-zinc-700 rounded px-1 py-1 text-xs text-right" value="${ln.debit || ''}"></td>
        <td class="p-1 w-24"><input type="number" step="0.01" class="acct-je-credit w-full bg-zinc-800 border border-zinc-700 rounded px-1 py-1 text-xs text-right" value="${ln.credit || ''}"></td>
        <td class="p-1 w-8"><button type="button" class="acct-je-rm text-red-400 text-xs" title="Remove line">×</button></td>
      </tr>`;
    }).join('');

    const body = `
      <div class="space-y-3 text-sm">
        <div class="grid md:grid-cols-2 gap-2">
          <div><label class="block text-xs text-zinc-400 mb-1">Batch date</label><input type="date" id="acctJeDate" class="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm" value="${esc(batch.batch_date || todayIso())}"></div>
          <div><label class="block text-xs text-zinc-400 mb-1">Source</label>
            <select id="acctJeSource" class="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm">
              ${['GL', 'AP', 'AR', 'BK', 'JC', 'PR'].map((s) => `<option${batch.source === s ? ' selected' : ''}>${s}</option>`).join('')}
            </select></div>
        </div>
        <div><label class="block text-xs text-zinc-400 mb-1">Description</label>
          <input type="text" id="acctJeDesc" class="w-full bg-zinc-800 border border-zinc-700 rounded px-2 py-1.5 text-sm" value="${esc(batch.description || '')}" placeholder="Journal entry description"></div>
        <div class="overflow-x-auto border border-zinc-700 rounded-lg">
          <table class="w-full text-xs"><thead class="bg-zinc-800 text-zinc-400"><tr>
            <th class="text-left p-2">Account</th><th class="text-left p-2">Segments</th><th class="text-left p-2">Location</th>
            <th class="text-left p-2">Line description</th><th class="text-right p-2">Debit</th><th class="text-right p-2">Credit</th><th></th>
          </tr></thead><tbody id="acctJeLines">${renderLines()}</tbody></table>
        </div>
        <button type="button" id="acctJeAddLine" class="text-xs text-emerald-400">+ Add line</button>
        <p id="acctJeBalance" class="text-xs text-zinc-500 font-mono"></p>
      </div>`;

    const dialog = openWorkspaceDialog(
      batchId ? `Edit journal ${batch.batch_number}` : 'New journal entry',
      body,
      `<button type="button" class="casepm-dialog-btn casepm-dialog-btn-secondary" data-act="cancel">Cancel</button>
       <button type="button" class="casepm-dialog-btn casepm-dialog-btn-primary" data-act="save">Save batch</button>`,
      'min(820px, 98vw)',
    );
    if (!dialog) return;

    const tbody = dialog.querySelector('#acctJeLines');
    const balanceEl = dialog.querySelector('#acctJeBalance');

    function recalcBalance() {
      let d = 0;
      let c = 0;
      tbody.querySelectorAll('.acct-je-line').forEach((row) => {
        d += parseFloat(row.querySelector('.acct-je-debit')?.value || 0) || 0;
        c += parseFloat(row.querySelector('.acct-je-credit')?.value || 0) || 0;
      });
      const diff = Math.round((d - c) * 100) / 100;
      balanceEl.textContent = `Debits ${money(d)} · Credits ${money(c)} · ${diff === 0 ? 'In balance' : `Out of balance by ${money(diff)}`}`;
      balanceEl.className = `text-xs font-mono ${diff === 0 ? 'text-emerald-400' : 'text-amber-400'}`;
    }

    function wireLine(row) {
      row.querySelectorAll('input').forEach((inp) => inp.addEventListener('input', recalcBalance));
      row.querySelector('.acct-je-rm')?.addEventListener('click', () => {
        if (tbody.querySelectorAll('.acct-je-line').length <= 2) return;
        row.remove();
        recalcBalance();
      });
    }
    tbody.querySelectorAll('.acct-je-line').forEach(wireLine);
    recalcBalance();

    dialog.querySelector('#acctJeAddLine')?.addEventListener('click', () => {
      const idx = tbody.querySelectorAll('.acct-je-line').length;
      const tr = document.createElement('tr');
      tr.className = 'border-t border-zinc-800 acct-je-line';
      tr.dataset.idx = String(idx);
      tr.innerHTML = `
        <td class="p-1"><select class="acct-je-acct w-full bg-zinc-800 border border-zinc-700 rounded px-1 py-1 text-xs">${accountOptions(accounts, accounts[0]?.id)}</select></td>
        <td class="p-1"><input type="text" class="acct-je-seg w-full bg-zinc-800 border border-zinc-700 rounded px-1 py-1 text-xs font-mono" placeholder="seg-seg-seg"></td>
        <td class="p-1"><select class="acct-je-loc w-full bg-zinc-800 border border-zinc-700 rounded px-1 py-1 text-xs">${locOpts()}</select></td>
        <td class="p-1"><input type="text" class="acct-je-desc w-full bg-zinc-800 border border-zinc-700 rounded px-1 py-1 text-xs"></td>
        <td class="p-1 w-24"><input type="number" step="0.01" class="acct-je-debit w-full bg-zinc-800 border border-zinc-700 rounded px-1 py-1 text-xs text-right"></td>
        <td class="p-1 w-24"><input type="number" step="0.01" class="acct-je-credit w-full bg-zinc-800 border border-zinc-700 rounded px-1 py-1 text-xs text-right"></td>
        <td class="p-1 w-8"><button type="button" class="acct-je-rm text-red-400 text-xs">×</button></td>`;
      tbody.appendChild(tr);
      wireLine(tr);
      recalcBalance();
    });

    dialog.querySelector('[data-act="cancel"]')?.addEventListener('click', () => closeWorkspaceDialog(dialog));
    dialog.querySelector('[data-act="save"]')?.addEventListener('click', async () => {
      const lines = [];
      tbody.querySelectorAll('.acct-je-line').forEach((row) => {
        const segRaw = row.querySelector('.acct-je-seg')?.value?.trim() || '';
        const segs = segRaw ? segRaw.replace('.', '-').split('-').map((s) => s.trim()).filter(Boolean) : null;
        const loc = row.querySelector('.acct-je-loc')?.value;
        lines.push({
          account_id: parseInt(row.querySelector('.acct-je-acct')?.value, 10),
          description: row.querySelector('.acct-je-desc')?.value?.trim() || '',
          debit: parseFloat(row.querySelector('.acct-je-debit')?.value || 0) || 0,
          credit: parseFloat(row.querySelector('.acct-je-credit')?.value || 0) || 0,
          location_id: loc ? parseInt(loc, 10) : null,
          segments: segs,
        });
      });
      const payload = {
        description: dialog.querySelector('#acctJeDesc')?.value?.trim() || '',
        batch_date: dialog.querySelector('#acctJeDate')?.value || todayIso(),
        source: dialog.querySelector('#acctJeSource')?.value || 'GL',
        lines,
      };
      try {
        if (batchId) {
          await api(`/api/accounting/gl/batches/${batchId}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
        } else {
          await api('/api/accounting/gl/batches', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          });
        }
        closeWorkspaceDialog(dialog);
        switchModule('gl');
      } catch (e) {
        await AD().alert(e.message, 'error');
      }
    });
  }

  async function openAccountRegister(accountId) {
    const { api, esc, money } = ctx;
    const data = await api(`/api/accounting/gl/accounts/${accountId}/register`);
    const rows = (data.transactions || []).map((t) => `
      <tr class="border-t border-zinc-800 text-xs">
        <td class="px-2 py-1">${esc(t.batch_date)}</td>
        <td class="px-2 py-1 font-mono">${esc(t.batch_number)}</td>
        <td class="px-2 py-1">${esc(t.source)}</td>
        <td class="px-2 py-1">${esc(t.line_description || t.reference)}</td>
        <td class="px-2 py-1 text-right">${money(t.debit)}</td>
        <td class="px-2 py-1 text-right">${money(t.credit)}</td>
      </tr>`).join('');
    const body = `
      <p class="text-sm text-zinc-300 mb-2 font-mono">${esc(data.account.account_number)} — ${esc(data.account.description)}</p>
      <p class="text-xs text-zinc-500 mb-3">Posted activity · Balance ${money(data.totals?.balance)}</p>
      <div class="max-h-64 overflow-y-auto border border-zinc-700 rounded-lg bg-zinc-900/80">
        <table class="acct-dialog-table text-xs"><thead class="bg-zinc-800 sticky top-0"><tr>
          <th class="text-left px-2 py-1">Date</th><th class="text-left px-2 py-1">Batch</th><th class="text-left px-2 py-1">Src</th>
          <th class="text-left px-2 py-1">Description</th><th class="text-right px-2 py-1">Debit</th><th class="text-right px-2 py-1">Credit</th>
        </tr></thead><tbody>${rows || '<tr><td colspan="6" class="p-3 text-zinc-500">No posted transactions on this account.</td></tr>'}</tbody></table>
      </div>`;
    const dialog = openWorkspaceDialog('Account inquiry', body, '<button type="button" class="casepm-dialog-btn casepm-dialog-btn-primary" data-act="close">Close</button>');
    dialog?.querySelector('[data-act="close"]')?.addEventListener('click', () => closeWorkspaceDialog(dialog));
  }

  async function render() {
    const { api, esc, money } = ctx;
    const [acct, batches, options, tb] = await Promise.all([
      api('/api/accounting/gl/accounts'),
      api('/api/accounting/gl/batches'),
      api('/api/accounting/gl/options'),
      api('/api/accounting/reports/trial-balance'),
    ]);
    const accounts = acct.accounts || [];
    const closed = (options.closed_periods || []).join(', ') || 'none';
    return `<div class="space-y-6">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 class="text-lg font-semibold text-white">General Ledger</h2>
          <p class="text-xs text-zinc-500 mt-1">Chart of accounts, journal batches, account inquiry, and fiscal period control (Sage 300 G/L–style).</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button type="button" id="acctNewJe" class="px-3 py-2 bg-emerald-600 hover:bg-emerald-500 rounded-md text-sm font-medium">+ Journal entry</button>
          <button type="button" id="acctGlOptions" class="px-3 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-md text-sm">G/L options</button>
        </div>
      </div>
      <div class="grid lg:grid-cols-3 gap-4">
        <div class="lg:col-span-2 border border-zinc-700 rounded-lg overflow-hidden">
          <div class="px-3 py-2 bg-zinc-800 flex justify-between items-center">
            <span class="text-xs text-zinc-400 uppercase tracking-wide">Chart of accounts</span>
            <button type="button" id="acctAddAccount" class="text-xs text-emerald-400">+ Account</button>
          </div>
          <div class="max-h-72 overflow-y-auto">
            <table class="w-full text-sm"><thead class="bg-zinc-900 text-zinc-500 text-xs sticky top-0"><tr>
              <th class="text-left px-3 py-2">Number</th><th class="text-left px-3 py-2">Description</th>
              <th class="text-left px-3 py-2">Type</th><th class="text-left px-3 py-2">Status</th><th></th>
            </tr></thead><tbody>
              ${accounts.map((a) => `<tr class="border-t border-zinc-800 hover:bg-zinc-800/40">
                <td class="px-3 py-2 font-mono">${esc(a.account_number)}</td>
                <td class="px-3 py-2">${esc(a.description)}</td>
                <td class="px-3 py-2 text-xs">${esc(a.account_type)}</td>
                <td class="px-3 py-2 text-xs">${esc(a.status)}</td>
                <td class="px-3 py-2 text-right whitespace-nowrap">
                  <button type="button" class="text-sky-400 text-xs acct-gl-inquiry" data-id="${a.id}">Inquiry</button>
                </td></tr>`).join('')}
            </tbody></table>
          </div>
        </div>
        <div class="border border-zinc-700 rounded-lg p-3 text-xs text-zinc-400 space-y-2">
          <div class="font-medium text-zinc-300">Ledger options</div>
          <div>Currency: <span class="text-zinc-200">${esc(options.base_currency)}</span></div>
          <div>Segment slots: <span class="text-zinc-200">${options.segment_count}</span></div>
          <div>Closed periods: <span class="text-zinc-200 font-mono">${esc(closed)}</span></div>
          <div class="pt-2 border-t border-zinc-800 text-zinc-500">Trial balance (posted)</div>
          <div class="max-h-40 overflow-y-auto font-mono text-[11px]">
            ${(tb.rows || []).filter((r) => r.debit || r.credit).slice(0, 12).map((r) =>
              `<div class="flex justify-between gap-2"><span>${esc(r.account_number)}</span><span>${money(r.balance)}</span></div>`
            ).join('') || '<div>No activity</div>'}
          </div>
        </div>
      </div>
      <section>
        <h3 class="text-sm font-semibold text-white mb-2">Journal batches</h3>
        <div class="overflow-x-auto border border-zinc-700 rounded-lg">
          <table class="w-full text-sm"><thead class="bg-zinc-800 text-xs text-zinc-400"><tr>
            <th class="px-3 py-2 text-left">Batch</th><th class="px-3 py-2 text-left">Date</th><th class="px-3 py-2 text-left">Source</th>
            <th class="px-3 py-2 text-left">Description</th><th class="px-3 py-2 text-left">Status</th><th class="px-3 py-2"></th>
          </tr></thead><tbody>
            ${(batches.batches || []).map((b) => `<tr class="border-t border-zinc-800">
              <td class="px-3 py-2 font-mono text-xs">${esc(b.batch_number)}</td>
              <td class="px-3 py-2 text-xs">${esc(b.batch_date)}</td>
              <td class="px-3 py-2 text-xs">${esc(b.source)}</td>
              <td class="px-3 py-2 text-xs truncate max-w-[200px]">${esc(b.description)}</td>
              <td class="px-3 py-2 text-xs">${esc(b.status)}</td>
              <td class="px-3 py-2 text-right whitespace-nowrap text-xs">
                ${b.status === 'Open' ? `
                  <button type="button" class="text-sky-400 acct-gl-edit-batch" data-id="${b.id}">Edit</button>
                  <button type="button" class="text-emerald-400 ml-2" data-post-batch="${b.id}">Post</button>
                  <button type="button" class="text-red-400 ml-2 acct-gl-del-batch" data-id="${b.id}">Delete</button>` : ''}
              </td></tr>`).join('') || '<tr><td colspan="6" class="p-4 text-zinc-500 text-sm">No journal batches yet.</td></tr>'}
          </tbody></table>
        </div>
      </section>
      ${global.CasePMAcctGlApArExt ? '<div id="acctGlExtRoot"></div>' : ''}
    </div>`;
  }

  async function appendGlExtras() {
    if (!global.CasePMAcctGlApArExt || !ctx) return;
    global.CasePMAcctGlApArExt.init(ctx);
    const root = document.getElementById('acctGlExtRoot');
    if (root) {
      root.innerHTML = await global.CasePMAcctGlApArExt.glExtrasHtml();
      global.CasePMAcctGlApArExt.bindGlExtras();
    }
  }

  function bindHandlers() {
    const { api, switchModule, AD } = ctx;
    document.getElementById('acctNewJe')?.addEventListener('click', () => openJournalEditor(null));
    document.querySelectorAll('.acct-gl-edit-batch').forEach((btn) => {
      btn.addEventListener('click', () => openJournalEditor(parseInt(btn.getAttribute('data-id'), 10)));
    });
    document.querySelectorAll('.acct-gl-del-batch').forEach((btn) => {
      btn.addEventListener('click', async () => {
        if (!await AD().confirm('Delete this open journal batch?', { title: 'Delete batch' })) return;
        await api(`/api/accounting/gl/batches/${btn.getAttribute('data-id')}`, { method: 'DELETE' });
        switchModule('gl');
      });
    });
    document.querySelectorAll('.acct-gl-inquiry').forEach((btn) => {
      btn.addEventListener('click', () => openAccountRegister(parseInt(btn.getAttribute('data-id'), 10)));
    });
    document.getElementById('acctAddAccount')?.addEventListener('click', async () => {
      const data = await AD().form({
        title: 'Add G/L account',
        fields: [
          { key: 'account_number', label: 'Account number', required: true },
          { key: 'description', label: 'Description', required: true },
          {
            key: 'account_type',
            label: 'Account type',
            type: 'select',
            defaultValue: 'expense',
            options: [
              { value: 'asset', label: 'Asset' },
              { value: 'liability', label: 'Liability' },
              { value: 'equity', label: 'Equity' },
              { value: 'revenue', label: 'Revenue' },
              { value: 'expense', label: 'Expense' },
            ],
          },
          {
            key: 'normal_balance',
            label: 'Normal balance',
            type: 'select',
            defaultValue: 'debit',
            options: [{ value: 'debit', label: 'Debit' }, { value: 'credit', label: 'Credit' }],
          },
        ],
      });
      if (!data) return;
      await api('/api/accounting/gl/accounts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      });
      switchModule('gl');
    });
    document.getElementById('acctGlOptions')?.addEventListener('click', async () => {
      const opts = await api('/api/accounting/gl/options');
      const data = await AD().form({
        title: 'G/L options',
        message: 'Close fiscal periods using YYYY-MM (posting blocked for closed months).',
        fields: [
          { key: 'segment_count', label: 'Account segment count (1–10)', type: 'number', defaultValue: String(opts.segment_count || 3) },
          { key: 'closed_periods', label: 'Closed periods (comma-separated YYYY-MM)', defaultValue: (opts.closed_periods || []).join(', ') },
          { key: 'fiscal_year_end_month', label: 'Fiscal year-end month (1–12)', type: 'number', defaultValue: String(opts.fiscal_year_end_month || 12) },
        ],
        submitLabel: 'Save options',
      });
      if (!data) return;
      const closed = (data.closed_periods || '').split(',').map((s) => s.trim()).filter(Boolean);
      await api('/api/accounting/gl/options', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          segment_count: parseInt(data.segment_count, 10),
          closed_periods: closed,
          fiscal_year_end_month: parseInt(data.fiscal_year_end_month, 10),
        }),
      });
      switchModule('gl');
    });
  }

  global.CasePMAcctGLUI = {
    init(context) {
      ctx = context;
    },
    render: async function renderGl() {
      const html = await render();
      setTimeout(() => { appendGlExtras(); }, 0);
      return html;
    },
    bindHandlers,
    openJournalEditor,
  };
})(window);
