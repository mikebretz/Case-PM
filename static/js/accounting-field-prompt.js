/**
 * Optional prompts to post field events (equipment daily log, delivery receipt) to built-in accounting.
 */
(function (global) {
  'use strict';

  async function loadAccountingPrefs() {
    try {
      const r = await fetch('/api/accounting/field-post-prefs', { credentials: 'same-origin' });
      const j = await r.json();
      return j || {};
    } catch (_) {
      return {};
    }
  }

  async function postJson(url, body) {
    const r = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || 'Accounting post failed');
    return j;
  }

  async function maybePostEquipmentDailyLog(dailyLogId, equipmentRowCount) {
    if (!dailyLogId || !equipmentRowCount) return null;
    const prefs = await loadAccountingPrefs();
    if (prefs.field_auto_post_silent === '1') return null;
    const autoFlag = prefs.auto_post_equipment_on_daily_log === '1';
    const dcOn = prefs.direct_cost_post_on_approve !== '0';
    if (!autoFlag && !dcOn) {
      return null;
    }
    const ask = global.CasePMDialog
      ? await global.CasePMDialog.confirm(
          `Post ${equipmentRowCount} equipment line(s) from this daily log to job cost / G/L?`,
          'Accounting',
        )
      : global.confirm('Post equipment hours to accounting?');
    if (!ask) return null;
    const out = await postJson(`/api/accounting/jc/equipment-daily-log/${dailyLogId}`, {});
    if (global.showToast) global.showToast(`Accounting: ${out.posted_count || 0} equipment post(s)`);
    return out;
  }

  async function maybePostDeliveryReceive(deliveryId, status, prevStatus) {
    if (!deliveryId || status !== 'Delivered') return null;
    if (prevStatus === 'Delivered') return null;
    const prefs = await loadAccountingPrefs();
    if (prefs.field_auto_post_silent === '1') return null;
    const autoFlag = prefs.auto_post_delivery_on_delivered === '1';
    const dcOn = prefs.direct_cost_post_on_approve !== '0';
    if (!autoFlag && !dcOn) {
      return null;
    }
    const amountStr = global.prompt(
      'Delivery marked Delivered. Enter receipt amount to post to materials / job cost (leave blank to skip):',
      '',
    );
    if (amountStr === null || String(amountStr).trim() === '') return null;
    const amount = parseFloat(amountStr);
    if (!Number.isFinite(amount) || amount <= 0) {
      if (global.CasePMDialog) await global.CasePMDialog.alert('Enter a positive amount.', 'Accounting');
      return null;
    }
    const out = await postJson(`/api/accounting/distribution/delivery-receive/${deliveryId}`, { amount });
    if (global.showToast) global.showToast('Delivery receipt posted to accounting');
    return out;
  }

  global.CasePMAccountingField = {
    maybePostEquipmentDailyLog,
    maybePostDeliveryReceive,
  };
})(typeof window !== 'undefined' ? window : globalThis);
