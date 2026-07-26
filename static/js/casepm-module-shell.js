/**
 * Case PM Module Shell — progressive disclosure: simple fields first, expand for advanced.
 */
(function (global) {
  'use strict';

  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function fieldHtml(field, prefix, values) {
    const key = field[0];
    const label = field[1];
    const type = field[2];
    const val = values[key] != null ? values[key] : '';
    const id = `${prefix}_${key}`;
    if (type === 'textarea') {
      return `<div><label class="block text-xs text-zinc-400 mb-1">${esc(label)}</label><textarea id="${id}" class="ops-input resize-y" rows="2">${esc(val)}</textarea></div>`;
    }
    if (type === 'select') {
      const opts = (field[3] || []).map(o => `<option value="${esc(o)}" ${String(val) === String(o) ? 'selected' : ''}>${esc(o)}</option>`).join('');
      return `<div><label class="block text-xs text-zinc-400 mb-1">${esc(label)}</label><select id="${id}" class="ops-input">${opts}</select></div>`;
    }
    const inputType = type === 'number' ? 'number' : type === 'date' ? 'date' : 'text';
    return `<div><label class="block text-xs text-zinc-400 mb-1">${esc(label)}</label><input id="${id}" type="${inputType}" class="ops-input" value="${esc(val)}"></div>`;
  }

  function readFields(container, schema, prefix) {
    const simple = {};
    const advanced = {};
    (schema.simple || []).forEach(f => {
      const el = container.querySelector(`#${prefix}_${f[0]}`);
      if (el) simple[f[0]] = el.value;
    });
    (schema.advanced || []).forEach(f => {
      const el = container.querySelector(`#${prefix}_${f[0]}`);
      if (el) advanced[f[0]] = el.value;
    });
    return { simple, advanced };
  }

  function buildFormHtml(schema, prefix, record) {
    const simple = record?.simple || {};
    const advanced = record?.advanced || {};
    let html = '<div class="space-y-3" id="' + prefix + 'Simple">';
    (schema.simple || []).forEach(f => { html += fieldHtml(f, prefix, simple); });
    html += '</div>';
    html += '<div class="ops-advanced hidden space-y-3" id="' + prefix + 'Advanced">';
    (schema.advanced || []).forEach(f => { html += fieldHtml(f, prefix, advanced); });
    html += '</div>';
    return html;
  }

  function statusChip(status) {
    const s = status || 'Draft';
    const colors = {
      Draft: 'bg-zinc-600/30 text-zinc-300',
      Open: 'bg-sky-500/20 text-sky-300',
      Approved: 'bg-emerald-500/20 text-emerald-300',
      Closed: 'bg-zinc-500/20 text-zinc-400',
      Sent: 'bg-violet-500/20 text-violet-300',
    };
    const cls = colors[s] || 'bg-amber-500/20 text-amber-300';
    return `<span class="ops-chip ${cls}">${esc(s)}</span>`;
  }

  global.CasePMModuleShell = {
    esc,
    fieldHtml,
    readFields,
    buildFormHtml,
    statusChip,
  };
})(window);
