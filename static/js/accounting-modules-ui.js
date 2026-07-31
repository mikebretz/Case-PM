/**
 * Rich UI panels for Tax, Fixed Assets, Inventory, PO, OE (loaded after accounting-app helpers).
 */
(function (global) {
  'use strict';

  function helpers() {
    const A = global.CasePMAccounting || {};
    return {
      api: A._api,
      esc: A._esc,
      money: A._money,
      switchModule: A.switchModule,
      projectId: A._projectId,
    };
  }

  async function renderTax() {
    const { api, esc, money } = helpers();
    const [groups, summary] = await Promise.all([
      api('/api/accounting/tax/groups'),
      api('/api/accounting/tax/summary'),
    ]);
    const rows = (groups.groups || []).map((g) =>
      `<tr class="border-t border-zinc-800 ${g.is_active ? '' : 'opacity-50'}">
        <td class="px-3 py-2 font-mono text-xs">${esc(g.code)}</td>
        <td class="px-3 py-2">${esc(g.description)}</td>
        <td class="px-3 py-2 text-xs">${esc(g.tax_type)}</td>
        <td class="px-3 py-2 text-xs">${esc(g.applies_to)}</td>
        <td class="px-3 py-2 text-right">${g.rate_percent}%</td>
        <td class="px-3 py-2 text-xs text-zinc-500">${esc(g.authority)}</td>
        <td class="px-3 py-2 text-right"><button type="button" class="text-amber-400 text-xs acct-tax-edit" data-id="${g.id}">Edit</button></td>
      </tr>`
    ).join('');
    return `<div class="space-y-6">
      <div class="flex flex-wrap justify-between gap-2 items-center">
        <h2 class="text-lg font-semibold text-white">Tax Services</h2>
        <button type="button" id="acctAddTax" class="text-xs text-emerald-400">+ Tax group</button>
      </div>
      <p class="text-xs text-zinc-500">Sales / use / withholding groups for AP and AR documents. Assign tax group codes on vendors in Accounts Payable.</p>
      <div class="grid md:grid-cols-3 gap-3 text-sm">
        <div class="bg-zinc-800 border border-zinc-700 rounded-lg p-3"><div class="text-zinc-500 text-xs">Active tax groups</div><div class="text-xl">${(groups.groups || []).filter((g) => g.is_active).length}</div></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded-lg p-3"><div class="text-zinc-500 text-xs">Open A/P (tax base est.)</div><div class="text-xl">${money(summary.open_ap_base)}</div></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded-lg p-3"><div class="text-zinc-500 text-xs">Vendors with tax group</div><div class="text-xl">${Object.values(summary.vendors_by_tax_group || {}).reduce((a, b) => a + b, 0)}</div></div>
      </div>
      <div class="border border-zinc-700 rounded-lg overflow-x-auto">
        <table class="w-full text-sm"><thead class="bg-zinc-800 text-xs text-zinc-400"><tr>
          <th class="text-left px-3 py-2">Code</th><th class="text-left px-3 py-2">Description</th><th class="text-left px-3 py-2">Type</th>
          <th class="text-left px-3 py-2">Applies</th><th class="text-right px-3 py-2">Rate</th><th class="text-left px-3 py-2">Authority</th><th></th>
        </tr></thead><tbody>${rows || '<tr><td colspan="7" class="p-4 text-zinc-500">No tax groups — add state / local rates.</td></tr>'}</tbody></table>
      </div>
      <div class="bg-zinc-800/40 border border-zinc-700 rounded-lg p-4">
        <h3 class="text-sm font-medium text-zinc-300 mb-2">Tax calculator</h3>
        <div class="flex flex-wrap gap-2 items-end">
          <div><label class="text-xs text-zinc-500 block">Amount</label><input id="acctTaxCalcAmt" type="number" step="0.01" class="bg-zinc-900 border border-zinc-600 rounded px-2 py-1 text-sm w-32" value="1000"></div>
          <div><label class="text-xs text-zinc-500 block">Tax group code</label><input id="acctTaxCalcCode" class="bg-zinc-900 border border-zinc-600 rounded px-2 py-1 text-sm w-28 font-mono" placeholder="FL-SALES"></div>
          <button type="button" id="acctTaxCalcBtn" class="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 rounded text-sm">Calculate</button>
        </div>
        <pre id="acctTaxCalcOut" class="text-xs text-zinc-400 mt-2 font-mono"></pre>
      </div>
    </div>`;
  }

  async function renderAssets() {
    const { api, esc, money } = helpers();
    const [assets, runs] = await Promise.all([
      api('/api/accounting/assets'),
      api('/api/accounting/assets/depreciation-runs'),
    ]);
    const totalCost = (assets.assets || []).reduce((s, a) => s + (a.acquisition_cost || 0), 0);
    const totalNbv = (assets.assets || []).reduce((s, a) => s + (a.net_book_value || 0), 0);
    const rows = (assets.assets || []).map((a) =>
      `<tr class="border-t border-zinc-800">
        <td class="px-3 py-2 font-mono text-xs">${esc(a.asset_number)}</td>
        <td class="px-3 py-2">${esc(a.description)}</td>
        <td class="px-3 py-2 text-xs">${esc(a.location)}</td>
        <td class="px-3 py-2 text-right">${money(a.acquisition_cost)}</td>
        <td class="px-3 py-2 text-right">${money(a.accumulated_depreciation)}</td>
        <td class="px-3 py-2 text-right font-medium text-emerald-400">${money(a.net_book_value)}</td>
        <td class="px-3 py-2 text-xs">${a.useful_life_months} mo · ${money(a.monthly_depreciation)}/mo</td>
        <td class="px-3 py-2 text-xs">${esc(a.status)}</td>
        <td class="px-3 py-2 text-right whitespace-nowrap">
          ${a.status === 'Active' || a.status === 'Fully Depreciated' ? `<button type="button" class="text-red-400 text-xs acct-asset-dispose" data-id="${a.id}">Dispose</button>` : ''}
        </td>
      </tr>`
    ).join('');
    return `<div class="space-y-4">
      <div class="flex flex-wrap gap-2 items-center justify-between">
        <h2 class="text-lg font-semibold text-white">Fixed Assets</h2>
        <div class="flex gap-2">
          <button type="button" id="acctAddAsset" class="text-xs text-emerald-400">+ Asset</button>
          <button type="button" id="acctRunDep" class="text-xs text-violet-400">Run monthly depreciation</button>
        </div>
      </div>
      <div class="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
        <div class="bg-zinc-800 border border-zinc-700 rounded p-2">Cost: <strong>${money(totalCost)}</strong></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded p-2">Net book: <strong>${money(totalNbv)}</strong></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded p-2">Assets: <strong>${(assets.assets || []).length}</strong></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded p-2">Dep runs: <strong>${(runs.runs || []).length}</strong></div>
      </div>
      <div class="overflow-x-auto border border-zinc-700 rounded-lg">
        <table class="w-full text-sm"><thead class="bg-zinc-800 text-xs text-zinc-400"><tr>
          <th class="text-left px-3 py-2">Asset #</th><th class="text-left px-3 py-2">Description</th><th class="text-left px-3 py-2">Location</th>
          <th class="text-right px-3 py-2">Cost</th><th class="text-right px-3 py-2">Accum dep</th><th class="text-right px-3 py-2">NBV</th>
          <th class="text-left px-3 py-2">Schedule</th><th class="text-left px-3 py-2">Status</th><th></th>
        </tr></thead><tbody>${rows || '<tr><td colspan="9" class="p-4 text-zinc-500">No fixed assets registered.</td></tr>'}</tbody></table>
      </div>
      <div><h3 class="text-sm text-zinc-400 mb-2">Depreciation history</h3>
        <ul class="text-xs space-y-1">${(runs.runs || []).map((r) =>
          `<li class="font-mono text-zinc-500">${esc(r.run_number)} — ${money(r.total_amount)} · batch ${r.journal_batch_id || '—'}</li>`
        ).join('') || '<li class="text-zinc-600">No depreciation posted yet.</li>'}</ul>
      </div>
    </div>`;
  }

  async function renderInventory() {
    const { api, esc, money } = helpers();
    const [items, txns] = await Promise.all([
      api('/api/accounting/inventory/items'),
      api('/api/accounting/inventory/transactions'),
    ]);
    const ext = (items.items || []).reduce((s, i) => s + (i.extended_value || 0), 0);
    return `<div class="space-y-4">
      <div class="flex justify-between items-center">
        <h2 class="text-lg font-semibold text-white">Inventory Control</h2>
        <button type="button" id="acctAddItem" class="text-xs text-emerald-400">+ Item</button>
        <button type="button" id="acctIcFifo" class="text-xs text-violet-400 ml-2">FIFO issue</button>
        <button type="button" id="acctIcTransfer" class="text-xs text-sky-400 ml-2">Location transfer</button>
      </div>
      <p class="text-xs text-zinc-500">Perpetual inventory · PO receipts and manual adjustments post to quantity on hand.</p>
      <div class="text-sm bg-zinc-800 border border-zinc-700 rounded p-2 inline-block">Extended value: <strong>${money(ext)}</strong></div>
      <table class="w-full text-sm border border-zinc-700 rounded-lg"><thead class="bg-zinc-800 text-xs text-zinc-400"><tr>
        <th class="text-left px-3 py-2">Item</th><th class="text-left px-3 py-2">Description</th><th class="text-right px-3 py-2">On hand</th>
        <th class="text-right px-3 py-2">Unit cost</th><th class="text-right px-3 py-2">Value</th><th></th>
      </tr></thead><tbody>
        ${(items.items || []).map((i) => `<tr class="border-t border-zinc-800">
          <td class="px-3 py-2 font-mono">${esc(i.item_number)}</td><td class="px-3 py-2">${esc(i.description)}</td>
          <td class="px-3 py-2 text-right">${i.qty_on_hand} ${esc(i.uom)}</td>
          <td class="px-3 py-2 text-right">${money(i.unit_cost)}</td>
          <td class="px-3 py-2 text-right">${money(i.extended_value)}</td>
          <td class="px-3 py-2 text-right"><button type="button" class="text-emerald-400 text-xs acct-inv-adj" data-id="${i.id}">± Qty</button></td>
        </tr>`).join('')}
      </tbody></table>
      <h3 class="text-sm text-zinc-400">Recent transactions</h3>
      <ul class="text-xs max-h-40 overflow-y-auto border border-zinc-800 rounded p-2">${(txns.transactions || []).map((t) =>
        `<li class="py-1 border-b border-zinc-800 font-mono">${esc(t.item_number)} ${t.qty_delta > 0 ? '+' : ''}${t.qty_delta} · ${esc(t.txn_type)} ${esc(t.reference)}</li>`
      ).join('') || '<li class="text-zinc-600">No movements yet.</li>'}</ul>
    </div>`;
  }

  async function renderPO() {
    const { api, esc, money } = helpers();
    const [orders, vendors] = await Promise.all([
      api('/api/accounting/po/orders'),
      api('/api/accounting/ap/vendors'),
    ]);
    const vopts = (vendors.vendors || []).map((v) => `<option value="${v.id}">${esc(v.code)} — ${esc(v.name)}</option>`).join('');
    const cards = (orders.orders || []).map((o) => {
      const lines = (o.lines || []).map((ln, idx) =>
        `<li class="text-xs text-zinc-500">${esc(ln.description || ln.item_number || 'Line')} · qty ${ln.qty || 0} @ ${money(ln.unit_price || 0)} · rcv ${ln.qty_received || 0}</li>`
      ).join('');
      return `<div class="border border-zinc-700 rounded-lg p-3 mb-2" data-po-id="${o.id}">
        <div class="flex justify-between items-start gap-2">
          <div><span class="font-mono text-emerald-400">${esc(o.po_number)}</span> <span class="text-xs text-zinc-500">${esc(o.status)}</span>
            <div class="text-xs text-zinc-400">${esc(o.vendor_name || 'No vendor')} · ${money(o.total_amount)}</div></div>
          <button type="button" class="text-xs text-sky-400 acct-po-receive" data-id="${o.id}">Receive</button>
          <button type="button" class="text-xs text-zinc-400 acct-po-grid ml-1" data-id="${o.id}">Lines</button>
          <button type="button" class="text-xs text-amber-400 acct-po-voucher ml-1" data-id="${o.id}">AP voucher</button>
        </div>
        <ul class="mt-2">${lines || '<li class="text-xs text-zinc-600">No lines — edit PO to add material lines.</li>'}</ul>
      </div>`;
    }).join('');
    return `<div class="space-y-4">
      <h2 class="text-lg font-semibold text-white">Purchase Orders</h2>
      <button type="button" id="acctAddPO" class="text-xs text-emerald-400">+ Purchase order</button>
      <button type="button" id="acctPoBlanket" class="text-xs text-violet-400 ml-2">Blanket release</button>
      <div id="acctPOList">${cards || '<p class="text-zinc-500 text-sm">No POs.</p>'}</div>
      <datalist id="acctVendorList">${vopts}</datalist>
    </div>`;
  }

  async function renderOE() {
    const { api, esc, money } = helpers();
    const orders = await api('/api/accounting/oe/orders');
    const cards = (orders.orders || []).map((o) => {
      const lines = (o.lines || []).map((ln) =>
        `<li class="text-xs text-zinc-500">${esc(ln.description || 'Line')} · qty ${ln.qty || 0} · ship ${ln.qty_shipped || 0}</li>`
      ).join('');
      const actions = [];
      if (o.status !== 'Invoiced') {
        actions.push(`<button type="button" class="text-xs text-sky-400 acct-oe-ship" data-id="${o.id}">Ship</button>`);
        actions.push(`<button type="button" class="text-xs text-zinc-400 acct-oe-grid" data-id="${o.id}">Fulfillment</button>`);
        actions.push(`<button type="button" class="text-xs text-violet-400 acct-oe-cogs" data-id="${o.id}">Ship + COGS</button>`);
        actions.push(`<button type="button" class="text-xs text-emerald-400 acct-oe-invoice" data-id="${o.id}">Invoice A/R</button>`);
      }
      return `<div class="border border-zinc-700 rounded-lg p-3 mb-2">
        <div class="flex justify-between"><div><span class="font-mono">${esc(o.order_number)}</span> <span class="text-xs">${esc(o.status)}</span>
          <div class="text-xs text-zinc-400">${esc(o.customer_name || '')} · ${money(o.total_amount)}</div></div>
          <div class="flex gap-2">${actions.join('')}</div></div>
        <ul class="mt-2">${lines || '<li class="text-xs text-zinc-600">No lines on order.</li>'}</ul>
      </div>`;
    }).join('');
    return `<div class="space-y-4">
      <h2 class="text-lg font-semibold text-white">Order Entry / Sales</h2>
      <button type="button" id="acctAddOE" class="text-xs text-emerald-400">+ Sales order</button>
      <div>${cards || '<p class="text-zinc-500 text-sm">No sales orders.</p>'}</div>
    </div>`;
  }

  function bindTaxExtras() {
    const { api, switchModule } = helpers();
    const AD = () => global.CasePMAccountingDialog || {};
    document.getElementById('acctTaxCalcBtn')?.addEventListener('click', async () => {
      const amount = parseFloat(document.getElementById('acctTaxCalcAmt')?.value || '0');
      const code = document.getElementById('acctTaxCalcCode')?.value?.trim();
      const out = document.getElementById('acctTaxCalcOut');
      try {
        const json = await api('/api/accounting/tax/calculate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ amount, tax_group_code: code }),
        });
        out.textContent = JSON.stringify(json, null, 2);
      } catch (e) {
        out.textContent = e.message;
      }
    });
    document.querySelectorAll('.acct-tax-edit').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const rate = await AD().prompt('New rate %', '', { title: 'Edit tax rate', label: 'Rate %' });
        if (rate == null) return;
        await api(`/api/accounting/tax/groups/${btn.getAttribute('data-id')}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ rate_percent: parseFloat(rate) }),
        });
        switchModule('tax');
      });
    });
  }

  function bindAssetExtras() {
    const { api, switchModule } = helpers();
    const AD = () => global.CasePMAccountingDialog || {};
    document.querySelectorAll('.acct-asset-dispose').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const proceeds = await AD().prompt('Disposal proceeds (cash received)', '0', {
          title: 'Dispose asset',
          label: 'Proceeds',
        });
        if (proceeds == null) return;
        try {
          await api(`/api/accounting/assets/${btn.getAttribute('data-id')}/dispose`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ proceeds: parseFloat(proceeds || 0) }),
          });
          switchModule('assets');
        } catch (e) {
          await AD().alert(e.message, 'error');
        }
      });
    });
  }

  function bindPOExtras() {
    const { api, switchModule } = helpers();
    const AD = () => global.CasePMAccountingDialog || {};
    document.querySelectorAll('.acct-po-receive').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-id');
        try {
          const detail = await api(`/api/accounting/po/orders/${id}`);
          const lines = (detail.order?.lines || []).map((ln, idx) => ({
            line_index: idx,
            qty: Math.max((ln.qty || 0) - (ln.qty_received || 0), 0),
          })).filter((l) => l.qty > 0);
          await api(`/api/accounting/po/orders/${id}/receive`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lines }),
          });
          switchModule('po');
        } catch (e) {
          await AD().alert(e.message, 'error');
        }
      });
    });
    document.querySelectorAll('.acct-po-grid').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const g = await api(`/api/accounting/po/orders/${btn.getAttribute('data-id')}/line-grid`);
        const lines = (g.lines || []).map((ln) => `Line ${ln.line_index}: ${ln.description || ''} — open qty ${ln.qty_open}`).join('\n');
        await AD().alert(lines || 'No lines', 'info');
      });
    });
    document.getElementById('acctPoBlanket')?.addEventListener('click', async () => {
      const orders = await api('/api/accounting/po/orders');
      const list = orders.orders || [];
      if (!list[0]) {
        await AD().alert('Create a PO first.', 'warning');
        return;
      }
      const pick = await AD().select({
        title: 'Blanket PO',
        items: list.map((o) => ({ value: String(o.id), label: `${o.po_number} — ${o.status}` })),
      });
      if (!pick) return;
      const data = await AD().form({
        title: 'Release line',
        fields: [
          { key: 'description', label: 'Description', required: true },
          { key: 'qty', label: 'Qty', defaultValue: '1' },
          { key: 'unit_price', label: 'Unit price', defaultValue: '100' },
        ],
      });
      if (!data) return;
      await api(`/api/accounting/po/orders/${pick.value}/blanket-release`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lines: [{ description: data.description, qty: parseFloat(data.qty), unit_price: parseFloat(data.unit_price) }] }),
      });
      switchModule('po');
    });
  }

  function bindInventoryExtras() {
    const { api, switchModule } = helpers();
    const AD = () => global.CasePMAccountingDialog || {};
    document.getElementById('acctIcTransfer')?.addEventListener('click', async () => {
      const items = await api('/api/accounting/inventory/items');
      const list = items.items || [];
      if (!list[0]) return;
      const data = await AD().form({
        title: 'Inventory location transfer',
        fields: [
          { key: 'item_id', label: 'Item', type: 'select', options: list.map((i) => ({ value: String(i.id), label: i.item_number })), required: true },
          { key: 'qty', label: 'Quantity', defaultValue: '1', required: true },
          { key: 'from_location_code', label: 'From', defaultValue: 'MAIN' },
          { key: 'to_location_code', label: 'To', defaultValue: 'SITE' },
        ],
      });
      if (!data) return;
      await api('/api/accounting/inventory/transfer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          item_id: parseInt(data.item_id, 10),
          qty: parseFloat(data.qty),
          from_location_code: data.from_location_code,
          to_location_code: data.to_location_code,
        }),
      });
      switchModule('inventory');
    });
  }

  function bindOEExtras() {
    const { api, switchModule } = helpers();
    const AD = () => global.CasePMAccountingDialog || {};
    document.querySelectorAll('.acct-oe-ship').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-id');
        try {
          const detail = await api(`/api/accounting/oe/orders/${id}`);
          const lines = (detail.order?.lines || []).map((ln, idx) => ({
            line_index: idx,
            qty: Math.max((ln.qty || 0) - (ln.qty_shipped || 0), 0),
          })).filter((l) => l.qty > 0);
          await api(`/api/accounting/oe/orders/${id}/ship`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ lines }),
          });
          switchModule('oe');
        } catch (e) {
          await AD().alert(e.message, 'error');
        }
      });
    });
    document.querySelectorAll('.acct-oe-invoice').forEach((btn) => {
      btn.addEventListener('click', async () => {
        try {
          const out = await api(`/api/accounting/oe/orders/${btn.getAttribute('data-id')}/invoice`, { method: 'POST', body: '{}' });
          await AD().alert(`A/R invoice #${out.ar_document_id} created for ${out.amount}`, 'success');
          switchModule('oe');
        } catch (e) {
          await AD().alert(e.message, 'error');
        }
      });
    });
    document.querySelectorAll('.acct-oe-grid').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const g = await api(`/api/accounting/oe/orders/${btn.getAttribute('data-id')}/fulfillment-grid`);
        const lines = (g.lines || []).map((ln) => `Line ${ln.line_index}: open ship ${ln.qty_open} · comm ${ln.commission_percent}%`).join('\n');
        await AD().alert(lines || 'No lines', 'info');
      });
    });
  }

  global.CasePMAcctModulesUI = {
    renderTax,
    renderAssets,
    renderInventory,
    renderPO,
    renderOE,
    bindExtras(route) {
      if (route === 'tax') bindTaxExtras();
      if (route === 'assets') bindAssetExtras();
      if (route === 'po') bindPOExtras();
      if (route === 'oe') bindOEExtras();
      if (route === 'inventory') bindInventoryExtras();
    },
  };
})(window);
