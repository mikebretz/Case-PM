"""Bidder plan room business logic."""
from __future__ import annotations

import json
import os
from datetime import datetime

from werkzeug.security import generate_password_hash

SPECIALTY_OPTIONS = (
    'General contracting', 'Concrete', 'Masonry', 'Structural steel', 'Carpentry / framing',
    'Roofing', 'Waterproofing', 'Drywall', 'Painting', 'Flooring', 'Glazing',
    'HVAC', 'Plumbing', 'Electrical', 'Fire protection', 'Low voltage',
    'Earthwork / sitework', 'Paving', 'Landscaping', 'Demolition', 'Other',
)


def _json_load(raw, default=None):
    if default is None:
        default = []
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return default


def load_plan_room_settings():
    from program_settings_persistence import load_company_info
    company = load_company_info()
    return {
        'company_name': company.get('company_name') or 'Our Construction Company',
        'tagline': 'Partner with us on upcoming bid opportunities',
        'hero_body': (
            'Register your firm to receive invitations and view public bid opportunities. '
            'Our estimating team reviews every application before granting plan room access.'
        ),
        'primary_color': '#059669',
        'logo_data_url': company.get('logo_data_url') or '',
        'contact_email': company.get('company_phone') or '',
        'public_path': '/plan-room',
    }


def registration_to_dict(row, *, include_internal=False) -> dict:
    out = {
        'id': row.id,
        'status': row.status,
        'company_name': row.company_name,
        'contact_name': row.contact_name,
        'email': row.email,
        'phone': row.phone,
        'specialties': _json_load(row.specialties_json, []),
        'comments': row.comments,
        'created_at': row.created_at.isoformat() if row.created_at else None,
        'reviewed_at': row.reviewed_at.isoformat() if row.reviewed_at else None,
    }
    if include_internal:
        out.update({
            'user_id': row.user_id,
            'company_id': row.company_id,
            'rejection_reason': row.rejection_reason,
        })
    return out


def list_registrations(db, BidderNetworkRegistration, *, status=None, limit=100) -> dict:
    q = BidderNetworkRegistration.query.order_by(BidderNetworkRegistration.id.desc())
    if status:
        q = q.filter_by(status=status)
    rows = q.limit(limit).all()
    return {'registrations': [registration_to_dict(r, include_internal=True) for r in rows]}


def _split_name(contact_name: str) -> tuple[str, str]:
    parts = (contact_name or '').strip().split(None, 1)
    if not parts:
        return 'Contact', 'User'
    if len(parts) == 1:
        return parts[0], 'User'
    return parts[0], parts[1]


def create_registration(
    db,
    models,
    *,
    body: dict,
    files,
    save_file_fn,
    upload_folder: str,
) -> dict:
    BidderNetworkRegistration = models['BidderNetworkRegistration']
    BidderNetworkDocument = models['BidderNetworkDocument']
    User = models['User']
    email = (body.get('email') or '').strip().lower()
    company_name = (body.get('company_name') or '').strip()
    contact_name = (body.get('contact_name') or '').strip()
    password = body.get('password') or ''
    if not email or '@' not in email:
        raise ValueError('Valid email is required')
    if not company_name or not contact_name:
        raise ValueError('Company name and contact name are required')
    if len(password) < 8:
        raise ValueError('Password must be at least 8 characters')

    existing = BidderNetworkRegistration.query.filter(
        BidderNetworkRegistration.email == email,
        BidderNetworkRegistration.status.in_(('pending', 'approved')),
    ).first()
    if existing:
        raise ValueError('An application with this email is already on file')

    if User.query.filter_by(email=email).first():
        raise ValueError('This email already has a user account — sign in instead')

    specialties = body.get('specialties')
    if isinstance(specialties, str):
        try:
            specialties = json.loads(specialties)
        except json.JSONDecodeError:
            specialties = [s.strip() for s in specialties.split(',') if s.strip()]
    if not isinstance(specialties, list):
        specialties = []

    row = BidderNetworkRegistration(
        company_name=company_name,
        contact_name=contact_name,
        email=email,
        phone=(body.get('phone') or '').strip() or None,
        password_hash=generate_password_hash(password),
        specialties_json=json.dumps(specialties),
        comments=(body.get('comments') or '').strip() or None,
        status='pending',
    )
    db.session.add(row)
    db.session.flush()

    os.makedirs(os.path.join(upload_folder, 'bidder_network'), exist_ok=True)
    for f in files or []:
        if not f or not f.filename:
            continue
        stored = save_file_fn(f, folder='bidder_network')
        if not stored:
            continue
        path = os.path.join(upload_folder, 'bidder_network', stored)
        size = os.path.getsize(path) if os.path.isfile(path) else 0
        db.session.add(BidderNetworkDocument(
            registration_id=row.id,
            original_filename=f.filename,
            stored_filename=stored,
            content_type=f.mimetype,
            size_bytes=size,
        ))

    return {'ok': True, 'registration': registration_to_dict(row), 'message': 'Application submitted. You will receive access after our team approves your registration.'}


def approve_registration(db, models, registration_id: int, *, reviewer_id: int | None) -> dict:
    BidderNetworkRegistration = models['BidderNetworkRegistration']
    Company = models['Company']
    User = models['User']

    row = BidderNetworkRegistration.query.get(int(registration_id))
    if not row:
        raise ValueError('Registration not found')
    if row.status != 'pending':
        raise ValueError(f'Registration is already {row.status}')

    company = Company.query.filter_by(name=row.company_name).first()
    if not company:
        company = Company(name=row.company_name, type='Subcontractor', email=row.email, phone=row.phone)
        db.session.add(company)
        db.session.flush()
    details = _json_load(company.details_json, {})
    if not isinstance(details, dict):
        details = {}
    details['prequal_status'] = 'approved'
    details['actively_bidding'] = True
    details['bidder_network_registration_id'] = row.id
    details['specialties'] = _json_load(row.specialties_json, [])
    company.details_json = json.dumps(details)
    if row.specialties_json:
        trades = _json_load(row.specialties_json, [])
        if trades:
            company.trade = trades[0][:80]

    from user_management_service import create_user

    first, last = _split_name(row.contact_name)
    user, _temp = create_user(
        db, User, Company,
        {
            'firstName': first,
            'lastName': last,
            'email': row.email,
            'phone': row.phone,
            'company': row.company_name,
            'company_id': company.id,
            'role': 'Subcontractor Contact',
            'accessEnabled': True,
            'status': 'Active',
            'temp_password': 'BidderNetwork1!',  # overwritten below
        },
        actor_id=reviewer_id,
    )
    user.password_hash = row.password_hash
    user.must_change_password = False
    user.access_enabled = True
    company.primary_contact_user_id = user.id

    row.status = 'approved'
    row.user_id = user.id
    row.company_id = company.id
    row.reviewed_by_id = reviewer_id
    row.reviewed_at = datetime.utcnow()

    return {
        'ok': True,
        'registration': registration_to_dict(row, include_internal=True),
        'user_id': user.id,
        'company_id': company.id,
    }


def reject_registration(db, BidderNetworkRegistration, registration_id: int, reason: str, *, reviewer_id: int | None) -> dict:
    row = BidderNetworkRegistration.query.get(int(registration_id))
    if not row:
        raise ValueError('Registration not found')
    if row.status != 'pending':
        raise ValueError(f'Registration is already {row.status}')
    row.status = 'rejected'
    row.rejection_reason = (reason or '').strip() or 'Not approved at this time'
    row.reviewed_by_id = reviewer_id
    row.reviewed_at = datetime.utcnow()
    return {'ok': True, 'registration': registration_to_dict(row, include_internal=True)}


def bidder_access_for_user(db, BidderNetworkRegistration, user) -> dict:
    if not user or not getattr(user, 'email', None):
        return {'approved': False, 'reason': 'not_logged_in'}
    email = user.email.strip().lower()
    reg = BidderNetworkRegistration.query.filter_by(email=email, status='approved').first()
    if reg:
        return {'approved': True, 'registration_id': reg.id, 'company_name': reg.company_name}
    pending = BidderNetworkRegistration.query.filter_by(email=email, status='pending').first()
    if pending:
        return {'approved': False, 'reason': 'pending_approval'}
    return {'approved': False, 'reason': 'not_registered'}


def list_network_opportunities(db, BidPackage, Project, Estimate) -> dict:
    rows = (
        BidPackage.query.filter(
            BidPackage.network_published.is_(True),
            BidPackage.status.in_(('Open', 'Sent', 'Bidding', 'Published')),
        )
        .order_by(BidPackage.due_date.asc(), BidPackage.id.desc())
        .limit(100)
        .all()
    )
    opportunities = []
    for pkg in rows:
        project = Project.query.get(pkg.project_id) if pkg.project_id else None
        opportunities.append({
            'id': pkg.id,
            'title': pkg.title or pkg.number or f'Package #{pkg.id}',
            'number': pkg.number,
            'spec_section': pkg.spec_section,
            'division': pkg.division,
            'summary': (pkg.network_summary or pkg.description or pkg.scope_notes or '')[:2000],
            'due_date': pkg.due_date.isoformat() if pkg.due_date else None,
            'status': pkg.status,
            'project_name': project.name if project else None,
            'project_location': getattr(project, 'location', None) if project else None,
            'portal_url': f'/estimate-portal?project_id={pkg.project_id}&package_id={pkg.id}',
        })
    return {'opportunities': opportunities}


def set_package_network_publish(db, BidPackage, package_id: int, *, published: bool, summary: str | None = None) -> dict:
    pkg = BidPackage.query.get(int(package_id))
    if not pkg:
        raise ValueError('Bid package not found')
    pkg.network_published = bool(published)
    if summary is not None:
        pkg.network_summary = summary.strip() or None
    return {
        'id': pkg.id,
        'network_published': bool(pkg.network_published),
        'network_summary': pkg.network_summary,
    }
