"""Accounting UI strings — multi-language (en, fr, es, zh)."""
from __future__ import annotations

_COMMON = {
    'save': 'Save',
    'cancel': 'Cancel',
    'post': 'Post',
    'delete': 'Delete',
    'import': 'Import',
    'export': 'Export',
    'dashboard': 'Dashboard',
    'reports': 'Reports',
    'bank': 'Bank Services',
    'tax': 'Tax Services',
    'inventory': 'Inventory',
    'payroll': 'Payroll',
    'payments': 'Payment Processing',
    'admin': 'Platform & Admin',
    'jobcost': 'Job Costing',
    'consolidation': 'Consolidation',
    'reconcile': 'Reconcile',
    'open': 'Open',
    'closed': 'Closed',
}

PACKS = {
    'en': {
        **_COMMON,
        'platform_title': 'Platform & Administration',
        'gl_title': 'General Ledger',
        'consolidation_title': 'G/L Consolidation',
        'ap_title': 'Accounts Payable',
        'ar_title': 'Accounts Receivable',
        'fiscal_calendar': 'Fiscal calendar',
        'integrity_ok': 'Data integrity OK',
        'integrity_issues': 'Integrity issues found',
        'cash_workbench': 'Cash application workbench',
        'credit_review': 'Credit review',
        'screen_permissions': 'Screen permissions',
    },
    'fr': {
        **_COMMON,
        'platform_title': 'Plateforme et administration',
        'gl_title': 'Grand livre',
        'consolidation_title': 'Consolidation GL',
        'ap_title': 'Comptes fournisseurs',
        'ar_title': 'Comptes clients',
        'fiscal_calendar': 'Calendrier fiscal',
        'integrity_ok': 'Intégrité des données OK',
        'integrity_issues': 'Problèmes d\'intégrité',
        'cash_workbench': 'Application des encaissements',
        'credit_review': 'Révision de crédit',
        'screen_permissions': 'Autorisations d\'écran',
    },
    'es': {
        **_COMMON,
        'platform_title': 'Plataforma y administración',
        'gl_title': 'Libro mayor',
        'consolidation_title': 'Consolidación GL',
        'ap_title': 'Cuentas por pagar',
        'ar_title': 'Cuentas por cobrar',
        'fiscal_calendar': 'Calendario fiscal',
        'integrity_ok': 'Integridad de datos OK',
        'integrity_issues': 'Problemas de integridad',
        'cash_workbench': 'Aplicación de cobros',
        'credit_review': 'Revisión de crédito',
        'screen_permissions': 'Permisos de pantalla',
    },
    'zh': {
        **_COMMON,
        'platform_title': '平台管理',
        'gl_title': '总账',
        'consolidation_title': '合并报表',
        'ap_title': '应付账款',
        'ar_title': '应收账款',
        'fiscal_calendar': '会计期间',
        'integrity_ok': '数据完整性正常',
        'integrity_issues': '发现完整性问题',
        'cash_workbench': '收款核销',
        'credit_review': '信用审核',
        'screen_permissions': '屏幕权限',
    },
}


def translate(lang, key, default=None):
    pack = PACKS.get((lang or 'en')[:2].lower()) or PACKS['en']
    if (lang or '')[:2].lower() == 'zh':
        pack = PACKS.get('zh') or pack
    return pack.get(key) or PACKS['en'].get(key) or default or key


def pack_for_lang(lang):
    base = dict(PACKS['en'])
    code = (lang or 'en')[:2].lower()
    if code == 'zh':
        overlay = PACKS.get('zh') or {}
    else:
        overlay = PACKS.get(code) or {}
    base.update(overlay)
    return base
