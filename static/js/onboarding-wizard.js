/**
 * First-run onboarding — project selection and quick tour.
 */
(function (global) {
  'use strict';

  const uid = document.body?.getAttribute('data-current-user-id') || '0';
  const KEY = `casepm_onboarding_done_u${uid}`;
  const isStaff = document.body?.getAttribute('data-is-staff-portal') === '1';

  function done() {
    try { localStorage.setItem(KEY, '1'); } catch (_) { /* ignore */ }
    document.getElementById('casepmOnboardingModal')?.close();
  }

  function shouldShow() {
    if (!isStaff) return false;
    try {
      if (localStorage.getItem(KEY) === '1') return false;
    } catch (_) { return false; }
    const pid = document.body?.getAttribute('data-active-project-id');
    const projects = document.querySelectorAll('.project-switcher-item').length;
    return !pid && projects === 0;
  }

  function buildModal() {
    if (document.getElementById('casepmOnboardingModal')) return;
    const dlg = document.createElement('dialog');
    dlg.id = 'casepmOnboardingModal';
    dlg.className = 'casepm-dialog bg-zinc-900 border border-zinc-700 rounded-xl w-full max-w-lg p-0 text-zinc-200';
    dlg.innerHTML = `
      <div class="px-6 py-4 border-b border-zinc-800">
        <h2 class="text-lg font-semibold text-white">Welcome to Case PM</h2>
        <p class="text-sm text-zinc-400 mt-1">A quick setup so you can start working.</p>
      </div>
      <div class="p-6 space-y-4 text-sm">
        <div class="flex gap-3">
          <div class="w-8 h-8 rounded-full bg-emerald-600/20 text-emerald-400 flex items-center justify-center shrink-0 font-semibold">1</div>
          <div>
            <div class="font-medium text-white">Create or open a project</div>
            <p class="text-zinc-500 mt-0.5">Use <strong class="text-zinc-300">Projects</strong> or the project menu in the header.</p>
            <a href="/projects" class="inline-block mt-2 text-emerald-400 text-xs hover:underline">Go to Projects →</a>
          </div>
        </div>
        <div class="flex gap-3">
          <div class="w-8 h-8 rounded-full bg-emerald-600/20 text-emerald-400 flex items-center justify-center shrink-0 font-semibold">2</div>
          <div>
            <div class="font-medium text-white">Check My work</div>
            <p class="text-zinc-500 mt-0.5">RFIs, submittals, change orders, and approvals appear in one queue.</p>
            <a href="/my-work" class="inline-block mt-2 text-emerald-400 text-xs hover:underline">Open My work →</a>
          </div>
        </div>
        <div class="flex gap-3">
          <div class="w-8 h-8 rounded-full bg-emerald-600/20 text-emerald-400 flex items-center justify-center shrink-0 font-semibold">3</div>
          <div>
            <div class="font-medium text-white">Connect email (optional)</div>
            <p class="text-zinc-500 mt-0.5">Use <strong class="text-zinc-300">Microsoft Outlook</strong> today. Gmail OAuth is planned — use IMAP/SMTP until then.</p>
            <a href="/email" class="inline-block mt-2 text-emerald-400 text-xs hover:underline">Email settings →</a>
          </div>
        </div>
      </div>
      <div class="px-6 py-4 border-t border-zinc-800 flex justify-end gap-2">
        <button type="button" id="casepmOnboardingDismiss" class="px-4 py-2 text-sm rounded-md bg-emerald-600 hover:bg-emerald-500 font-semibold text-white">Got it</button>
      </div>`;
    document.body.appendChild(dlg);
    dlg.querySelector('#casepmOnboardingDismiss')?.addEventListener('click', done);
  }

  function maybeOpen() {
    if (!shouldShow()) return;
    buildModal();
    document.getElementById('casepmOnboardingModal')?.showModal();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', maybeOpen);
  else setTimeout(maybeOpen, 800);

  global.CasePMOnboarding = { done, maybeOpen };
})(window);
