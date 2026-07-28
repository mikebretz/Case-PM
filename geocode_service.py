"""Geocoding and job-location helpers (Open-Meteo + project addresses)."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

OPEN_METEO_GEOCODE = 'https://geocoding-api.open-meteo.com/v1/search'
NOMINATIM_SEARCH = 'https://nominatim.openstreetmap.org/search'
USER_AGENT = 'CasePM/1.0 (construction project management)'


ACTIVE_JOB_STATUSES = frozenset({'Active', 'Pre-Construction', 'In Progress'})


def _http_json(url: str, timeout: int = 10) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(str(exc)) from exc


def _parse_float(val) -> float | None:
    try:
        if val in (None, ''):
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def project_location_dict(project) -> dict[str, Any]:
    """Normalize a Project model or dict into a location payload."""
    if hasattr(project, 'to_dict'):
        data = project.to_dict()
    elif isinstance(project, dict):
        data = dict(project)
    else:
        data = {}

    lat = _parse_float(data.get('latitude'))
    lng = _parse_float(data.get('longitude'))
    address = (data.get('address') or '').strip()
    city = (data.get('city') or '').strip()
    state = (data.get('state') or '').strip()
    zip_code = (data.get('zip_code') or data.get('zip') or '').strip()
    label_parts = [p for p in [address, ', '.join(x for x in [city, state] if x), zip_code] if p]
    return {
        'id': data.get('id'),
        'number': data.get('number') or '',
        'name': data.get('name') or '',
        'status': data.get('status') or 'Active',
        'client': data.get('client') or '',
        'address': address,
        'city': city,
        'state': state,
        'zip_code': zip_code,
        'store_number': data.get('store_number') or '',
        'latitude': lat,
        'longitude': lng,
        'label': data.get('address_display') or ', '.join(label_parts) or (data.get('name') or 'Job site'),
        'source': 'project',
    }


def geocode_query(query: str, *, count: int = 8) -> list[dict[str, Any]]:
    q = (query or '').strip()
    if len(q) < 2:
        return []
    params = urllib.parse.urlencode({
        'name': q,
        'count': max(1, min(int(count), 20)),
        'language': 'en',
        'format': 'json',
    })
    data = _http_json(f'{OPEN_METEO_GEOCODE}?{params}')
    results = []
    for row in data.get('results') or []:
        lat = row.get('latitude')
        lng = row.get('longitude')
        if lat is None or lng is None:
            continue
        label = ', '.join(filter(None, [
            row.get('name'),
            row.get('admin1'),
            row.get('country'),
        ]))
        results.append({
            'id': f"geo_{row.get('id', len(results))}",
            'label': label,
            'address': label,
            'city': row.get('name') or '',
            'state': row.get('admin1_code') or row.get('admin1') or '',
            'country': row.get('country') or '',
            'latitude': lat,
            'longitude': lng,
            'source': 'geocode',
        })
    return results


def geocode_address_nominatim(query: str) -> dict[str, Any] | None:
    q = (query or '').strip()
    if len(q) < 3:
        return None
    params = urllib.parse.urlencode({
        'q': q,
        'format': 'json',
        'limit': 1,
        'addressdetails': 1,
        'countrycodes': 'us',
    })
    req = urllib.request.Request(
        f'{NOMINATIM_SEARCH}?{params}',
        headers={'User-Agent': USER_AGENT},
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            rows = json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    if not rows:
        return None
    row = rows[0]
    addr = row.get('address') or {}
    return {
        'latitude': float(row.get('lat')),
        'longitude': float(row.get('lon')),
        'city': addr.get('city') or addr.get('town') or addr.get('village') or '',
        'state': addr.get('state') or '',
        'label': row.get('display_name') or q,
    }


def geocode_project_location(loc: dict[str, Any]) -> dict[str, Any]:
    """Fill missing latitude/longitude for a project location dict."""
    out = dict(loc)
    if out.get('latitude') is not None and out.get('longitude') is not None:
        return out
    query_bits = [out.get('address'), out.get('city'), out.get('state'), out.get('zip_code')]
    full_query = ', '.join(x for x in query_bits if x)
    if not full_query:
        full_query = out.get('name') or ''
    if not full_query:
        return out

    # Prefer Nominatim for full street addresses (better US coverage).
    if out.get('address') or ',' in full_query:
        nominatim = geocode_address_nominatim(full_query)
        if nominatim:
            out['latitude'] = nominatim['latitude']
            out['longitude'] = nominatim['longitude']
            if not out.get('city') and nominatim.get('city'):
                out['city'] = nominatim['city']
            if not out.get('state') and nominatim.get('state'):
                out['state'] = nominatim['state']
            out['geocoded'] = True
            out['geocode_source'] = 'nominatim'
            return out

    try:
        matches = geocode_query(full_query if not out.get('address') else (out.get('city') or full_query), count=3)
    except RuntimeError:
        matches = []
    if not matches and full_query != (out.get('city') or ''):
        nominatim = geocode_address_nominatim(full_query)
        if nominatim:
            out['latitude'] = nominatim['latitude']
            out['longitude'] = nominatim['longitude']
            out['geocoded'] = True
            out['geocode_source'] = 'nominatim'
            return out
    if not matches:
        return out
    state = (out.get('state') or '').upper()
    match = matches[0]
    if state:
        for candidate in matches:
            if state in (candidate.get('state') or '').upper():
                match = candidate
                break
    out['latitude'] = match.get('latitude')
    out['longitude'] = match.get('longitude')
    if not out.get('city') and match.get('city'):
        out['city'] = match['city']
    if not out.get('state') and match.get('state'):
        out['state'] = match['state']
    out['geocoded'] = True
    out['geocode_source'] = 'open_meteo'
    return out


def list_company_job_locations(projects, *, geocode_missing: bool = True, include_unmapped: bool = False) -> list[dict[str, Any]]:
    locations = []
    for project in projects or []:
        loc = project_location_dict(project)
        if not loc.get('label') and not loc.get('name'):
            continue
        has_coords = loc.get('latitude') is not None and loc.get('longitude') is not None
        if not has_coords and geocode_missing:
            loc = geocode_project_location(loc)
        mapped = loc.get('latitude') is not None and loc.get('longitude') is not None
        loc['mapped'] = mapped
        if mapped or include_unmapped:
            locations.append(loc)
    return locations


def is_active_job_status(status: str | None) -> bool:
    return (status or 'Active') in ACTIVE_JOB_STATUSES


def search_address_suggestions(query: str, projects=None, *, limit: int = 12) -> list[dict[str, Any]]:
    """Autocomplete: project job sites first, then geocoded addresses."""
    q = (query or '').strip().lower()
    if len(q) < 2:
        return []
    suggestions: list[dict[str, Any]] = []
    seen = set()

    for project in projects or []:
        loc = project_location_dict(project)
        hay = ' '.join([
            loc.get('name') or '',
            loc.get('number') or '',
            loc.get('label') or '',
            loc.get('address') or '',
            loc.get('city') or '',
            loc.get('state') or '',
            loc.get('store_number') or '',
        ]).lower()
        if q not in hay:
            continue
        if loc.get('latitude') is None or loc.get('longitude') is None:
            loc = geocode_project_location(loc)
        key = f"project:{loc.get('id')}"
        if key in seen:
            continue
        seen.add(key)
        suggestions.append({
            **loc,
            'kind': 'project',
            'subtitle': f"Job site · {loc.get('status') or 'Active'}",
        })
        if len(suggestions) >= limit:
            return suggestions

    try:
        for row in geocode_query(query, count=max(4, limit - len(suggestions))):
            key = f"geo:{row.get('label')}"
            if key in seen:
                continue
            seen.add(key)
            suggestions.append({
                **row,
                'kind': 'address',
                'subtitle': 'Address lookup',
            })
            if len(suggestions) >= limit:
                break
    except RuntimeError:
        pass
    return suggestions[:limit]
