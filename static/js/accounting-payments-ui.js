/**
 * Payment Processing — AP batches, MICR export, Pay Now links, processor settings.
 */
(function (global) {
  'use strict';

  let ctx = null;

  function AD() {
    return global.CasePMAccountingDialog || {};
  }

  async function render() {
    const { api, esc, money } = ctx;
    try {
      const [settings, batches, links, banks, apInvoices, stripeBanner] = await Promise.all([
      api('/api/accounting/payments/settings'),
      api('/api/accounting/payments/batches'),
      api('/api/accounting/payments/pay-now-links'),
      api('/api/accounting/bank/accounts').catch(() => ({ accounts: [] })),
      api('/api/accounting/ap/invoices').catch(() => ({ invoices: [] })),
      api('/api/accounting/integrations/stripe-banner').catch(() => ({ level: 'ok', messages: [] })),
    ]);
    const openAp = (apInvoices.invoices || []).filter((d) => ['Open', 'Partial'].includes(d.status));
    const arInvoices = await api('/api/accounting/ar/invoices').catch(() => ({ invoices: [] }));
    const openAr = (arInvoices.invoices || []).filter((d) => {
      const open = (parseFloat(d.amount) || 0) - (parseFloat(d.amount_paid) || 0);
      return open > 0.01;
    });

    return `<div class="space-y-6">
      ${(stripeBanner.messages || []).length ? `<div class="text-xs border border-amber-800 bg-amber-950/30 text-amber-200 rounded p-2">${(stripeBanner.messages || []).map((m) => esc(m)).join('<br>')}</div>` : ''}
      <div class="flex flex-wrap justify-between gap-2 items-start">
        <div>
          <h2 class="text-lg font-semibold text-white">Payment Processing</h2>
          <p class="text-xs text-zinc-500 mt-1">AP payment batches, check MICR export, customer Pay Now links, processor settings.</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <button type="button" id="acctPpSettings" class="text-xs px-3 py-2 border border-zinc-700 rounded-md text-zinc-300">Processor settings</button>
          <button type="button" id="acctPpNewBatch" class="text-xs px-3 py-2 bg-violet-600 hover:bg-violet-500 rounded-md text-white">+ Payment batch</button>
          <button type="button" id="acctPpPayNow" class="text-xs px-3 py-2 border border-emerald-700 rounded-md text-emerald-400">+ Pay Now link</button>
          <button type="button" id="acctPpStripeTest" class="text-xs px-3 py-2 border border-violet-700 rounded-md text-violet-400">Stripe test intent</button>
          <button type="button" id="acctPpPlaidImport" class="text-xs px-3 py-2 border border-cyan-700 rounded-md text-cyan-400">Plaid import (7d)</button>
          <button type="button" id="acctPpExceptions" class="text-xs px-3 py-2 border border-red-800 rounded-md text-red-300">Payment exceptions</button>
        </div>
      </div>

      <div class="grid md:grid-cols-3 gap-3 text-xs">
        <div class="p-3 rounded-lg border border-zinc-700 bg-zinc-900/50">
          <div class="text-zinc-500">Processor</div>
          <div class="text-white font-medium">${esc(settings.processor || 'none')}</div>
        </div>
        <div class="p-3 rounded-lg border border-zinc-700 bg-zinc-900/50">
          <div class="text-zinc-500">Pay Now</div>
          <div class="text-white font-medium">${settings.enable_pay_now ? 'Enabled' : 'Disabled'}</div>
        </div>
        <div class="p-3 rounded-lg border border-zinc-700 bg-zinc-900/50">
          <div class="text-zinc-500">Open AP for batches</div>
          <div class="text-white font-medium">${openAp.length} invoice(s)</div>
        </div>
        <div class="p-3 rounded-lg border border-zinc-700 bg-zinc-900/50 md:col-span-1">
          <div class="text-zinc-500">Card processing</div>
          <div id="acctPpStripeStatus" class="text-white font-medium text-xs">Loading…</div>
        </div>
      </div>

      <div>
        <h3 class="text-sm text-zinc-400 mb-2">Payment batches</h3>
        <div class="border border-zinc-700 rounded-lg overflow-x-auto">
          <table class="w-full text-xs">
            <thead class="bg-zinc-800 text-zinc-500"><tr>
              <th class="text-left px-2 py-2">Batch</th>
              <th class="text-left px-2 py-2">Date</th>
              <th class="text-left px-2 py-2">Method</th>
              <th class="text-right px-2 py-2">Total</th>
              <th class="text-left px-2 py-2">Status</th>
              <th class="text-right px-2 py-2">Actions</th>
            </tr></thead>
            <tbody>
              ${(batches.batches || []).map((b) => `<tr class="border-t border-zinc-800">
                <td class="px-2 py-2 font-mono text-emerald-400">${esc(b.batch_number)}</td>
                <td class="px-2 py-2">${esc(b.payment_date)}</td>
                <td class="px-2 py-2">${esc(b.payment_method)}</td>
                <td class="px-2 py-2 text-right font-mono">${money(b.total_amount)}</td>
                <td class="px-2 py-2">${esc(b.status)}</td>
                <td class="px-2 py-2 text-right space-x-2">
                  ${b.status === 'Open' ? `<button type="button" class="acct-pp-post text-emerald-400 bg-transparent border-none cursor-pointer" data-id="${b.id}">Post</button>` : ''}
                  ${b.status === 'Posted' ? `<button type="button" class="acct-pp-micr text-violet-400 bg-transparent border-none cursor-pointer" data-id="${b.id}">MICR CSV</button>` : ''}
                </td>
              </tr>`).join('') || '<tr><td colspan="6" class="p-3 text-zinc-500">No batches yet.</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <h3 class="text-sm text-zinc-400 mb-2">Pay Now links</h3>
        <div class="border border-zinc-700 rounded-lg max-h-48 overflow-y-auto divide-y divide-zinc-800 text-xs">
          ${(links.links || []).map((l) => {
            const url = `${global.location.origin}/pay-now/${encodeURIComponent(l.token)}`;
            return `<div class="p-2 flex flex-wrap justify-between gap-2 items-center">
              <div>
                <span class="text-zinc-300">AR #${esc(l.ar_document_id)}</span>
                <span class="text-zinc-500 ml-2">${money(l.amount)} · ${esc(l.status)}</span>
              </div>
              <div class="flex gap-2 items-center">
                ${l.status === 'Pending' ? `<a class="text-sky-400" href="/pay-now/${encodeURIComponent(l.token)}" target="_blank" rel="noopener">Open checkout</a>
                <button type="button" class="acct-pp-complete text-emerald-400 bg-transparent border-none cursor-pointer" data-token="${esc(l.token)}">Simulate pay</button>` : ''}
                <span class="font-mono text-[10px] text-zinc-600 truncate max-w-xs" title="${esc(url)}">${esc(l.token.slice(0, 12))}…</span>
              </div>
            </div>`;
          }).join('') || '<p class="p-3 text-zinc-500">No pay links.</p>'}
        </div>
        <p class="text-[10px] text-zinc-600 mt-1">${openAr.length} open AR invoice(s) available for new links.</p>
      </div>
    </div>`;
    } catch (e) {
      return `<p class="text-red-400 text-sm">${esc(e.message)}</p>`;
    }
  }

  function bindHandlers() {
    const { api, switchModule, esc, money } = ctx;

    document.getElementById('acctPpSettings')?.addEventListener('click', async () => {
      const cur = await api('/api/accounting/payments/settings');
      const data = await AD().form({
        title: 'Payment processor settings',
        fields: [
          { key: 'processor', label: 'Processor id', defaultValue: cur.processor || 'none' },
          { key: 'micr_company_name', label: 'MICR company name', defaultValue: cur.micr_company_name },
          { key: 'micr_bank_routing', label: 'MICR routing', defaultValue: cur.micr_bank_routing },
          { key: 'micr_bank_account', label: 'MICR account', defaultValue: cur.micr_bank_account },
          { key: 'enable_pay_now', label: 'Enable Pay Now', type: 'checkbox', defaultValue: cur.enable_pay_now },
          { key: 'default_pay_now_days', label: 'Default link days', defaultValue: String(cur.default_pay_now_days || 30) },
        ],
      });
      if (!data) return;
      await api('/api/accounting/payments/settings', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...data,
          enable_pay_now: !!data.enable_pay_now,
          default_pay_now_days: parseInt(data.default_pay_now_days, 10) || 30,
        }),
      });
      switchModule('payments');
    });

    document.getElementById('acctPpNewBatch')?.addEventListener('click', async () => {
      const [vendors, invoices, banks] = await Promise.all([
        api('/api/accounting/ap/vendors'),
        api('/api/accounting/ap/invoices'),
        api('/api/accounting/bank/accounts'),
      ]);
      const open = (invoices.invoices || []).filter((d) => ['Open', 'Partial'].includes(d.status));
      if (!open.length) {
        await AD().alert({ title: 'No open invoices', message: 'Create AP invoices before building a payment batch.' });
        return;
      }
      const pick = await AD().form({
        title: 'Add invoice to batch (first line)',
        fields: [
          {
            key: 'ap_document_id',
            label: 'Invoice',
            type: 'select',
            required: true,
            options: open.map((d) => {
              const v = (vendors.vendors || []).find((x) => x.id === d.vendor_id);
              const openAmt = (parseFloat(d.amount) || 0) - (parseFloat(d.amount_paid) || 0);
              return { value: String(d.id), label: `${d.document_number} — ${v?.name || ''} (${money(openAmt)})` };
            }),
          },
          { key: 'payment_date', label: 'Payment date', type: 'date', defaultValue: new Date().toISOString().slice(0, 10) },
          { key: 'payment_method', label: 'Method', defaultValue: 'Check' },
          { key: 'check_number_start', label: 'Starting check #', defaultValue: '1001' },
          {
            key: 'bank_account_id',
            label: 'Bank account',
            type: 'select',
            options: [{ value: '', label: '—' }].concat(
              (banks.accounts || []).map((b) => ({ value: String(b.id), label: `${b.code} — ${b.name}` })),
            ),
          },
        ],
      });
      if (!pick) return;
      const doc = open.find((d) => String(d.id) === String(pick.ap_document_id));
      const amt = Math.round(((parseFloat(doc.amount) || 0) - (parseFloat(doc.amount_paid) || 0)) * 100) / 100;
      await api('/api/accounting/payments/batches', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          payment_date: pick.payment_date,
          payment_method: pick.payment_method,
          check_number_start: pick.check_number_start,
          bank_account_id: pick.bank_account_id ? parseInt(pick.bank_account_id, 10) : null,
          lines: [{ vendor_id: doc.vendor_id, ap_document_id: doc.id, amount: amt }],
        }),
      });
      switchModule('payments');
    });

    document.getElementById('acctPpPayNow')?.addEventListener('click', async () => {
      const ar = await api('/api/accounting/ar/invoices');
      const open = (ar.invoices || []).filter((d) => {
        const o = (parseFloat(d.amount) || 0) - (parseFloat(d.amount_paid) || 0);
        return o > 0.01;
      });
      if (!open.length) {
        await AD().alert({ title: 'No open AR', message: 'Post AR invoices with open balance first.' });
        return;
      }
      const data = await AD().form({
        title: 'Create Pay Now link',
        fields: [
          {
            key: 'ar_document_id',
            label: 'Invoice',
            type: 'select',
            required: true,
            options: open.map((d) => ({ value: String(d.id), label: d.document_number })),
          },
          { key: 'days_valid', label: 'Valid days', defaultValue: '30' },
          { key: 'payment_method', label: 'Method (card/ach)', defaultValue: 'card' },
        ],
      });
      if (!data) return;
      await api('/api/accounting/payments/pay-now-links', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ar_document_id: parseInt(data.ar_document_id, 10),
          days_valid: parseInt(data.days_valid, 10) || 30,
          payment_method: data.payment_method,
        }),
      });
      switchModule('payments');
    });

    document.querySelectorAll('.acct-pp-post').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const id = btn.getAttribute('data-id');
        if (!await AD().confirm({ title: 'Post batch?', message: 'Creates AP payments and G/L entries.' })) return;
        await api(`/api/accounting/payments/batches/${id}/post`, { method: 'POST' });
        switchModule('payments');
      });
    });

    document.querySelectorAll('.acct-pp-micr').forEach((btn) => {
      btn.addEventListener('click', () => {
        const id = btn.getAttribute('data-id');
        global.location.href = `/api/accounting/payments/batches/${id}/micr?format=csv`;
      });
    });

    document.querySelectorAll('.acct-pp-complete').forEach((btn) => {
      btn.addEventListener('click', async () => {
        const token = btn.getAttribute('data-token');
        await api(`/api/accounting/payments/pay-now/${token}/complete`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        });
        switchModule('payments');
      });
    });

    document.getElementById('acctPpStripeTest')?.addEventListener('click', async () => {
      const out = await api('/api/accounting/payments/stripe-intent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ amount: 100, currency: 'usd', metadata: { test: true } }),
      });
      await AD().alert(`Test intent: ${out.client_secret}`, 'info');
    });
    document.getElementById('acctPpPlaidImport')?.addEventListener('click', async () => {
      const out = await api('/api/accounting/bank/plaid-auto-import', { method: 'POST', body: '{}' });
      await AD().alert(out.skipped ? `Skipped: ${out.skipped}` : `Imported ${out.imported || out.count || 0} transaction(s).`, 'info');
      switchModule('payments');
    });
    document.getElementById('acctPpExceptions')?.addEventListener('click', async () => {
      const box = await api('/api/accounting/payments/exceptions');
      const n = (box.exceptions || []).length;
      const retry = n ? await AD().confirm(`${n} exception(s). Retry Pay Now captures now?`, 'Payments') : false;
      if (retry) {
        const r = await api('/api/accounting/payments/exceptions/reconcile', { method: 'POST', body: '{}' });
        await AD().alert(`Fixed ${r.fixed || 0}; ${r.remaining || 0} remaining.`, 'info');
      } else {
        await AD().alert(n ? `${n} payment exception(s) on file.` : 'No payment exceptions.', 'info');
      }
    });
  }

  global.CasePMAcctPaymentsUI = {
    init(c) {
      ctx = c;
    },
    render,
    bindHandlers,
  };
})(typeof window !== 'undefined' ? window : global);
