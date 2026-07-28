"""Turn-by-turn directions and mileage via OSRM (OpenStreetMap routing)."""
from __future__ import annotations

import urllib.parse
from typing import Any

from plugin_security import build_osrm_url, escape_html_text, safe_http_json, validate_coordinates

OSRM_BASE = 'https://router.project-osrm.org/route/v1/driving'


def _http_json(url: str, *, headers: dict | None = None, timeout: int = 20) -> dict:
    try:
        return safe_http_json(url, headers=headers, timeout=timeout)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc
    except RuntimeError:
        raise
    except Exception as exc:
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
    o_lat, o_lng = validate_coordinates(origin_lat, origin_lng)
    d_lat, d_lng = validate_coordinates(dest_lat, dest_lng)
    path = build_osrm_url(o_lng, o_lat, d_lng, d_lat)
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
        f'<li>{escape_html_text(s.get("instruction", "Continue"))}'
        f'{(" on " + escape_html_text(s["name"])) if s.get("name") else ""}'
        f' — {escape_html_text(s.get("distance_miles", 0))} mi</li>'
        for s in steps[:15]
    )
    o_label = escape_html_text(origin.get('label') or 'Your location')
    d_label = escape_html_text(dest.get('label') or 'Job site')
    dist = escape_html_text(directions.get('distance_miles'))
    dur = escape_html_text(directions.get('duration_minutes'))
    gmaps = escape_html_text(links.get('google_maps', '#'))
    amaps = escape_html_text(links.get('apple_maps', '#'))
    return f"""
    <div style="font-family:Arial,sans-serif;line-height:1.5;color:#111;">
      <h2 style="margin:0 0 12px;">Driving directions</h2>
      <p><strong>From:</strong> {o_label}<br>
         <strong>To:</strong> {d_label}</p>
      <p style="font-size:18px;"><strong>{dist} miles</strong>
         · about <strong>{dur} minutes</strong></p>
      <p>
        <a href="{gmaps}" style="display:inline-block;margin-right:12px;padding:10px 16px;background:#059669;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;">Open in Google Maps</a>
        <a href="{amaps}" style="display:inline-block;padding:10px 16px;background:#2563eb;color:#fff;text-decoration:none;border-radius:6px;font-weight:600;">Open in Apple Maps</a>
      </p>
      <h3 style="margin:16px 0 8px;">Turn-by-turn</h3>
      <ol style="padding-left:20px;">{step_rows}</ol>
      <p style="font-size:12px;color:#666;margin-top:16px;">Mileage for reimbursement: <strong>{dist} miles</strong></p>
    </div>
    """
