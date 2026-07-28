"""Geocoding and job-location helpers (Nominatim + Open-Meteo + project addresses)."""
from __future__ import annotations

import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

OPEN_METEO_GEOCODE = 'https://geocoding-api.open-meteo.com/v1/search'
NOMINATIM_SEARCH = 'https://nominatim.openstreetmap.org/search'
USER_AGENT = 'CasePM/1.0 (construction project management)'

# Florida bounding box — biases Nominatim results without excluding other US states.
FLORIDA_VIEWBOX = '-87.6349,24.3963,-79.9743,31.0009'

ACTIVE_JOB_STATUSES = frozenset({'Active', 'Pre-Construction', 'In Progress'})

US_COUNTRY_NAMES = frozenset({
    'united states',
    'united states of america',
    'usa',
    'us',
})

BUSINESS_OSM_CLASSES = frozenset({'shop', 'amenity', 'office', 'craft', 'tourism', 'leisure', 'commercial'})


def _http_json(url: str, timeout: int = 10, headers: dict | None = None) -> dict | list:
    from plugin_security import safe_http_json
    return safe_http_json(url, timeout=timeout, headers=headers)


def _parse_float(val) -> float | None:
    try:
        if val in (None, ''):
            return None
        return float(val)
    except (TypeError, ValueError):
        return None


def _normalize_state(state: str | None) -> str:
    raw = (state or '').strip().upper()
    if raw in ('FL', 'FLORIDA'):
        return 'FL'
    if len(raw) == 2:
        return raw
    return raw[:2] if raw else ''


def _is_us_country(country: str | None, country_code: str | None = None) -> bool:
    code = (country_code or '').strip().upper()
    if code == 'US':
        return True
    name = (country or '').strip().lower()
    return name in US_COUNTRY_NAMES


def _florida_rank(state: str | None) -> int:
    return 0 if _normalize_state(state) == 'FL' else 1


def _haversine_miles(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    rlat1, rlng1, rlat2, rlng2 = map(math.radians, [lat1, lng1, lat2, lng2])
    dlat = rlat2 - rlat1
    dlng = rlng2 - rlng1
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlng / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(a))


def _distance_rank(loc: dict[str, Any], near_lat: float | None, near_lng: float | None) -> float:
    if near_lat is None or near_lng is None:
        return 999999.0
    lat = loc.get('latitude')
    lng = loc.get('longitude')
    if lat is None or lng is None:
        return 999999.0
    return _haversine_miles(float(near_lat), float(near_lng), float(lat), float(lng))


def _annotate_distance(loc: dict[str, Any], near_lat: float | None, near_lng: float | None) -> dict[str, Any]:
    out = dict(loc)
    miles = _distance_rank(out, near_lat, near_lng)
    if miles < 999999:
        out['distance_miles'] = round(miles, 1)
    return out


def _florida_project_rank(loc: dict[str, Any]) -> int:
    return _florida_rank(loc.get('state'))


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
        'countryCode': 'US',
    })
    data = _http_json(f'{OPEN_METEO_GEOCODE}?{params}')
    results = []
    for row in data.get('results') or []:
        if not _is_us_country(row.get('country'), row.get('country_code')):
            continue
        lat = row.get('latitude')
        lng = row.get('longitude')
        if lat is None or lng is None:
            continue
        state = row.get('admin1_code') or row.get('admin1') or ''
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
            'state': state,
            'country': row.get('country') or 'United States',
            'latitude': lat,
            'longitude': lng,
            'source': 'geocode',
            'kind': 'address',
        })
    results.sort(key=lambda r: (_florida_rank(r.get('state')), r.get('label') or ''))
    return results


def _nominatim_kind(row: dict[str, Any]) -> str:
    osm_class = (row.get('class') or '').lower()
    place_type = (row.get('type') or '').lower()
    if osm_class in BUSINESS_OSM_CLASSES or place_type in BUSINESS_OSM_CLASSES:
        return 'business'
    if place_type in ('house', 'building', 'residential', 'commercial', 'industrial'):
        return 'address'
    if row.get('name') and osm_class not in ('highway', 'place'):
        return 'business'
    return 'address'


def _nominatim_subtitle(kind: str) -> str:
    if kind == 'business':
        return 'Business / place · United States'
    return 'US address'


def _nominatim_row_to_suggestion(row: dict[str, Any]) -> dict[str, Any] | None:
    addr = row.get('address') or {}
    country = addr.get('country') or ''
    country_code = addr.get('country_code') or ''
    if not _is_us_country(country, country_code):
        return None
    try:
        lat = float(row.get('lat'))
        lng = float(row.get('lon'))
    except (TypeError, ValueError):
        return None
    state = addr.get('state') or ''
    city = addr.get('city') or addr.get('town') or addr.get('village') or ''
    name = (row.get('name') or '').strip()
    street = ' '.join(filter(None, [addr.get('house_number'), addr.get('road')])).strip()
    if name and street and name.lower() not in street.lower():
        label = f"{name}, {street}, {city}, {state}".strip(', ')
    elif name:
        label = f"{name}, {city}, {state}".strip(', ')
    else:
        label = row.get('display_name') or ''
    label = re.sub(r',\s*,', ',', label).strip(' ,')
    kind = _nominatim_kind(row)
    return {
        'id': f"nom_{row.get('osm_id', row.get('place_id', ''))}",
        'label': label,
        'address': label,
        'name': name,
        'city': city,
        'state': state,
        'country': country or 'United States',
        'latitude': lat,
        'longitude': lng,
        'source': 'nominatim',
        'kind': kind,
        'subtitle': _nominatim_subtitle(kind),
    }


def search_nominatim_us(query: str, *, limit: int = 8, near_lat: float | None = None, near_lng: float | None = None) -> list[dict[str, Any]]:
    q = (query or '').strip()
    if len(q) < 2:
        return []
    params = urllib.parse.urlencode({
        'q': q,
        'format': 'json',
        'limit': max(1, min(int(limit), 20 if near_lat is not None else 15)),
        'addressdetails': 1,
        'countrycodes': 'us',
        'viewbox': FLORIDA_VIEWBOX,
    })
    rows = _http_json(
        f'{NOMINATIM_SEARCH}?{params}',
        timeout=12,
        headers={'User-Agent': USER_AGENT},
    )
    if not isinstance(rows, list):
        return []
    results = []
    for row in rows:
        suggestion = _nominatim_row_to_suggestion(row)
        if suggestion:
            results.append(_annotate_distance(suggestion, near_lat, near_lng))
    if near_lat is not None and near_lng is not None:
        results.sort(key=lambda r: (_florida_rank(r.get('state')), r.get('distance_miles', 999999), r.get('label') or ''))
    else:
        results.sort(key=lambda r: (_florida_rank(r.get('state')), 0 if r.get('kind') == 'business' else 1, r.get('label') or ''))
    return results[:limit]


def closest_us_location(query: str, near_lat: float, near_lng: float) -> dict[str, Any] | None:
    """Return the closest US match (e.g. nearest Walmart to a job site)."""
    hits = search_nominatim_us(query, limit=20, near_lat=near_lat, near_lng=near_lng)
    if hits:
        return hits[0]
    try:
        rows = geocode_query(query, count=10)
        rows = [_annotate_distance(row, near_lat, near_lng) for row in rows]
        rows.sort(key=lambda r: r.get('distance_miles', 999999))
        return rows[0] if rows else None
    except RuntimeError:
        return None


def geocode_address_nominatim(query: str) -> dict[str, Any] | None:
    hits = search_nominatim_us(query, limit=1)
    return hits[0] if hits else None


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

    # Prefer Nominatim for full street addresses and business names (US-only).
    if out.get('address') or ',' in full_query or len(full_query.split()) <= 4:
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


def search_address_suggestions(
    query: str,
    projects=None,
    *,
    limit: int = 12,
    near_lat: float | None = None,
    near_lng: float | None = None,
) -> list[dict[str, Any]]:
    """Autocomplete: FL job sites first, then closest US businesses/addresses to near_lat/lng."""
    q = (query or '').strip().lower()
    if len(q) < 2:
        return []
    suggestions: list[dict[str, Any]] = []
    seen = set()

    project_matches = []
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
            loc.get('client') or '',
        ]).lower()
        if q not in hay:
            continue
        if loc.get('latitude') is None or loc.get('longitude') is None:
            loc = geocode_project_location(loc)
        project_matches.append(loc)

    project_matches.sort(key=lambda loc: (
        _florida_project_rank(loc),
        _distance_rank(loc, near_lat, near_lng),
        loc.get('name') or '',
    ))
    for loc in project_matches:
        key = f"project:{loc.get('id')}"
        if key in seen:
            continue
        seen.add(key)
        state = loc.get('state') or ''
        fl_note = ' · Florida' if _normalize_state(state) == 'FL' else ''
        dist_note = ''
        annotated = _annotate_distance(loc, near_lat, near_lng)
        if annotated.get('distance_miles') is not None:
            dist_note = f" · {annotated['distance_miles']} mi"
        suggestions.append({
            **annotated,
            'kind': 'project',
            'subtitle': f"Job site · {loc.get('status') or 'Active'}{fl_note}{dist_note}",
        })
        if len(suggestions) >= limit:
            return suggestions

    try:
        nom_limit = max(10, limit - len(suggestions)) if near_lat is not None else max(6, limit - len(suggestions))
        for row in search_nominatim_us(query, limit=nom_limit, near_lat=near_lat, near_lng=near_lng):
            key = f"nom:{row.get('label')}"
            if key in seen:
                continue
            seen.add(key)
            subtitle = row.get('subtitle') or 'US address'
            if row.get('distance_miles') is not None:
                subtitle = f"{subtitle} · {row['distance_miles']} mi to job"
            suggestions.append({**row, 'subtitle': subtitle})
            if len(suggestions) >= limit:
                return suggestions[:limit]
    except RuntimeError:
        pass

    try:
        for row in geocode_query(query, count=max(4, limit - len(suggestions))):
            key = f"geo:{row.get('label')}"
            if key in seen:
                continue
            seen.add(key)
            suggestions.append({
                **row,
                'kind': row.get('kind') or 'address',
                'subtitle': 'US city / address',
            })
            if len(suggestions) >= limit:
                break
    except RuntimeError:
        pass
    return suggestions[:limit]
