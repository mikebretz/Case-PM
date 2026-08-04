/**
 * Parse spreadsheet rows into cost code objects (shared by Budget & Accounting).
 */
(function (global) {
  'use strict';

  function normalizeHeader(h) {
    return String(h || '').trim().toLowerCase();
  }

  function rowToCostCode(r) {
    if (!r || typeof r !== 'object') return null;
    let code = r.code || r['cost code'] || r.costcode || r.cost_code || r.cc || '';
    let desc = r.description || r.desc || r.name || r['description / name'] || r['desc / name'] || '';

    if (!code && Object.keys(r).length > 0) {
      const keys = Object.keys(r);
      code = r[keys[0]] || '';
      if (!desc && keys.length > 1) desc = r[keys[1]] || '';
    }

    code = String(code || '').trim();
    desc = String(desc || '').trim();

    if ((!desc || desc === code) && code) {
      const match = code.match(/^([0-9A-Za-z.-]+)\s*[-/]\s*(.+)$/);
      if (match) {
        code = match[1].trim();
        desc = match[2].trim();
      }
    }

    const type = String(r['cost type'] || r.type || r.costtype || r.cost_type || '').trim();

    if (!code) return null;
    if (!desc) desc = code;

    const out = { code, description: desc };
    if (type) out.cost_type = type;
    return out;
  }

  function parseObjectsFromRows(rows) {
    const out = [];
    (rows || []).forEach((r) => {
      const item = rowToCostCode(r);
      if (item) out.push(item);
    });
    return out;
  }

  function parseSheetRowsFromArray(json) {
    if (!json || json.length < 1) return [];
    const headers = json[0].map((h) => normalizeHeader(h));
    return json.slice(1).map((r) => {
      const o = {};
      headers.forEach((h, i) => {
        o[h] = r[i] !== undefined ? String(r[i]).trim() : '';
      });
      return o;
    });
  }

  function parseCsvText(text) {
    const lines = String(text || '').split(/\r?\n/).filter((l) => l.trim());
    if (!lines.length) return [];
    const headers = lines[0].split(',').map((h) => normalizeHeader(h));
    const rows = [];
    for (let i = 1; i < lines.length; i++) {
      const values = lines[i].split(',');
      const obj = {};
      headers.forEach((h, idx) => {
        obj[h] = values[idx] ? values[idx].trim() : '';
      });
      rows.push(obj);
    }
    return rows;
  }

  function mergeCostCodes(existing, incoming, mode) {
    const replace = mode === 'replace';
    const base = replace ? [] : [...(existing || [])];
    const seen = new Set(base.map((c) => String(c.code).toLowerCase()));
    let added = 0;
    let updated = 0;
    (incoming || []).forEach((item) => {
      const key = String(item.code).toLowerCase();
      const idx = base.findIndex((c) => String(c.code).toLowerCase() === key);
      if (idx >= 0) {
        base[idx] = { ...base[idx], ...item };
        updated++;
      } else if (!seen.has(key)) {
        seen.add(key);
        base.push(item);
        added++;
      } else {
        const j = base.findIndex((c) => String(c.code).toLowerCase() === key);
        if (j >= 0) {
          base[j] = { ...base[j], ...item };
          updated++;
        }
      }
    });
    return { list: base, added, updated, replaced: replace };
  }

  function pickCostCodeFile() {
    return new Promise((resolve, reject) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = '.xlsx,.xls,.csv';
      input.onchange = (e) => {
        const file = e.target.files && e.target.files[0];
        if (!file) {
          resolve(null);
          return;
        }
        const reader = new FileReader();
        reader.onload = (ev) => {
          try {
            let rows = [];
            const lower = file.name.toLowerCase();
            if (lower.endsWith('.csv')) {
              rows = parseCsvText(ev.target.result);
            } else {
              const XLSX = global.XLSX;
              if (!XLSX) throw new Error('Excel library not loaded — refresh the Accounting page.');
              const data = new Uint8Array(ev.target.result);
              const wb = XLSX.read(data, { type: 'array' });
              const sheet = wb.Sheets[wb.SheetNames[0]];
              const json = XLSX.utils.sheet_to_json(sheet, { header: 1 });
              rows = parseSheetRowsFromArray(json);
            }
            const incoming = parseObjectsFromRows(rows);
            if (!incoming.length) throw new Error('No cost codes found in file');
            resolve({ incoming, fileName: file.name });
          } catch (err) {
            reject(err);
          }
        };
        reader.onerror = () => reject(new Error('Could not read file'));
        if (file.name.toLowerCase().endsWith('.csv')) reader.readAsText(file);
        else reader.readAsArrayBuffer(file);
      };
      input.click();
    });
  }

  /**
   * Open file picker, parse xlsx/csv, return { list, added, updated, replaced }.
   * options: { existing, mode: 'append'|'replace' }
   */
  function pickAndImportCostCodes(options) {
    const opts = options || {};
    return new Promise((resolve, reject) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = '.xlsx,.xls,.csv';
      input.onchange = (e) => {
        const file = e.target.files && e.target.files[0];
        if (!file) {
          resolve(null);
          return;
        }
        const reader = new FileReader();
        reader.onload = (ev) => {
          try {
            let rows = [];
            const lower = file.name.toLowerCase();
            if (lower.endsWith('.csv')) {
              rows = parseCsvText(ev.target.result);
            } else {
              const XLSX = global.XLSX;
              if (!XLSX) throw new Error('Excel library not loaded');
              const data = new Uint8Array(ev.target.result);
              const wb = XLSX.read(data, { type: 'array' });
              const sheet = wb.Sheets[wb.SheetNames[0]];
              const json = XLSX.utils.sheet_to_json(sheet, { header: 1 });
              rows = parseSheetRowsFromArray(json);
            }
            const incoming = parseObjectsFromRows(rows);
            if (!incoming.length) throw new Error('No cost codes found in file');
            const result = mergeCostCodes(opts.existing || [], incoming, opts.mode || 'append');
            resolve({ ...result, fileName: file.name, rowCount: incoming.length });
          } catch (err) {
            reject(err);
          }
        };
        reader.onerror = () => reject(new Error('Could not read file'));
        if (file.name.toLowerCase().endsWith('.csv')) reader.readAsText(file);
        else reader.readAsArrayBuffer(file);
      };
      input.click();
    });
  }

  global.CasePMCostCodeImport = {
    parseObjectsFromRows,
    mergeCostCodes,
    pickCostCodeFile,
    pickAndImportCostCodes,
    rowToCostCode,
  };
})(typeof window !== 'undefined' ? window : globalThis);
