"""DocuSign eSignature integration for commitments (optional — requires env configuration)."""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime


def is_configured():
    return bool(
        os.environ.get('DOCUSIGN_INTEGRATION_KEY', '').strip()
        and os.environ.get('DOCUSIGN_USER_ID', '').strip()
        and os.environ.get('DOCUSIGN_ACCOUNT_ID', '').strip()
        and (
            os.environ.get('DOCUSIGN_PRIVATE_KEY', '').strip()
            or os.environ.get('DOCUSIGN_PRIVATE_KEY_PATH', '').strip()
        )
    )


def integration_info():
    base = os.environ.get('DOCUSIGN_BASE_URL', 'https://demo.docusign.net/restapi').strip()
    return {
        'configured': is_configured(),
        'base_url': base,
        'auth': 'jwt',
        'webhook_path': '/api/webhooks/docusign',
        'required_env': [
            'DOCUSIGN_INTEGRATION_KEY',
            'DOCUSIGN_USER_ID',
            'DOCUSIGN_ACCOUNT_ID',
            'DOCUSIGN_PRIVATE_KEY or DOCUSIGN_PRIVATE_KEY_PATH',
        ],
    }


def _load_private_key():
    raw = os.environ.get('DOCUSIGN_PRIVATE_KEY', '').strip()
    if raw:
        return raw.replace('\\n', '\n')
    path = os.environ.get('DOCUSIGN_PRIVATE_KEY_PATH', '').strip()
    if path and os.path.isfile(path):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    return None


def _get_access_token():
    """Obtain DocuSign JWT access token. Returns (token, error)."""
    if not is_configured():
        return None, 'DocuSign not configured'

    try:
        import jwt  # PyJWT — optional dependency
    except ImportError:
        return None, 'PyJWT not installed — add PyJWT to requirements for live DocuSign'

    integration_key = os.environ.get('DOCUSIGN_INTEGRATION_KEY', '').strip()
    user_id = os.environ.get('DOCUSIGN_USER_ID', '').strip()
    private_key = _load_private_key()
    if not private_key:
        return None, 'DocuSign private key missing'

    auth_server = os.environ.get('DOCUSIGN_AUTH_SERVER', 'account-d.docusign.com').strip()
    now = int(datetime.utcnow().timestamp())
    claim = {
        'iss': integration_key,
        'sub': user_id,
        'aud': auth_server,
        'iat': now,
        'exp': now + 3600,
        'scope': 'signature impersonation',
    }
    assertion = jwt.encode(claim, private_key, algorithm='RS256')

    import urllib.parse
    import urllib.request

    data = urllib.parse.urlencode({
        'grant_type': 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        'assertion': assertion,
    }).encode('utf-8')
    req = urllib.request.Request(
        f'https://{auth_server}/oauth/token',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode('utf-8'))
            return body.get('access_token'), None
    except Exception as exc:
        return None, str(exc)


def send_commitment_envelope(commitment_dict, pdf_bytes=None, pdf_filename='commitment.pdf'):
    """
    Create DocuSign envelope for a commitment.
    commitment_dict: output of commitment_to_dict()
    Returns { envelope_id, status, url?, simulated? }
    """
    if not is_configured():
        return {
            'simulated': True,
            'envelope_id': f'ENV-{commitment_dict.get("id")}-{int(datetime.utcnow().timestamp())}',
            'status': 'sent',
            'message': 'DocuSign not configured — simulated envelope ID assigned',
        }

    token, err = _get_access_token()
    if err:
        return {'simulated': True, 'error': err, 'status': 'error'}

    account_id = os.environ.get('DOCUSIGN_ACCOUNT_ID', '').strip()
    base = os.environ.get('DOCUSIGN_BASE_URL', 'https://demo.docusign.net/restapi').rstrip('/')

    signer_email = commitment_dict.get('contact_email') or os.environ.get('DOCUSIGN_DEFAULT_SIGNER_EMAIL', '')
    signer_name = commitment_dict.get('contact_name') or commitment_dict.get('company_name') or 'Subcontractor'
    if not signer_email:
        return {'simulated': True, 'error': 'No signer email on commitment', 'status': 'error'}

    document_b64 = base64.b64encode(pdf_bytes or b'%PDF-1.4\n% Case PM commitment placeholder').decode('ascii')
    envelope = {
        'emailSubject': f'Please sign {commitment_dict.get("number")} — {commitment_dict.get("title") or commitment_dict.get("description")}',
        'documents': [{
            'documentBase64': document_b64,
            'name': pdf_filename,
            'fileExtension': 'pdf',
            'documentId': '1',
        }],
        'recipients': {
            'signers': [{
                'email': signer_email,
                'name': signer_name,
                'recipientId': '1',
                'routingOrder': '1',
                'tabs': {
                    'signHereTabs': [{'documentId': '1', 'pageNumber': '1', 'xPosition': '100', 'yPosition': '700'}],
                    'dateSignedTabs': [{'documentId': '1', 'pageNumber': '1', 'xPosition': '300', 'yPosition': '700'}],
                },
            }],
        },
        'status': 'sent',
    }

    import urllib.request
    req = urllib.request.Request(
        f'{base}/v2.1/accounts/{account_id}/envelopes',
        data=json.dumps(envelope).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode('utf-8'))
            return {
                'envelope_id': body.get('envelopeId'),
                'status': body.get('status', 'sent'),
                'uri': body.get('uri'),
            }
    except Exception as exc:
        return {'simulated': False, 'error': str(exc), 'status': 'error'}


def parse_webhook_payload(body_bytes):
    """Parse DocuSign Connect webhook JSON."""
    try:
        data = json.loads(body_bytes.decode('utf-8'))
    except (TypeError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return data
