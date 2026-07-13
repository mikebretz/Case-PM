/**
 * CSI MasterFormat catalog helpers for estimating & companies UI
 */
(function (global) {
  'use strict';

  let _cache = null;

  async function loadCatalog() {
    if (_cache) return _cache;
    const res = await fetch('/api/csi/catalog', { credentials: 'same-origin' });
    const json = await res.json();
    if (!res.ok) throw new Error(json.error || 'Failed to load CSI catalog');
    _cache = json;
    return _cache;
  }

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  }

  function divisionFromSpec(code) {
    const parts = (code || '').trim().split(/\s+/);
    return parts[0] || '';
  }

  async function fillDivisionSelect(selectEl, selected) {
    const cat = await loadCatalog();
    if (!selectEl) return;
    selectEl.innerHTML = '<option value="">— Division —</option>' +
      cat.divisions.map(d => `<option value="${esc(d.code)}">${esc(d.code)} — ${esc(d.name)}</option>`).join('');
    if (selected) selectEl.value = selected;
  }

  async function fillSpecSelect(selectEl, divisionCode, selected) {
    const cat = await loadCatalog();
    if (!selectEl) return;
    const div = String(divisionCode || '').padStart(2, '0').slice(0, 2);
    const sections = div
      ? cat.spec_sections.filter(s => s.division === div)
      : cat.spec_sections;
    selectEl.innerHTML = '<option value="">— Spec Section —</option>' +
      sections.map(s => `<option value="${esc(s.code)}">${esc(s.label)}</option>`).join('');
    if (selected) selectEl.value = selected;
  }

  function wireDivisionSpecPair(divisionSelect, specSelect, onSpecChange) {
    if (!divisionSelect || !specSelect) return;
    divisionSelect.addEventListener('change', async () => {
      await fillSpecSelect(specSelect, divisionSelect.value);
      if (onSpecChange) onSpecChange();
    });
    specSelect.addEventListener('change', () => { if (onSpecChange) onSpecChange(); });
  }

  async function renderSpecCheckboxList(container, selectedCodes) {
    const cat = await loadCatalog();
    const sel = new Set((selectedCodes || []).map(c => c.replace(/\s/g, '')));
    if (!container) return;
    const byDiv = {};
    cat.spec_sections.forEach(s => {
      byDiv[s.division] = byDiv[s.division] || [];
      byDiv[s.division].push(s);
    });
    container.innerHTML = cat.divisions.map(d => {
      const sections = byDiv[d.code] || [];
      if (!sections.length) return '';
      return `<div class="csi-div-group mb-3">
        <div class="text-xs font-semibold text-emerald-400 mb-1">${esc(d.code)} — ${esc(d.name)}</div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-1 max-h-32 overflow-auto pl-2">
          ${sections.map(s => {
            const norm = s.code.replace(/\s/g, '');
            const checked = sel.has(norm) ? 'checked' : '';
            return `<label class="flex items-start gap-2 text-xs text-zinc-300 cursor-pointer hover:text-white">
              <input type="checkbox" class="csi-spec-cb mt-0.5 accent-emerald-600" value="${esc(s.code)}" ${checked}>
              <span>${esc(s.label)}</span>
            </label>`;
          }).join('')}
        </div>
      </div>`;
    }).join('');
  }

  function readSelectedSpecCodes(container) {
    if (!container) return [];
    return [...container.querySelectorAll('.csi-spec-cb:checked')].map(cb => cb.value);
  }

  global.CasePMCsiCatalog = {
    loadCatalog,
    fillDivisionSelect,
    fillSpecSelect,
    wireDivisionSpecPair,
    renderSpecCheckboxList,
    readSelectedSpecCodes,
    divisionFromSpec,
  };
})(window);
