"""Platform administration depth + configurable accounting dashboard."""
from __future__ import annotations

import json
from datetime import date

from accounting_gl_service import _parse_settings

# id, label, kpi_key, format, default drill route
DEFAULT_KPI_TILE_CATALOG = [
    {'id': 'open_ap', 'label': 'Open A/P', 'kpi_key': 'open_ap', 'format': 'money', 'drill_route': 'ap'},
    {'id': 'open_ar', 'label': 'Open A/R', 'kpi_key': 'open_ar', 'format': 'money', 'drill_route': 'ar'},
    {'id': 'gl_accounts', 'label': 'G/L accounts', 'kpi_key': 'gl_accounts', 'format': 'int', 'drill_route': 'gl'},
    {'id': 'open_batches', 'label': 'Open J/E batches', 'kpi_key': 'open_batches', 'format': 'int', 'drill_route': 'gl'},
    {'id': 'vendors', 'label': 'Vendors', 'kpi_key': 'vendors', 'format': 'int', 'drill_route': 'ap'},
    {'id': 'customers', 'label': 'Customers', 'kpi_key': 'customers', 'format': 'int', 'drill_route': 'ar'},
    {'id': 'bank_accounts', 'label': 'Bank accounts', 'kpi_key': 'bank_accounts', 'format': 'int', 'drill_route': 'bank'},
    {'id': 'open_ap_documents', 'label': 'Open A/P docs', 'kpi_key': 'open_ap_documents', 'format': 'int', 'drill_route': 'ap'},
    {'id': 'open_ar_documents', 'label': 'Open A/R docs', 'kpi_key': 'open_ar_documents', 'format': 'int', 'drill_route': 'ar'},
    {'id': 'credit_reviews_open', 'label': 'Credit reviews', 'kpi_key': 'credit_reviews_open', 'format': 'int', 'drill_route': 'ar'},
    {'id': 'consolidation_runs', 'label': 'Consolidation runs', 'kpi_key': 'consolidation_runs', 'format': 'int', 'drill_route': 'consolidation'},
    {'id': 'cash_ratio', 'label': 'A/R ÷ A/P ratio', 'kpi_key': 'cash_ratio', 'format': 'number', 'drill_route': 'reports'},
]

DEFAULT_VISIBLE_TILE_IDS = ['open_ap', 'open_ar', 'gl_accounts', 'open_batches']


def _catalog_by_id():
    return {t['id']: t for t in DEFAULT_KPI_TILE_CATALOG}


def dashboard_kpi_config(ledger) -> dict:
    settings = _parse_settings(ledger)
    cfg = settings.get('dashboard_kpi') or {}
    visible = cfg.get('visible_tile_ids')
    if not visible:
        visible = list(DEFAULT_VISIBLE_TILE_IDS)
    order = cfg.get('tile_order') or visible
    return {
        'visible_tile_ids': visible,
        'tile_order': order,
        'catalog': DEFAULT_KPI_TILE_CATALOG,
    }


def update_dashboard_kpi_config(ledger, body: dict) -> dict:
    settings = _parse_settings(ledger)
    cfg = settings.get('dashboard_kpi') or {}
    catalog_ids = set(_catalog_by_id())
    if 'visible_tile_ids' in body and isinstance(body['visible_tile_ids'], list):
        cfg['visible_tile_ids'] = [x for x in body['visible_tile_ids'] if x in catalog_ids]
    if 'tile_order' in body and isinstance(body['tile_order'], list):
        cfg['tile_order'] = [x for x in body['tile_order'] if x in catalog_ids]
    settings['dashboard_kpi'] = cfg
    ledger.settings_json = json.dumps(settings)
    return dashboard_kpi_config(ledger)


def build_dashboard_kpi_tiles(kpis: dict, ledger) -> list:
    cfg = dashboard_kpi_config(ledger)
    by_id = _catalog_by_id()
    order = cfg['tile_order']
    visible = set(cfg['visible_tile_ids'])
    tiles = []
    seen = set()
    for tid in order:
        if tid not in visible or tid in seen or tid not in by_id:
            continue
        seen.add(tid)
        meta = by_id[tid]
        raw = kpis.get(meta['kpi_key'])
        if raw is None:
            continue
        tiles.append({
            'id': tid,
            'label': meta['label'],
            'value': raw,
            'format': meta['format'],
            'drill_route': meta.get('drill_route'),
        })
    for tid in visible:
        if tid in seen or tid not in by_id:
            continue
        meta = by_id[tid]
        raw = kpis.get(meta['kpi_key'])
        if raw is None:
            continue
        tiles.append({
            'id': tid,
            'label': meta['label'],
            'value': raw,
            'format': meta['format'],
            'drill_route': meta.get('drill_route'),
        })
    return tiles


def consolidated_entity_summary(db, models, ledger_id: int) -> dict:
    from accounting_consolidation import consolidated_trial_balance, ledger_tree, subsidiary_ledger_ids

    AcctLedger = models['AcctLedger']
    ledger = AcctLedger.query.get(int(ledger_id))
    if not ledger:
        return {'enabled': False}
    child_ids = subsidiary_ledger_ids(AcctLedger, ledger.id)
    if not child_ids:
        return {
            'enabled': False,
            'parent_ledger_id': ledger.id,
            'parent_code': ledger.code,
            'entity_count': 1,
            'message': 'No subsidiary ledgers — add children under Consolidation to roll up.',
        }
    try:
        tb = consolidated_trial_balance(db, models, ledger.id, include_parent=True)
    except ValueError as exc:
        return {'enabled': False, 'error': str(exc)}
    rows = tb.get('rows') or []
    total_assets = sum(r['balance'] for r in rows if (r.get('account_type') or '').lower() == 'asset')
    total_liab = sum(r['balance'] for r in rows if (r.get('account_type') or '').lower() == 'liability')
    total_equity = sum(r['balance'] for r in rows if (r.get('account_type') or '').lower() == 'equity')
    tree = ledger_tree(AcctLedger)
    return {
        'enabled': True,
        'parent_ledger_id': ledger.id,
        'parent_code': ledger.code,
        'entity_count': len(tb.get('ledger_ids') or []),
        'subsidiary_count': len(child_ids),
        'totals': {
            'assets': round(total_assets, 2),
            'liabilities': round(total_liab, 2),
            'equity': round(total_equity, 2),
        },
        'account_lines': len(rows),
        'drill_route': 'consolidation',
        'ledgers': tree.get('ledgers', [])[:12],
    }


def list_fiscal_archive_index(models, ledger_id: int) -> dict:
    AcctFiscalPeriod = models['AcctFiscalPeriod']
    years = sorted({
        p.fiscal_year for p in AcctFiscalPeriod.query.filter_by(ledger_id=ledger_id).all()
        if p.fiscal_year
    }, reverse=True)
    out = []
    for fy in years:
        periods = AcctFiscalPeriod.query.filter_by(ledger_id=ledger_id, fiscal_year=fy).all()
        closed = sum(1 for p in periods if p.status == 'Closed')
        out.append({
            'fiscal_year': fy,
            'period_count': len(periods),
            'closed_periods': closed,
            'fully_closed': len(periods) > 0 and closed == len(periods),
        })
    return {'years': out}


def list_revaluation_runs(models, ledger_id: int, *, limit=30) -> dict:
    AcctRevaluationRun = models['AcctRevaluationRun']
    rows = (
        AcctRevaluationRun.query.filter_by(ledger_id=ledger_id)
        .order_by(AcctRevaluationRun.id.desc())
        .limit(limit)
        .all()
    )
    items = []
    for r in rows:
        details = {}
        if r.details_json:
            try:
                details = json.loads(r.details_json) or {}
            except (TypeError, ValueError, json.JSONDecodeError):
                details = {}
        items.append({
            'id': r.id,
            'run_number': r.run_number,
            'period_end': r.period_end.isoformat() if r.period_end else None,
            'status': r.status,
            'journal_batch_id': r.journal_batch_id,
            'adjustment': details.get('adjustment'),
            'posted_at': r.posted_at.isoformat() if r.posted_at else None,
        })
    return {'runs': items}


def posting_schedule_full(db, models, ledger_id: int) -> dict:
    from accounting_core_gaps import posting_schedule_dashboard

    base = posting_schedule_dashboard(db, models, ledger_id)
    AcctGLRecurringJournal = models['AcctGLRecurringJournal']
    AcctAPRecurringPayable = models['AcctAPRecurringPayable']
    AcctARRecurringInvoice = models['AcctARRecurringInvoice']
    today = date.today()

    def _upcoming(query_model, label_field='code'):
        rows = query_model.query.filter_by(ledger_id=ledger_id, is_active=True).all()
        upcoming = []
        for r in rows:
            if not r.next_run_date:
                continue
            upcoming.append({
                'id': r.id,
                'label': getattr(r, label_field, None) or str(r.id),
                'next_run_date': r.next_run_date.isoformat(),
                'due': r.next_run_date <= today,
            })
        upcoming.sort(key=lambda x: x['next_run_date'])
        return upcoming[:25]

    base['upcoming'] = {
        'gl': _upcoming(AcctGLRecurringJournal, 'code'),
        'ap': _upcoming(AcctAPRecurringPayable, 'id'),
        'ar': _upcoming(AcctARRecurringInvoice, 'id'),
    }
    return base
