/**
 * Shared address autocomplete — project job sites + geocoded addresses.
 * Usage: CasePMAddressAutocomplete.attach(inputEl, { onSelect(item) })
 */
(function (global) {
  'use strict';

  let debounceTimer = null;

  function esc(s) {
    const d = document.createElement('div');
    d.textContent = s == null ? '' : String(s);
    return d.innerHTML;
  }

  async function fetchSuggestions(query) {
    const res = await fetch(`/api/geocode/search?q=${encodeURIComponent(query)}&limit=12`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.suggestions || [];
  }

  function ensureDropdown(input) {
    let wrap = input.closest('.casepm-address-wrap');
    if (!wrap) {
      wrap = document.createElement('div');
      wrap.className = 'casepm-address-wrap';
      input.parentNode.insertBefore(wrap, input);
      wrap.appendChild(input);
    }
    let list = wrap.querySelector('.casepm-address-dropdown');
    if (!list) {
      list = document.createElement('div');
      list.className = 'casepm-address-dropdown hidden';
      wrap.appendChild(list);
    }
    return list;
  }

  function hideDropdown(list) {
    if (list) list.classList.add('hidden');
  }

  function showDropdown(list, items, onSelect) {
    if (!items.length) {
      hideDropdown(list);
      return;
    }
    list.innerHTML = items.map((item, idx) => `
      <button type="button" class="casepm-address-option" data-idx="${idx}">
        <span class="casepm-address-option-label">${esc(item.label || item.name || item.address)}</span>
        <span class="casepm-address-option-sub">${esc(item.subtitle || item.city || '')}</span>
      </button>
    `).join('');
    list.classList.remove('hidden');
    list.querySelectorAll('.casepm-address-option').forEach(btn => {
      btn.addEventListener('mousedown', (e) => {
        e.preventDefault();
        const item = items[parseInt(btn.getAttribute('data-idx'), 10)];
        if (item && onSelect) onSelect(item);
        hideDropdown(list);
      });
    });
  }

  function attach(input, options) {
    if (!input) return;
    const list = ensureDropdown(input);
    const onSelect = options?.onSelect;
    const minChars = options?.minChars || 2;

    input.addEventListener('input', () => {
      clearTimeout(debounceTimer);
      const q = input.value.trim();
      if (q.length < minChars) {
        hideDropdown(list);
        return;
      }
      debounceTimer = setTimeout(async () => {
        const items = await fetchSuggestions(q);
        showDropdown(list, items, (item) => {
          input.value = item.label || item.address || input.value;
          if (onSelect) onSelect(item);
        });
      }, 220);
    });

    input.addEventListener('blur', () => setTimeout(() => hideDropdown(list), 150));
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('data-lpignore', 'true');
  }

  global.CasePMAddressAutocomplete = { attach, fetchSuggestions };
})(window);
