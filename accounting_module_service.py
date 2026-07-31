"""Built-in accounting dashboard and summaries (standalone ERP)."""
from __future__ import annotations

from accounting_catalog import catalog_for_api
from accounting_persistence import (
    ap_aging,
    ar_aging,
    get_or_create_default_ledger,
    seed_chart_of_accounts,
    trial_balance,
)


def _models(deps):
    return {k: deps[k] for k in deps if k.startswith('Acct')}


def get_catalog(db=None, models=None):
    data = catalog_for_api()
    if db and models:
        from accounting_persistence import get_or_create_default_ledger
        from accounting_all_chunks import allowed_screens_for_ledger
        ledger = get_or_create_default_ledger(db, models['AcctLedger'])
        data['allowed_screens'] = allowed_screens_for_ledger(ledger)
    return data


def build_company_dashboard(db, models, project_id=None, Project=None, SageSyncEvent=None):
    AcctLedger = models['AcctLedger']
    AcctGLAccount = models['AcctGLAccount']
    AcctJournalBatch = models['AcctJournalBatch']
    AcctJournalLine = models['AcctJournalLine']
    AcctVendor = models['AcctVendor']
    AcctCustomer = models['AcctCustomer']
    AcctAPDocument = models['AcctAPDocument']
    AcctARDocument = models['AcctARDocument']
    AcctBankAccount = models['AcctBankAccount']

    ledger = get_or_create_default_ledger(db, AcctLedger)
    seed_chart_of_accounts(db, AcctLedger, AcctGLAccount, ledger)

    tb = trial_balance(db, AcctGLAccount, AcctJournalLine, AcctJournalBatch, ledger.id)
    ap = ap_aging(AcctAPDocument, ledger.id)
    ar = ar_aging(AcctARDocument, ledger.id)

    from program_settings_persistence import load_sage_defaults
    sage = load_sage_defaults()
    sage_sync_on = sage.get('sage_sync_enabled', '1') != '0' and bool(
        sage.get('sage_api_url') or __import__('os').environ.get('SAGE_API_URL', '').strip()
    )

    project_ctx = None
    if project_id and Project:
        p = Project.query.get(int(project_id))
        if p:
            project_ctx = {
                'id': p.id,
                'name': p.name,
                'number': p.number,
                'job_number': (p.sage_job_number or p.accounting_project_number or '').strip(),
            }

    pending_erp = 0
    if project_id and SageSyncEvent:
        pending_erp = SageSyncEvent.query.filter_by(
            project_id=int(project_id),
            accounting_status='pending_review',
        ).count()

    return {
        'ok': True,
        'ledger': {
            'id': ledger.id,
            'code': ledger.code,
            'name': ledger.name,
            'base_currency': ledger.base_currency,
        },
        'kpis': {
            'gl_accounts': AcctGLAccount.query.filter_by(ledger_id=ledger.id).count(),
            'open_ap': round(sum(ap['buckets'].values()), 2),
            'open_ar': round(sum(ar['buckets'].values()), 2),
            'vendors': AcctVendor.query.filter_by(ledger_id=ledger.id).count(),
            'customers': AcctCustomer.query.filter_by(ledger_id=ledger.id).count(),
            'open_batches': AcctJournalBatch.query.filter_by(ledger_id=ledger.id, status='Open').count(),
            'bank_accounts': AcctBankAccount.query.filter_by(ledger_id=ledger.id).count(),
            **__import__('accounting_parity_wave2', fromlist=['extended_dashboard_kpis']).extended_dashboard_kpis(
                db, models, ledger.id
            ),
        },
        'trial_balance_preview': tb[:8],
        'ap_aging_buckets': ap['buckets'],
        'ar_aging_buckets': ar['buckets'],
        'project': project_ctx,
        'external_sync': {
            'sage_300': {
                'enabled': sage_sync_on,
                'configure_url_hint': '/program-settings?tab=sage',
            },
            'pending_construction_exports': pending_erp if sage_sync_on else 0,
        },
    }
