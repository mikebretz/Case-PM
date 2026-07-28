"""Turn-by-turn directions and mileage via OSRM (OpenStreetMap routing)."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

OSRM_BASE = 'https://router.project-osrm.org/route/v1/driving'


def _http_json(url: str, *, headers: dict | None = None, timeout: int = 20) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(detail or exc.reason) from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(str(exc)) from exc


def _meters_to_miles(meters: float) -> float:
    return round(float(meters) / 1609.344, 2)


def _seconds_to_minutes(seconds: float) -> int:
    return int(round(float(seconds) / 60))


def get_directions(
    origin_lat: float,
    origin_lng: float,
    dest_lat: float,
    dest_lng: float,
    *,
    origin_label: str = '',
    dest_label: str = '',
) -> dict[str, Any]:
    """Return driving route with distance, duration, steps, and mobile map links."""
    path = f"{OSRM_BASE}/{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
    params = urllib.parse.urlencode({
        'overview': 'full',
        'geometries': 'geojson',
        'steps': 'true',
        'annotations': 'distance,duration',
    })
    data = _http_json(f'{path}?{params}')
    if data.get('code') != 'Ok' or not data.get('routes'):
        raise RuntimeError(data.get('message') or 'Could not calculate route')

    route = data['routes'][0]
    distance_m = route.get('distance') or 0
    duration_s = route.get('duration') or 0
    geometry = (route.get('geometry') or {}).get('coordinates') or []

    steps = []
    for leg in route.get('legs') or []:
        for step in leg.get('steps') or []:
            maneuver = step.get('maneuver') or {}
            steps.append({
                'instruction': maneuver.get('modifier') or maneuver.get('type') or 'continue',
                'name': (step.get('name') or '').strip(),
                'distance_miles': _meters_to_miles(step.get('distance') or 0),
                'duration_minutes': _seconds_to_minutes(step.get('duration') or 0),
            })

    dest_query = dest_label or f'{dest_lat},{dest_lng}'
    google_maps = (
        'https://www.google.com/maps/dir/?api=1'
        + f'&origin={origin_lat},{origin_lng}'
        + f'&destination={urllib.parse.quote(dest_query)}'
        + '&travelmode=driving'
    )
    apple_maps = f'https://maps.apple.com/?saddr={origin_lat},{origin_lng}&daddr={dest_lat},{dest_lng}&dirflg=d'

    return {
        'origin': {'latitude': origin_lat, 'longitude': origin_lng, 'label': origin_label},
        'destination': {'latitude': dest_lat, 'longitude': dest_lng, 'label': dest_label},
        'distance_miles': _meters_to_miles(distance_m),
        'distance_meters': round(distance_m),
        'duration_minutes': _seconds_to_minutes(duration_s),
        'duration_seconds': int(duration_s),
        'geometry': geometry,
        'steps': steps[:40],
        'links': {
            'google_maps': google_maps,
            'apple_maps': apple_maps,
        },
        'mileage_reimbursement_note': (
            f'Driving distance: {_meters_to_miles(distance_m)} miles '
            f'(approx. {_seconds_to_minutes(duration_s)} min)'
        ),
    }


def build_directions_email_html(directions: dict[str, Any]) -> str:
    dest = directions.get('destination') or {}
    origin = directions.get('origin') or {}
    steps = directions.get('steps') or []
    links = directions.get('links') or {}
    step_rows = ''.join(
        f'<li>{s.get("instruction", "Continue")}'
        f'{(" on " + s["name"]) if s.get("name") else ""}'
        f' — {s.get("distance_miles", 0)} mi</li>'
        for s in steps[:15]
    )
    return f"""
    <div style="font-family:Arial,sans-serif;line-height:1.5;color:#111;">
      <h2 style="margin:0 0 12px;">Driving directions</h2>
      <p><strong>From:</strong> {origin.get('label') or 'Your location'}<br>
         <strong>To:</strong> {dest.get('label') or 'Job site'}</p>
      <p style="font-size:18px;"><strong>{directions.get('distance_miles')} miles</strong>
         · about <strong>{directions.get('duration_minutes')} minutes</strong></p>
      <p>
        <a href="{links.get('google_maps', '#')}" style="display:inline-block;margin-right:12px;padding:10px 16px;background:#059669;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;">Open in Google Maps</a>
        <a href="{links.get('apple_maps', '#')}" style="display:inline-block;padding:10px 16px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;">Open in Apple Maps</a>
      </p>
      <h3 style="margin:16px 0 8px;">Turn-by-turn</h3>
      <ol style="padding-left:20px;">{step_rows}</ol>
      <p style="font-size:12px;color:#666;margin-top:16px;">Mileage for reimbursement: <strong>{directions.get('distance_miles')} miles</strong></p>
    </div>
    """
