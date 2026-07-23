/**
 * Case PM electronic signatures — user-owned, server-verified.
 */
(function (global) {
  'use strict';

  let cachedMySignature = null;
  let cachedMyStamp = null;

  async function fetchMySignature(forceRefresh) {
    if (cachedMySignature && !forceRefresh) return cachedMySignature;
    const res = await fetch('/api/users/me/signature', { credentials: 'same-origin' });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Could not load signature');
    cachedMySignature = json.signature || { has_signature: false };
    return cachedMySignature;
  }

  async function fetchUserSignature(userId) {
    const res = await fetch(`/api/users/${userId}/signature`, { credentials: 'same-origin' });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Could not load signature');
    return json.signature || { has_signature: false };
  }

  async function saveMySignature(payload) {
    const res = await fetch('/api/users/me/signature', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Could not save signature');
    cachedMySignature = json.signature;
    return json.signature;
  }

  async function fetchMyStamp(forceRefresh) {
    if (cachedMyStamp && !forceRefresh) return cachedMyStamp;
    const res = await fetch('/api/users/me/stamp', { credentials: 'same-origin' });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Could not load stamp');
    cachedMyStamp = json.stamp || { has_stamp: false };
    return cachedMyStamp;
  }

  async function fetchUserStamp(userId) {
    const res = await fetch(`/api/users/${userId}/stamp`, { credentials: 'same-origin' });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Could not load stamp');
    return json.stamp || { has_stamp: false };
  }

  async function saveMyStamp(payload) {
    const res = await fetch('/api/users/me/stamp', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    });
    const json = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(json.error || 'Could not save stamp');
    cachedMyStamp = json.stamp;
    return json.stamp;
  }

  function clearCache() {
    cachedMySignature = null;
    cachedMyStamp = null;
  }

  /**
   * Build attestation payload for workflow APIs.
   */
  async function buildAttestationPayload() {
    const sig = await fetchMySignature(true);
    if (!sig?.has_signature || !sig.hash) {
      throw new Error('Set up your electronic signature in User Management → Signature first.');
    }
    return {
      signature_attestation: true,
      signature_hash: sig.hash,
      signature_legal_name: sig.legal_name,
    };
  }

  /**
   * Inject e-sign UI into a container. Returns { getReady, destroy }.
   */
  function mountSignPanel(container, options = {}) {
    if (!container) return null;
    const requireSig = options.requireSignature !== false;
    const title = options.title || 'Electronic Signature';

    container.innerHTML = `
      <div class="casepm-esign-panel border border-zinc-700 rounded-md p-4 bg-zinc-900/80 space-y-3">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="text-sm font-medium text-white">${title}</div>
            <p class="text-[11px] text-zinc-500 mt-0.5">Your signature is locked to your account. Admins cannot change it for you.</p>
          </div>
          <span id="casepmEsignStatus" class="text-[10px] px-2 py-0.5 rounded bg-zinc-800 text-zinc-400">Checking…</span>
        </div>
        <div id="casepmEsignPreview" class="flex items-center gap-4 min-h-[72px] bg-white rounded p-2 border border-zinc-600">
          <div class="text-xs text-zinc-500">Loading signature…</div>
        </div>
        <label class="flex items-start gap-2 text-xs text-zinc-300 cursor-pointer select-none">
          <input type="checkbox" id="casepmEsignAttest" class="mt-0.5 accent-emerald-600">
          <span>I agree this is my legal electronic signature under my User Management profile, and I authorize it to be applied to this document.</span>
        </label>
        <div id="casepmEsignError" class="hidden text-xs text-red-400"></div>
        ${!requireSig ? '' : '<p class="text-[10px] text-amber-400/90">Owner and Architect approvals require a saved signature.</p>'}
      </div>`;

    const statusEl = container.querySelector('#casepmEsignStatus');
    const previewEl = container.querySelector('#casepmEsignPreview');
    const attestEl = container.querySelector('#casepmEsignAttest');
    const errEl = container.querySelector('#casepmEsignError');
    let ready = false;
    let sigMeta = null;

    fetchMySignature(true).then(sig => {
      sigMeta = sig;
      if (sig.has_signature && sig.image_url) {
        statusEl.textContent = 'Ready';
        statusEl.className = 'text-[10px] px-2 py-0.5 rounded bg-emerald-900/50 text-emerald-400';
        previewEl.innerHTML = `
          <img src="${sig.image_url}?t=${Date.now()}" alt="Your signature" class="max-h-16 max-w-[240px] object-contain">
          <div class="text-xs text-zinc-700">
            <div class="font-medium">${sig.legal_name || ''}</div>
            <div class="font-mono text-[10px] text-zinc-500">SHA ${(sig.hash || '').slice(0, 12)}…</div>
          </div>`;
        ready = true;
      } else {
        statusEl.textContent = 'Not set up';
        statusEl.className = 'text-[10px] px-2 py-0.5 rounded bg-amber-900/40 text-amber-400';
        previewEl.innerHTML = `<div class="text-xs text-zinc-600 px-2">No signature on file. Open <a href="/user-management" class="text-emerald-600 underline">User Management</a> → your profile → Signature.</div>`;
      }
    }).catch(err => {
      statusEl.textContent = 'Error';
      previewEl.innerHTML = `<div class="text-xs text-red-600">${err.message}</div>`;
    });

    return {
      async getPayload() {
        errEl.classList.add('hidden');
        if (!attestEl.checked) {
          errEl.textContent = 'Check the attestation box to sign.';
          errEl.classList.remove('hidden');
          throw new Error('Attestation required');
        }
        const payload = await buildAttestationPayload();
        return payload;
      },
      isReady: () => ready,
      destroy() { container.innerHTML = ''; },
    };
  }

  global.CasePMEsign = {
    fetchMySignature,
    fetchUserSignature,
    saveMySignature,
    fetchMyStamp,
    fetchUserStamp,
    saveMyStamp,
    buildAttestationPayload,
    mountSignPanel,
    clearCache,
  };
})(window);
