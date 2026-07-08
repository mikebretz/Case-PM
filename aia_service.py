"""AIA Contract Documents (Catina) integration helpers — deep links and document registration."""
from __future__ import annotations

import os
import urllib.parse


CATINA_PORTAL_URL = os.environ.get('AIA_CATINA_PORTAL_URL', 'https://contractdocs.aia.org').rstrip('/')


def is_catina_configured():
    return bool(os.environ.get('AIA_CATINA_ORG_ID', '').strip() or os.environ.get('AIA_CATINA_ENABLED', '').strip() == '1')


def integration_info():
    return {
        'catina': {
            'configured': is_catina_configured(),
            'portal_url': CATINA_PORTAL_URL,
            'org_id': os.environ.get('AIA_CATINA_ORG_ID', '').strip() or None,
            'required_env': ['AIA_CATINA_ORG_ID or AIA_CATINA_ENABLED=1'],
            'note': 'Official licensed AIA forms are created and executed in AIA Contract Documents (Catina). Case PM links commitments to Catina documents.',
        },
        'docusign_via_catina': {
            'note': 'Catina includes built-in DocuSign eSignature for AIA documents. Prefer Catina for official AIA execution.',
        },
    }


def build_catina_create_url(commitment_dict, project_dict=None):
    """
    Build deep link to AIA Contract Documents for creating a document from commitment data.
    Catina does not expose a public create API in all tiers — this opens the portal with context params.
    """
    project_dict = project_dict or {}
    form = commitment_dict.get('aia_form') or 'A401'
    params = {
        'source': 'CasePM',
        'form': form,
        'ref': commitment_dict.get('number') or '',
        'project': project_dict.get('name') or project_dict.get('number') or '',
    }
    org = os.environ.get('AIA_CATINA_ORG_ID', '').strip()
    if org:
        params['org'] = org
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v})
    return f'{CATINA_PORTAL_URL}/documents/new?{query}'


def build_catina_open_url(external_document_id=None, external_document_url=None):
    if external_document_url:
        return external_document_url
    if external_document_id:
        return f'{CATINA_PORTAL_URL}/documents/{urllib.parse.quote(str(external_document_id))}'
    return CATINA_PORTAL_URL


def register_external_document(commitment, provider, document_id, document_url=None, catina_project_id=None):
    """Store linkage to official AIA / external document on commitment model."""
    commitment.external_document_provider = provider
    commitment.external_document_id = document_id
    if document_url:
        commitment.external_document_url = document_url
    if catina_project_id:
        commitment.catina_project_id = catina_project_id
    return commitment


def commitment_export_for_catina(commitment_dict):
    """Structured field export for handoff to AIA Contract Documents."""
    return {
        'casepm_commitment_id': commitment_dict.get('id'),
        'number': commitment_dict.get('number'),
        'aia_form': commitment_dict.get('aia_form'),
        'commitment_type': commitment_dict.get('commitment_type'),
        'title': commitment_dict.get('title'),
        'description': commitment_dict.get('description'),
        'scope_of_work': commitment_dict.get('scope_of_work'),
        'contract_sum': commitment_dict.get('current_amount'),
        'retainage_percent': commitment_dict.get('retainage_percent'),
        'payment_terms': commitment_dict.get('payment_terms'),
        'dates': {
            'contract': commitment_dict.get('date'),
            'start': commitment_dict.get('start_date'),
            'end': commitment_dict.get('end_date'),
        },
        'parties': {
            'owner': commitment_dict.get('owner_name'),
            'contractor': commitment_dict.get('contractor_name'),
            'architect': commitment_dict.get('architect_engineer'),
            'subcontractor': commitment_dict.get('company_name'),
            'contact_email': commitment_dict.get('contact_email'),
        },
        'allocations': commitment_dict.get('allocations') or [],
        'aia_contract': commitment_dict.get('aia_contract'),
    }
