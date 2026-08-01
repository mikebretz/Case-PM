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
        'tagline': 'Electronic plan room & bid opportunities',
        'hero_body': (
            'Browse active projects, download plans and specifications, and submit bids online. '
            'Register once — our preconstruction team approves your firm before plan access is enabled.'
        ),
        'primary_color': '#2563eb',
        'logo_data_url': company.get('logo_data_url') or '',
        'contact_email': company.get('company_phone') or '',
        'public_path': '/plan-room',
    }


def plan_room_meta(project) -> dict:
    if not project:
        return {}
    pr = (project.get_details() if hasattr(project, 'get_details') else {}) or {}
    if not isinstance(pr, dict):
        pr = {}
    block = pr.get('plan_room') if isinstance(pr.get('plan_room'), dict) else {}
    return {
        'published': bool(block.get('published')),
        'summary': (block.get('summary') or '').strip(),
        'bid_date': block.get('bid_date'),
        'pre_bid_date': block.get('pre_bid_date'),
        'contact_name': block.get('contact_name') or '',
        'contact_email': block.get('contact_email') or '',
        'document_ids': [int(x) for x in (block.get('document_ids') or []) if str(x).isdigit()],
    }


def save_plan_room_meta(project, patch: dict) -> dict:
    details = project.get_details() if hasattr(project, 'get_details') else {}
    if not isinstance(details, dict):
        details = {}
    block = details.get('plan_room') if isinstance(details.get('plan_room'), dict) else {}
    for key in ('published', 'summary', 'bid_date', 'pre_bid_date', 'contact_name', 'contact_email', 'document_ids'):
        if key in patch:
            block[key] = patch[key]
    details['plan_room'] = block
    project.set_details(details)
    return block


def _project_location(project) -> str:
    if not project:
        return ''
    if hasattr(project, 'location_label'):
        return project.location_label() or ''
    parts = [getattr(project, 'city', None), getattr(project, 'state', None)]
    return ', '.join(p for p in parts if p)


def _document_dict(doc) -> dict:
    return {
        'id': doc.id,
        'name': doc.name,
        'filename': doc.original_filename or doc.filename,
        'mime_type': doc.mime_type or 'application/octet-stream',
        'file_size': doc.file_size or 0,
        'document_type': doc.document_type,
        'download_url': f'/api/bidder-network/plan-documents/{doc.id}/download',
    }



def gather_plan_documents(db, Document, BidPackageAddendum, project, packages: list) -> list:
    doc_ids = set(plan_room_meta(project).get('document_ids') or [])
    for pkg in packages:
        for did in _json_load(getattr(pkg, 'attachments_json', None), []):
            try:
                doc_ids.add(int(did))
            except (TypeError, ValueError):
                pass
        for add in BidPackageAddendum.query.filter_by(bid_package_id=pkg.id).all():
            for did in _json_load(add.document_ids_json, []):
                try:
                    doc_ids.add(int(did))
                except (TypeError, ValueError):
                    pass
    if not doc_ids:
        return []
    rows = Document.query.filter(
        Document.id.in_(list(doc_ids)),
        Document.project_id == project.id,
        Document.deleted_at.is_(None),
    ).order_by(Document.name).all()
    return [_document_dict(d) for d in rows]


def _published_packages_for_project(BidPackage, project_id: int) -> list:
    return BidPackage.query.filter(
        BidPackage.project_id == int(project_id),
        BidPackage.network_published.is_(True),
        BidPackage.status.in_(('Open', 'Sent', 'Bidding', 'Published', 'Draft')),
    ).order_by(BidPackage.due_date.asc(), BidPackage.id).all()


def project_in_plan_room(project, packages: list | None = None) -> bool:
    if plan_room_meta(project).get('published'):
        return True
    if packages is None:
        return False
    return len(packages) > 0


def _project_card(project, packages: list, *, public_teaser: bool = False) -> dict:
    meta = plan_room_meta(project)
    due_dates = [p.due_date for p in packages if p.due_date]
    bid_date = meta.get('bid_date')
    if not bid_date and due_dates:
        bid_date = min(due_dates).isoformat()
    divisions = sorted({(p.division or p.spec_section or '')[:20] for p in packages if (p.division or p.spec_section)})
    card = {
        'id': project.id,
        'number': project.number or '',
        'name': project.name,
        'location': _project_location(project),
        'project_type': getattr(project, 'project_type', None) or '',
        'status': 'Bidding',
        'bid_date': bid_date,
        'pre_bid_date': meta.get('pre_bid_date'),
        'summary': (meta.get('summary') or project.description or '')[:500],
        'package_count': len(packages),
        'divisions': [d for d in divisions if d],
        'detail_url': f'/plan-room/projects/{project.id}',
    }
    if public_teaser:
        card.pop('detail_url', None)
        card['summary'] = (card['summary'] or '')[:160]
    return card


def list_plan_room_projects(db, BidPackage, Project, *, public_teaser: bool = False) -> dict:
    pkg_rows = BidPackage.query.filter(BidPackage.network_published.is_(True)).all()
    by_project: dict[int, list] = {}
    for pkg in pkg_rows:
        by_project.setdefault(int(pkg.project_id), []).append(pkg)

    projects_out = []
    seen = set(by_project.keys())

    for pid in seen:
        project = Project.query.get(pid)
        if not project:
            continue
        packages = by_project.get(pid) or []
        if not project_in_plan_room(project, packages):
            continue
        projects_out.append(_project_card(project, packages, public_teaser=public_teaser))

    # Projects flagged published without packages yet
    for project in Project.query.filter(Project.status != 'Archived').limit(500).all():
        if project.id in seen:
            continue
        meta = plan_room_meta(project)
        if not meta.get('published'):
            continue
        projects_out.append(_project_card(project, [], public_teaser=public_teaser))

    projects_out.sort(key=lambda x: (x.get('bid_date') or '9999', x.get('name') or ''))
    return {'projects': projects_out}


def plan_room_project_detail(db, models, project_id: int) -> dict:
    Project = models['Project']
    BidPackage = models['BidPackage']
    Document = models['Document']
    BidPackageAddendum = models['BidPackageAddendum']

    project = Project.query.get(int(project_id))
    if not project:
        raise ValueError('Project not found')
    packages = _published_packages_for_project(BidPackage, project.id)
    if not project_in_plan_room(project, packages):
        raise ValueError('Project is not published to the plan room')

    meta = plan_room_meta(project)
    documents = gather_plan_documents(db, Document, BidPackageAddendum, project, packages)
    addenda = []
    for pkg in packages:
        for add in BidPackageAddendum.query.filter_by(bid_package_id=pkg.id).order_by(BidPackageAddendum.created_at).all():
            addenda.append({
                'id': add.id,
                'package_id': pkg.id,
                'package_title': pkg.title or pkg.number,
                'number': add.number,
                'title': add.title,
                'description': add.description,
                'require_rebid': bool(add.require_rebid),
            })

    pkg_payload = []
    for p in packages:
        pkg_payload.append({
            'id': p.id,
            'number': p.number,
            'title': p.title,
            'spec_section': p.spec_section,
            'division': p.division,
            'due_date': p.due_date.isoformat() if p.due_date else None,
            'summary': (p.network_summary or p.description or p.scope_notes or '')[:3000],
            'drawing_refs': _json_load(p.drawing_refs_json, []),
            'spec_refs': _json_load(p.spec_refs_json, []),
            'portal_url': f'/estimate-portal?project_id={project.id}&package_id={p.id}',
        })

    return {
        'project': _project_card(project, packages),
        'plan_room': meta,
        'packages': pkg_payload,
        'documents': documents,
        'addenda': addenda,
    }


def user_may_access_plan_document(db, models, user, doc_id: int) -> bool:
    Document = models['Document']
    BidPackage = models['BidPackage']
    Project = models['Project']
    BidPackageAddendum = models['BidPackageAddendum']
    BidderNetworkRegistration = models['BidderNetworkRegistration']

    doc = Document.query.get(int(doc_id))
    if not doc or doc.deleted_at:
        return False
    packages = _published_packages_for_project(BidPackage, doc.project_id)
    project = Project.query.get(doc.project_id)
    if not project or not project_in_plan_room(project, packages):
        return False
    allowed_ids = {d['id'] for d in gather_plan_documents(db, Document, BidPackageAddendum, project, packages)}
    if doc.id not in allowed_ids:
        return False
    access = bidder_access_for_user(db, BidderNetworkRegistration, user)
    return bool(access.get('approved'))


def set_project_plan_room(db, Project, BidPackage, project_id: int, body: dict) -> dict:
    project = Project.query.get(int(project_id))
    if not project:
        raise ValueError('Project not found')
    patch = {}
    if 'published' in body:
        patch['published'] = bool(body['published'])
    for key in ('summary', 'bid_date', 'pre_bid_date', 'contact_name', 'contact_email'):
        if key in body:
            patch[key] = body[key]
    if 'document_ids' in body:
        patch['document_ids'] = body['document_ids']
    meta = save_plan_room_meta(project, patch)
    if body.get('publish_all_packages'):
        for pkg in BidPackage.query.filter_by(project_id=project.id).all():
            if (pkg.status or '').lower() in ('draft', 'open', 'sent', 'bidding', 'published', ''):
                pkg.network_published = bool(body.get('published', True))
    return {'ok': True, 'project_id': project.id, 'plan_room': meta}

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
