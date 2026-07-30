/**
 * Accounting → Payroll: employees, deductions, pay runs, job-cost labor posting.
 */
(function (global) {
  'use strict';

  function h() {
    const A = global.CasePMAccounting || {};
    return { api: A._api, esc: A._esc, money: A._money, switchModule: A.switchModule, projectId: A._projectId };
  }

  async function render() {
    const { api, esc, money } = h();
    const [employees, deductions, runs] = await Promise.all([
      api('/api/accounting/payroll/employees'),
      api('/api/accounting/payroll/deductions'),
      api('/api/accounting/payroll/runs'),
    ]);
    const activeEmp = (employees.employees || []).filter((e) => e.status === 'Active');
    const openRun = (runs.runs || []).find((r) => r.status === 'Open');

    const empRows = (employees.employees || []).map((e) =>
      `<tr class="border-t border-zinc-800"><td class="px-2 py-1 font-mono text-xs">${esc(e.employee_number)}</td>
        <td class="px-2 py-1">${esc(e.name)}</td><td class="px-2 py-1 text-xs">${esc(e.pay_type)}</td>
        <td class="px-2 py-1 text-right">${e.pay_type === 'salary' ? money(e.annual_salary) + '/yr' : money(e.hourly_rate) + '/hr'}</td>
        <td class="px-2 py-1 text-xs">${esc(e.department)}</td><td class="px-2 py-1 text-xs">${esc(e.status)}</td></tr>`
    ).join('');

    const dedRows = (deductions.deductions || []).map((d) =>
      `<li class="py-1 border-b border-zinc-800 text-xs"><span class="font-mono text-emerald-400">${esc(d.code)}</span> — ${esc(d.description)}
        · ${d.calc_method === 'percent' ? d.percent + '%' : money(d.amount)} · ${esc(d.deduction_type)}</li>`
    ).join('');

    const runCards = (runs.runs || []).slice(0, 8).map((r) =>
      `<div class="border border-zinc-700 rounded p-3 mb-2 flex justify-between gap-2 items-start">
        <div><span class="font-mono text-sm">${esc(r.run_number)}</span> <span class="text-xs text-zinc-500">${esc(r.status)}</span>
          <div class="text-xs text-zinc-400 mt-1">Gross ${money(r.total_gross)} · Net ${money(r.total_net)} · Taxes ${money(r.total_taxes)}</div>
          ${r.journal_batch_id ? `<div class="text-[10px] text-zinc-600">G/L batch ${r.journal_batch_id}</div>` : ''}
        </div>
        <div class="flex flex-col gap-1">
          ${r.status === 'Open' ? `<button type="button" class="text-xs text-sky-400 acct-pr-open" data-id="${r.id}">Open</button>` : ''}
          ${r.status === 'Open' ? `<button type="button" class="text-xs text-emerald-400 acct-pr-post" data-id="${r.id}">Post G/L</button>` : ''}
        </div>
      </div>`
    ).join('');

    return `<div class="space-y-6">
      <div class="flex flex-wrap justify-between gap-2 items-center">
        <h2 class="text-lg font-semibold text-white">Payroll</h2>
        <div class="flex flex-wrap gap-2">
          <button type="button" id="acctPrAddEmp" class="text-xs px-2 py-1 bg-zinc-800 border border-zinc-600 rounded">+ Employee</button>
          <button type="button" id="acctPrAddDed" class="text-xs px-2 py-1 bg-zinc-800 border border-zinc-600 rounded">+ Deduction</button>
          <button type="button" id="acctPrNewRun" class="text-xs px-2 py-1 bg-emerald-700 rounded">+ Pay run</button>
        </div>
      </div>
      <p class="text-xs text-zinc-500">Employees, withholding, deductions, and pay runs post to G/L with <strong class="text-zinc-400">job cost labor</strong> by project. Map accounts under Program Settings → Accounting.</p>
      <div class="grid md:grid-cols-4 gap-2 text-sm">
        <div class="bg-zinc-800 border border-zinc-700 rounded p-2">Active employees: <strong>${activeEmp.length}</strong></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded p-2">Deduction codes: <strong>${(deductions.deductions || []).length}</strong></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded p-2">Open run: <strong>${openRun ? esc(openRun.run_number) : '—'}</strong></div>
        <div class="bg-zinc-800 border border-zinc-700 rounded p-2">Pay runs: <strong>${(runs.runs || []).length}</strong></div>
      </div>

      <div id="acctPrRunEditor" class="hidden border border-emerald-900/50 bg-zinc-800/40 rounded-lg p-4">
        <h3 class="text-sm font-medium text-white mb-2">Pay run editor</h3>
        <div id="acctPrRunMeta" class="text-xs text-zinc-400 mb-3"></div>
        <div class="flex flex-wrap gap-2 mb-3">
          <button type="button" id="acctPrBuild" class="text-xs px-2 py-1 bg-zinc-700 rounded">Add all active employees</button>
          <button type="button" id="acctPrCalc" class="text-xs px-2 py-1 bg-zinc-700 rounded">Recalculate</button>
          <button type="button" id="acctPrPostRun" class="text-xs px-2 py-1 bg-emerald-600 rounded">Post to G/L</button>
        </div>
        <div class="overflow-x-auto border border-zinc-700 rounded max-h-64 overflow-y-auto">
          <table class="w-full text-xs"><thead class="bg-zinc-800 sticky top-0"><tr>
            <th class="text-left px-2 py-1">Employee</th><th class="text-right px-2 py-1">Hrs</th><th class="text-right px-2 py-1">Gross</th>
            <th class="text-right px-2 py-1">Taxes</th><th class="text-right px-2 py-1">Ded</th><th class="text-right px-2 py-1">Net</th><th class="text-left px-2 py-1">Job</th>
          </tr></thead><tbody id="acctPrRunLines"></tbody></table>
        </div>
      </div>

      <div class="grid lg:grid-cols-2 gap-4">
        <div>
          <h3 class="text-sm text-zinc-400 mb-2">Employees</h3>
          <table class="w-full text-sm border border-zinc-700 rounded-lg"><tbody>${empRows || '<tr><td class="p-3 text-zinc-500">No employees — add your field and office staff.</td></tr>'}</tbody></table>
        </div>
        <div>
          <h3 class="text-sm text-zinc-400 mb-2">Deductions</h3>
          <ul class="border border-zinc-700 rounded-lg p-2">${dedRows || '<li class="text-zinc-500 text-xs">No deduction codes (401k, health, union, etc.)</li>'}</ul>
          <h3 class="text-sm text-zinc-400 mt-4 mb-2">Recent pay runs</h3>
          <div>${runCards || '<p class="text-zinc-500 text-xs">No pay runs yet.</p>'}</div>
        </div>
      </div>
    </div>`;
  }

  let currentRunId = null;

  async function loadRun(runId) {
    const { api, esc, money } = h();
    currentRunId = runId;
    const data = await api(`/api/accounting/payroll/runs/${runId}`);
    const run = data.run;
    const editor = document.getElementById('acctPrRunEditor');
    const meta = document.getElementById('acctPrRunMeta');
    const tbody = document.getElementById('acctPrRunLines');
    if (!editor || !meta || !tbody) return;
    editor.classList.remove('hidden');
    meta.textContent = `${run.run_number} · ${run.status} · Pay ${run.pay_date || ''} · Gross ${money(run.total_gross)} · Net ${money(run.total_net)} · Employer taxes ${money(run.total_employer_taxes)}`;
    tbody.innerHTML = (run.lines || []).map((ln) => {
      const taxes = (ln.federal_wh || 0) + (ln.state_wh || 0) + (ln.fica_employee || 0) + (ln.medicare_employee || 0);
      return `<tr class="border-t border-zinc-800"><td class="px-2 py-1">${esc(ln.employee_name)}</td>
        <td class="px-2 py-1 text-right">${ln.hours_regular}${ln.hours_overtime ? '+' + ln.hours_overtime + 'OT' : ''}</td>
        <td class="px-2 py-1 text-right">${money(ln.gross_pay)}</td><td class="px-2 py-1 text-right">${money(taxes)}</td>
        <td class="px-2 py-1 text-right">${money(ln.other_deductions)}</td><td class="px-2 py-1 text-right">${money(ln.net_pay)}</td>
        <td class="px-2 py-1 text-zinc-500">${ln.project_id || '—'}</td></tr>`;
    }).join('') || '<tr><td colspan="7" class="p-2 text-zinc-500">No checks — use Add all active employees.</td></tr>';
  }

  function bindHandlers() {
    const { api, switchModule, projectId } = h();

    document.getElementById('acctPrAddEmp')?.addEventListener('click', async () => {
      const employee_number = prompt('Employee #');
      const first_name = prompt('First name');
      const last_name = prompt('Last name');
      if (!employee_number || !first_name || !last_name) return;
      const pay_type = prompt('Pay type: hourly or salary', 'hourly') || 'hourly';
      const hourly_rate = parseFloat(prompt('Hourly rate (if hourly)', '35') || '0');
      const annual_salary = parseFloat(prompt('Annual salary (if salary)', '0') || '0');
      const pid = projectId();
      await api('/api/accounting/payroll/employees', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          employee_number, first_name, last_name, pay_type, hourly_rate, annual_salary,
          default_project_id: pid || null,
        }),
      });
      switchModule('payroll');
    });

    document.getElementById('acctPrAddDed')?.addEventListener('click', async () => {
      const code = prompt('Deduction code (e.g. 401K)');
      if (!code) return;
      const amount = parseFloat(prompt('Fixed amount per period (or 0)', '0') || '0');
      const percent = parseFloat(prompt('Or percent of gross (or 0)', '0') || '0');
      await api('/api/accounting/payroll/deductions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code,
          description: code,
          calc_method: percent > 0 ? 'percent' : 'fixed',
          amount,
          percent,
        }),
      });
      switchModule('payroll');
    });

    document.getElementById('acctPrNewRun')?.addEventListener('click', async () => {
      const out = await api('/api/accounting/payroll/runs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
      await loadRun(out.run.id);
    });

    document.getElementById('acctPrBuild')?.addEventListener('click', async () => {
      if (!currentRunId) return;
      await api(`/api/accounting/payroll/runs/${currentRunId}/build`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ default_hours: 40 }),
      });
      await loadRun(currentRunId);
    });

    document.getElementById('acctPrCalc')?.addEventListener('click', async () => {
      if (!currentRunId) return;
      await api(`/api/accounting/payroll/runs/${currentRunId}/calculate`, { method: 'POST', body: '{}' });
      await loadRun(currentRunId);
    });

    async function postRun(id) {
      try {
        const out = await api(`/api/accounting/payroll/runs/${id}/post`, { method: 'POST', body: '{}' });
        alert(`Posted payroll · G/L batch ${out.journal_batch_id}`);
        switchModule('payroll');
      } catch (e) {
        alert(e.message);
      }
    }

    document.getElementById('acctPrPostRun')?.addEventListener('click', () => currentRunId && postRun(currentRunId));
    document.querySelectorAll('.acct-pr-post').forEach((btn) => btn.addEventListener('click', () => postRun(btn.getAttribute('data-id'))));
    document.querySelectorAll('.acct-pr-open').forEach((btn) => btn.addEventListener('click', () => loadRun(btn.getAttribute('data-id'))));
  }

  global.CasePMAcctPayrollUI = { render, bindHandlers, loadRun };
})(window);
