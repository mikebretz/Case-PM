"""Sage 300 Web API (OData) client for Case PM Accounting inquiries."""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request


def _load_program_sage_url() -> str:
    try:
        from program_settings_persistence import load_sage_defaults
        return (load_sage_defaults().get('sage_api_url') or '').strip()
    except Exception:
        return ''


def resolve_web_api_config():
    """
    Returns dict with base_url, company, user, password, mode.
    base_url should end before /v1.0/... or include full path through /v1.0/-/
    """
    base = (
        os.environ.get('SAGE300_WEB_API_URL', '').strip()
        or os.environ.get('SAGE_WEB_API_URL', '').strip()
        or _load_program_sage_url()
    )
    # CRE bridge URL is not OData — detect and skip
    if base and '/api/v1/' in base and 'Sage300WebApi' not in base:
        base = ''
    company = (
        os.environ.get('SAGE300_COMPANY', '').strip()
        or os.environ.get('SAGE_COMPANY', '').strip()
    )
    if not company:
        try:
            from program_settings_persistence import load_sage_defaults
            company = (load_sage_defaults().get('sage_company_code') or '').strip()
        except Exception:
            company = ''
    user = os.environ.get('SAGE300_WEB_USER', '').strip() or os.environ.get('SAGE_WEB_USER', '').strip()
    password = os.environ.get('SAGE300_WEB_PASSWORD', '').strip() or os.environ.get('SAGE_WEB_PASSWORD', '').strip()
    version = os.environ.get('SAGE300_API_VERSION', '1.0').strip() or '1.0'
    if not base:
        return {
            'configured': False,
            'base_url': '',
            'company': company,
            'mode': 'unconfigured',
        }
    base = base.rstrip('/')
    if 'Sage300WebApi' in base and '/v' not in base.split('Sage300WebApi')[-1]:
        base = f'{base}/v{version}/-'
    elif not base.endswith('/-'):
        if '/v' in base and not base.endswith('/-'):
            base = base if base.endswith('/') else base + '/'
            if not base.endswith('/-'):
                base = base.rstrip('/') + '/-'
    return {
        'configured': bool(base and company),
        'base_url': base,
        'company': company or 'SAMLTD',
        'user': user,
        'password': password,
        'mode': 'web_api' if user and password else 'web_api_no_credentials',
    }


def _auth_header(user: str, password: str) -> str:
    token = base64.b64encode(f'{user}:{password}'.encode('utf-8')).decode('ascii')
    return f'Basic {token}'


def build_resource_url(company: str, module: str, resource: str, *, top: int = 25, skip: int = 0, filters: str = '') -> str:
    cfg = resolve_web_api_config()
    base = cfg['base_url'].rstrip('/')
    co = urllib.parse.quote((company or cfg['company'] or 'SAMLTD').strip())
    mod = urllib.parse.quote((module or '').strip())
    res = urllib.parse.quote((resource or '').strip())
    path = f'{base}/{co}/{mod}/{res}'
    params = []
    if top:
        params.append(f'$top={int(top)}')
    if skip:
        params.append(f'$skip={int(skip)}')
    if filters:
        params.append(filters if filters.startswith('$') else f'$filter={filters}')
    if params:
        path += '?' + '&'.join(params)
    return path


def get_resource(
    module: str,
    resource: str,
    *,
    company: str = '',
    top: int = 25,
    skip: int = 0,
    filters: str = '',
) -> dict:
    cfg = resolve_web_api_config()
    if not cfg.get('configured'):
        return {
            'ok': False,
            'mode': 'unconfigured',
            'error': 'Sage 300 Web API URL and company code required (Program Settings → Sage 300 or SAGE300_WEB_API_URL).',
        }
    if not cfg.get('user') or not cfg.get('password'):
        return {
            'ok': False,
            'mode': 'simulated',
            'error': 'Set SAGE300_WEB_USER and SAGE300_WEB_PASSWORD for live Web API reads.',
            'url': build_resource_url(company, module, resource, top=top, skip=skip, filters=filters),
        }
    url = build_resource_url(company, module, resource, top=top, skip=skip, filters=filters)
    try:
        req = urllib.request.Request(
            url,
            headers={
                'Accept': 'application/json',
                'Authorization': _auth_header(cfg['user'], cfg['password']),
            },
            method='GET',
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode('utf-8')
            data = json.loads(body) if body else {}
            return {'ok': True, 'mode': 'live', 'url': url, 'data': data}
    except urllib.error.HTTPError as exc:
        err_body = ''
        try:
            err_body = exc.read().decode('utf-8')[:500]
        except Exception:
            pass
        return {'ok': False, 'mode': 'error', 'url': url, 'error': f'HTTP {exc.code}: {err_body or exc.reason}'}
    except Exception as exc:
        return {'ok': False, 'mode': 'error', 'url': url, 'error': str(exc)}


def probe_connection() -> dict:
    cfg = resolve_web_api_config()
    bridge = os.environ.get('SAGE_API_URL', '').strip()
    result = {
        'web_api': {
            'configured': cfg.get('configured'),
            'base_url': cfg.get('base_url'),
            'company': cfg.get('company'),
            'has_credentials': bool(cfg.get('user') and cfg.get('password')),
            'mode': cfg.get('mode'),
        },
        'cre_bridge': {
            'configured': bool(bridge),
            'url': bridge,
        },
    }
    if cfg.get('configured') and cfg.get('user') and cfg.get('password'):
        ping = get_resource('AR', 'ARCustomers', top=1)
        result['web_api']['probe'] = {
            'ok': ping.get('ok'),
            'error': ping.get('error'),
        }
    elif cfg.get('configured'):
        result['web_api']['probe'] = {'ok': False, 'error': 'Credentials not set'}
    else:
        result['web_api']['probe'] = {'ok': False, 'error': 'Web API not configured'}
    return result
