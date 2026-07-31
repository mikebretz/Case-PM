"""Accounting UI strings — multi-language (en, fr, es)."""
from __future__ import annotations

PACKS = {
    'en': {
        'platform_title': 'Platform & Administration',
        'gl_title': 'General Ledger',
        'consolidation_title': 'G/L Consolidation',
        'ap_title': 'Accounts Payable',
        'ar_title': 'Accounts Receivable',
        'fiscal_calendar': 'Fiscal calendar',
        'integrity_ok': 'Data integrity OK',
        'integrity_issues': 'Integrity issues found',
    },
    'fr': {
        'platform_title': 'Plateforme et administration',
        'gl_title': 'Grand livre',
        'consolidation_title': 'Consolidation GL',
        'ap_title': 'Comptes fournisseurs',
        'ar_title': 'Comptes clients',
        'fiscal_calendar': 'Calendrier fiscal',
        'integrity_ok': 'Intégrité des données OK',
        'integrity_issues': 'Problèmes d\'intégrité',
    },
    'es': {
        'platform_title': 'Plataforma y administración',
        'gl_title': 'Libro mayor',
        'consolidation_title': 'Consolidación GL',
        'ap_title': 'Cuentas por pagar',
        'ar_title': 'Cuentas por cobrar',
        'fiscal_calendar': 'Calendario fiscal',
        'integrity_ok': 'Integridad de datos OK',
        'integrity_issues': 'Problemas de integridad',
    },
}


def translate(lang, key, default=None):
    pack = PACKS.get((lang or 'en')[:2].lower()) or PACKS['en']
    return pack.get(key) or PACKS['en'].get(key) or default or key


def pack_for_lang(lang):
    base = dict(PACKS['en'])
    overlay = PACKS.get((lang or 'en')[:2].lower()) or {}
    base.update(overlay)
    return base
