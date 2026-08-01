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

MANIFEST_DOCUMENT_CATEGORIES = (
    ('plans', 'Plans & drawings'),
    ('specifications', 'Specifications'),
    ('geotechnical', 'Geotechnical & environmental'),
    ('schedules', 'Schedules & equipment lists'),
    ('bid_forms', 'Bid forms & exhibits'),
    ('insurance', 'Insurance, bonds & certifications'),
    ('general', 'General conditions & ITB'),
)

MANIFEST_DOC_KEYS = tuple(k for k, _ in MANIFEST_DOCUMENT_CATEGORIES)


def _default_meeting_block():
    return {
        'date': '',
        'time': '',
        'location': '',
        'mandatory': False,
        'virtual_url': '',
        'notes': '',
    }


def _default_bonding_block():
    return {
        'bid_bond_percent': '',
        'performance_bond': '',
        'payment_bond': '',
        'notes': '',
    }


def default_package_manifest() -> dict:
    return {
        'itb': {
            'scope_summary_html': '',
            'instructions_html': '',
            'bid_due_time': '',
            'timezone': 'America/Denver',
            'pre_bid_meeting': _default_meeting_block(),
            'job_walk': _default_meeting_block(),
            'bonding': _default_bonding_block(),
            'qualifications_html': '',
            'wage_requirements': '',
            'subs_to_include': '',
            'subs_to_exclude': '',
        },
        'documents': {key: [] for key in MANIFEST_DOC_KEYS},
    }


def parse_package_manifest(pkg) -> dict:
    base = default_package_manifest()
    raw = _json_load(getattr(pkg, 'network_manifest_json', None), None)
    if not isinstance(raw, dict):
        return base
    itb = raw.get('itb') if isinstance(raw.get('itb'), dict) else {}
    for key in base['itb']:
        if key in ('pre_bid_meeting', 'job_walk'):
            block = itb.get(key) if isinstance(itb.get(key), dict) else {}
            base['itb'][key].update({k: block.get(k, base['itb'][key].get(k)) for k in base['itb'][key]})
        elif key == 'bonding':
            block = itb.get('bonding') if isinstance(itb.get('bonding'), dict) else {}
            base['itb']['bonding'].update({k: block.get(k, base['itb']['bonding'].get(k)) for k in base['itb']['bonding']})
        elif key in itb:
            base['itb'][key] = itb[key]
    docs = raw.get('documents') if isinstance(raw.get('documents'), dict) else {}
    for key in MANIFEST_DOC_KEYS:
        entries = docs.get(key)
        if isinstance(entries, list):
            base['documents'][key] = [e for e in entries if isinstance(e, dict)]
    return base


def save_package_manifest(pkg, manifest: dict) -> dict:
    if not isinstance(manifest, dict):
        manifest = default_package_manifest()
    cleaned = default_package_manifest()
    itb_in = manifest.get('itb') if isinstance(manifest.get('itb'), dict) else {}
    for key in cleaned['itb']:
        if key in ('pre_bid_meeting', 'job_walk', 'bonding'):
            block = itb_in.get(key) if isinstance(itb_in.get(key), dict) else {}
            cleaned['itb'][key].update({k: block.get(k, cleaned['itb'][key].get(k)) for k in cleaned['itb'][key]})
        elif key in itb_in:
            cleaned['itb'][key] = itb_in[key]
    docs_in = manifest.get('documents') if isinstance(manifest.get('documents'), dict) else {}
    for key in MANIFEST_DOC_KEYS:
        entries = docs_in.get(key) if isinstance(docs_in.get(key), list) else []
        norm = []
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            did = entry.get('document_id')
            try:
                did = int(did)
            except (TypeError, ValueError):
                continue
            norm.append({
                'document_id': did,
                'title': (entry.get('title') or '').strip(),
                'sort_order': int(entry.get('sort_order', i)),
                'sheet': (entry.get('sheet') or '').strip(),
            })
        norm.sort(key=lambda x: x.get('sort_order', 0))
        cleaned['documents'][key] = norm
    pkg.network_manifest_json = json.dumps(cleaned)
    return cleaned


def manifest_document_ids(manifest: dict) -> set:
    ids = set()
    if not isinstance(manifest, dict):
        return ids
    docs = manifest.get('documents') if isinstance(manifest.get('documents'), dict) else {}
    for key in MANIFEST_DOC_KEYS:
        for entry in docs.get(key) or []:
            if isinstance(entry, dict) and entry.get('document_id'):
                try:
                    ids.add(int(entry['document_id']))
                except (TypeError, ValueError):
                    pass
    return ids


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
        'bid_due_time': block.get('bid_due_time') or '',
        'timezone': block.get('timezone') or 'America/Denver',
        'pre_bid_date': block.get('pre_bid_date'),
        'pre_bid_meeting': block.get('pre_bid_meeting') if isinstance(block.get('pre_bid_meeting'), dict) else _default_meeting_block(),
        'job_walk': block.get('job_walk') if isinstance(block.get('job_walk'), dict) else _default_meeting_block(),
        'bonding': block.get('bonding') if isinstance(block.get('bonding'), dict) else _default_bonding_block(),
        'instructions_html': block.get('instructions_html') or '',
        'owner_name': block.get('owner_name') or '',
        'architect_name': block.get('architect_name') or '',
        'engineer_name': block.get('engineer_name') or '',
        'project_address': block.get('project_address') or '',
        'contact_name': block.get('contact_name') or '',
        'contact_email': block.get('contact_email') or '',
        'contact_phone': block.get('contact_phone') or '',
        'document_ids': [int(x) for x in (block.get('document_ids') or []) if str(x).isdigit()],
    }


def save_plan_room_meta(project, patch: dict) -> dict:
    details = project.get_details() if hasattr(project, 'get_details') else {}
    if not isinstance(details, dict):
        details = {}
    block = details.get('plan_room') if isinstance(details.get('plan_room'), dict) else {}
    scalar_keys = (
        'published', 'summary', 'bid_date', 'bid_due_time', 'timezone', 'pre_bid_date',
        'contact_name', 'contact_email', 'contact_phone', 'document_ids',
        'instructions_html', 'owner_name', 'architect_name', 'engineer_name', 'project_address',
    )
    dict_keys = ('pre_bid_meeting', 'job_walk', 'bonding')
    for key in scalar_keys:
        if key in patch:
            block[key] = patch[key]
    for key in dict_keys:
        if key in patch and isinstance(patch[key], dict):
            cur = block.get(key) if isinstance(block.get(key), dict) else {}
            cur.update(patch[key])
            block[key] = cur
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
        doc_ids |= manifest_document_ids(parse_package_manifest(pkg))
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


def _documents_by_id(db, Document, project_id: int, doc_ids: set) -> dict:
    if not doc_ids:
        return {}
    rows = Document.query.filter(
        Document.id.in_(list(doc_ids)),
        Document.project_id == int(project_id),
        Document.deleted_at.is_(None),
    ).all()
    return {d.id: _document_dict(d) for d in rows}


def manifest_document_sections(manifest: dict, doc_by_id: dict) -> list:
    sections = []
    docs = manifest.get('documents') if isinstance(manifest.get('documents'), dict) else {}
    for key, label in MANIFEST_DOCUMENT_CATEGORIES:
        entries = docs.get(key) or []
        items = []
        for entry in sorted(entries, key=lambda e: e.get('sort_order', 0)):
            if not isinstance(entry, dict):
                continue
            did = entry.get('document_id')
            base = doc_by_id.get(did)
            if not base:
                continue
            items.append({
                **base,
                'title': (entry.get('title') or base.get('name')),
                'sheet': entry.get('sheet') or '',
            })
        if items:
            sections.append({'key': key, 'label': label, 'documents': items})
    return sections


def _package_public_dict(project, pkg, *, include_manifest: bool = False) -> dict:
    manifest = parse_package_manifest(pkg)
    payload = {
        'id': pkg.id,
        'number': pkg.number,
        'title': pkg.title,
        'spec_section': pkg.spec_section,
        'division': pkg.division,
        'due_date': pkg.due_date.isoformat() if pkg.due_date else None,
        'summary': (pkg.network_summary or pkg.description or pkg.scope_notes or '')[:3000],
        'drawing_refs': _json_load(pkg.drawing_refs_json, []),
        'spec_refs': _json_load(pkg.spec_refs_json, []),
        'network_published': bool(pkg.network_published),
        'detail_url': f'/plan-room/projects/{project.id}/packages/{pkg.id}',
        'portal_url': f'/estimate-portal?project_id={project.id}&package_id={pkg.id}',
    }
    if include_manifest:
        payload['manifest'] = manifest
        payload['itb'] = manifest.get('itb') or {}
    return payload


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


def plan_room_project_detail(db, models, project_id: int, *, staff_access: bool = False) -> dict:
    Project = models['Project']
    BidPackage = models['BidPackage']
    Document = models['Document']
    BidPackageAddendum = models['BidPackageAddendum']

    project = Project.query.get(int(project_id))
    if not project:
        raise ValueError('Project not found')
    packages = _published_packages_for_project(BidPackage, project.id)
    if staff_access and not packages:
        packages = BidPackage.query.filter_by(project_id=project.id).order_by(
            BidPackage.due_date.asc(), BidPackage.id,
        ).all()
    if not staff_access and not project_in_plan_room(project, packages):
        raise ValueError('Project is not published to the plan room')

    meta = plan_room_meta(project)
    documents = gather_plan_documents(db, Document, BidPackageAddendum, project, packages)
    doc_by_id = {d['id']: d for d in documents}
    document_sections = []
    seen_section_keys = set()
    for pkg in packages:
        for sec in manifest_document_sections(parse_package_manifest(pkg), doc_by_id):
            if sec['key'] not in seen_section_keys:
                document_sections.append(sec)
                seen_section_keys.add(sec['key'])
            else:
                for existing in document_sections:
                    if existing['key'] == sec['key']:
                        existing_ids = {d['id'] for d in existing['documents']}
                        for doc in sec['documents']:
                            if doc['id'] not in existing_ids:
                                existing['documents'].append(doc)
                        break
    addenda = []
    for pkg in packages:
        for add in BidPackageAddendum.query.filter_by(bid_package_id=pkg.id).order_by(BidPackageAddendum.created_at).all():
            add_docs = []
            for did in _json_load(add.document_ids_json, []):
                try:
                    did = int(did)
                except (TypeError, ValueError):
                    continue
                if did in doc_by_id:
                    add_docs.append(doc_by_id[did])
            addenda.append({
                'id': add.id,
                'package_id': pkg.id,
                'package_title': pkg.title or pkg.number,
                'number': add.number,
                'title': add.title,
                'description': add.description,
                'require_rebid': bool(add.require_rebid),
                'documents': add_docs,
            })

    pkg_payload = [_package_public_dict(project, p) for p in packages]

    return {
        'project': _project_card(project, packages),
        'plan_room': meta,
        'packages': pkg_payload,
        'documents': documents,
        'document_sections': document_sections,
        'addenda': addenda,
        'manifest_categories': [{'key': k, 'label': v} for k, v in MANIFEST_DOCUMENT_CATEGORIES],
    }


def plan_room_package_detail(db, models, project_id: int, package_id: int, *, staff_access: bool = False) -> dict:
    Project = models['Project']
    BidPackage = models['BidPackage']
    Document = models['Document']
    BidPackageAddendum = models['BidPackageAddendum']

    project = Project.query.get(int(project_id))
    if not project:
        raise ValueError('Project not found')
    pkg = BidPackage.query.get(int(package_id))
    if not pkg or int(pkg.project_id) != int(project.id):
        raise ValueError('Bid package not found')
    if not staff_access and not pkg.network_published:
        raise ValueError('Package is not published to the plan room')

    packages = _published_packages_for_project(BidPackage, project.id)
    if staff_access and not packages:
        packages = [pkg]
    if not staff_access and not project_in_plan_room(project, packages):
        raise ValueError('Project is not published to the plan room')

    meta = plan_room_meta(project)
    manifest = parse_package_manifest(pkg)
    doc_ids = manifest_document_ids(manifest)
    for did in _json_load(pkg.attachments_json, []):
        try:
            doc_ids.add(int(did))
        except (TypeError, ValueError):
            pass
    doc_by_id = _documents_by_id(db, Document, project.id, doc_ids)
    sections = manifest_document_sections(manifest, doc_by_id)
    legacy = []
    for did in _json_load(pkg.attachments_json, []):
        try:
            did = int(did)
        except (TypeError, ValueError):
            continue
        if did in doc_by_id and not any(d['id'] == did for s in sections for d in s['documents']):
            legacy.append(doc_by_id[did])
    if legacy:
        sections.insert(0, {'key': 'legacy', 'label': 'Package attachments', 'documents': legacy})

    addenda = []
    for add in BidPackageAddendum.query.filter_by(bid_package_id=pkg.id).order_by(BidPackageAddendum.created_at).all():
        add_docs = []
        for did in _json_load(add.document_ids_json, []):
            try:
                did = int(did)
            except (TypeError, ValueError):
                continue
            row = Document.query.get(did)
            if row and row.project_id == project.id and not row.deleted_at:
                add_docs.append(_document_dict(row))
        addenda.append({
            'id': add.id,
            'number': add.number,
            'title': add.title,
            'description': add.description,
            'require_rebid': bool(add.require_rebid),
            'documents': add_docs,
        })

    return {
        'project': _project_card(project, packages),
        'plan_room': meta,
        'package': _package_public_dict(project, pkg, include_manifest=True),
        'document_sections': sections,
        'addenda': addenda,
        'manifest_categories': [{'key': k, 'label': v} for k, v in MANIFEST_DOCUMENT_CATEGORIES],
    }


def list_project_documents_for_console(db, Document, project_id: int, *, limit=500) -> list:
    rows = Document.query.filter_by(project_id=int(project_id)).filter(
        Document.deleted_at.is_(None),
    ).order_by(Document.name).limit(limit).all()
    return [{
        'id': d.id,
        'name': d.name,
        'filename': d.original_filename or d.filename,
        'document_type': d.document_type,
        'file_size': d.file_size or 0,
    } for d in rows]


def admin_plan_room_console(db, models, project_id: int) -> dict:
    Project = models['Project']
    BidPackage = models['BidPackage']
    Document = models['Document']
    BidPackageAddendum = models['BidPackageAddendum']

    project = Project.query.get(int(project_id))
    if not project:
        raise ValueError('Project not found')
    packages = BidPackage.query.filter_by(project_id=project.id).order_by(
        BidPackage.due_date.asc(), BidPackage.id,
    ).all()
    meta = plan_room_meta(project)
    pkg_rows = []
    for pkg in packages:
        manifest = parse_package_manifest(pkg)
        addenda_count = BidPackageAddendum.query.filter_by(bid_package_id=pkg.id).count()
        pkg_rows.append({
            **_package_public_dict(project, pkg, include_manifest=True),
            'status': pkg.status,
            'addenda_count': addenda_count,
            'manifest_document_count': len(manifest_document_ids(manifest)),
        })
    return {
        'project': {
            'id': project.id,
            'number': project.number,
            'name': project.name,
            'location': _project_location(project),
        },
        'plan_room': meta,
        'packages': pkg_rows,
        'project_documents': list_project_documents_for_console(db, Document, project.id),
        'manifest_categories': [{'key': k, 'label': v} for k, v in MANIFEST_DOCUMENT_CATEGORIES],
    }


def update_bid_package_manifest(db, BidPackage, package_id: int, body: dict) -> dict:
    pkg = BidPackage.query.get(int(package_id))
    if not pkg:
        raise ValueError('Bid package not found')
    manifest = body.get('manifest') if isinstance(body.get('manifest'), dict) else body
    saved = save_package_manifest(pkg, manifest)
    if 'network_summary' in body:
        pkg.network_summary = (body.get('network_summary') or '').strip() or None
    if 'network_published' in body:
        pkg.network_published = bool(body['network_published'])
    return {
        'id': pkg.id,
        'network_published': bool(pkg.network_published),
        'network_summary': pkg.network_summary,
        'manifest': saved,
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
    scalar_keys = (
        'summary', 'bid_date', 'bid_due_time', 'timezone', 'pre_bid_date',
        'contact_name', 'contact_email', 'contact_phone', 'document_ids',
        'instructions_html', 'owner_name', 'architect_name', 'engineer_name', 'project_address',
    )
    for key in scalar_keys:
        if key in body:
            patch[key] = body[key]
    for key in ('pre_bid_meeting', 'job_walk', 'bonding'):
        if key in body and isinstance(body[key], dict):
            patch[key] = body[key]
    if 'plan_room' in body and isinstance(body['plan_room'], dict):
        pr = body['plan_room']
        for key in scalar_keys:
            if key in pr:
                patch[key] = pr[key]
        for key in ('pre_bid_meeting', 'job_walk', 'bonding'):
            if key in pr and isinstance(pr[key], dict):
                patch[key] = pr[key]
        if 'published' in pr:
            patch['published'] = bool(pr['published'])
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


def set_package_network_publish(db, BidPackage, package_id: int, *, published: bool, summary: str | None = None, manifest: dict | None = None) -> dict:
    pkg = BidPackage.query.get(int(package_id))
    if not pkg:
        raise ValueError('Bid package not found')
    pkg.network_published = bool(published)
    if summary is not None:
        pkg.network_summary = summary.strip() or None
    saved_manifest = parse_package_manifest(pkg)
    if manifest is not None:
        saved_manifest = save_package_manifest(pkg, manifest)
    return {
        'id': pkg.id,
        'network_published': bool(pkg.network_published),
        'network_summary': pkg.network_summary,
        'manifest': saved_manifest,
    }
