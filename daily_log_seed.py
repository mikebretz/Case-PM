"""Seed sample daily field reports for weekly log compile testing."""
from __future__ import annotations

import json
from datetime import date, timedelta

from daily_log_persistence import build_details, sync_equipment, sync_manpower


def _weekday_logs(base: date):
    """Mon–Fri of the week containing base (or prior week if base is weekend)."""
    d = base
    while d.weekday() > 4:
        d -= timedelta(days=1)
    monday = d - timedelta(days=d.weekday())
    return [monday + timedelta(days=i) for i in range(5)]


SAMPLE_LOGS = [
    {
        'weather': 'Partly cloudy, 88°F',
        'work_performed': (
            'Continued slab-on-grade formwork at grid B2–B5. '
            'Under-slab plumbing rough-in inspected and signed off by city inspector. '
            'Mobilized tower crane for steel delivery tomorrow.'
        ),
        'notes': 'Owner rep walked site at 2 PM — no issues noted.',
        'manpower': [
            {'company': 'Case Concrete', 'personnel_count': 12, 'hours': 96, 'work_performed': 'Formwork'},
            {'company': 'ABC Plumbing', 'personnel_count': 6, 'hours': 48, 'work_performed': 'Under-slab'},
            {'company': 'Case Supervision', 'personnel_count': 2, 'hours': 16, 'work_performed': 'PM/Super'},
        ],
        'equipment': [
            {'equipment_name': 'Skid Steer', 'quantity': 1, 'condition': 'Good'},
            {'equipment_name': 'Concrete Pump (standby)', 'quantity': 1, 'condition': 'Good'},
        ],
        'deliveries': [{'item': 'Rebar #5 bundles', 'supplier': 'Steel Supply Co', 'quantity': '4,200 lf', 'notes': 'Staged at laydown'}],
        'scheduled_work': [
            {'activity': 'SOG Form & Pour — Area B', 'status': 'On Track', 'notes': 'Pour scheduled Thu'},
            {'activity': 'Structural Steel — Level 1', 'status': 'Not Started', 'notes': 'Awaiting delivery'},
        ],
        'safety': [{'type': 'Toolbox Talk', 'description': 'Heat illness prevention', 'action': '15-min crew briefing at 7 AM'}],
    },
    {
        'weather': 'Clear, 91°F — heat advisory',
        'work_performed': (
            'Set structural steel columns at grid lines 1–4. '
            'Completed anchor bolt template verification. '
            'Backfilled utility trench along north property line.'
        ),
        'notes': 'Steel erector requested revised lift plan for bay 3 — sent to safety for review.',
        'manpower': [
            {'company': 'Iron Works Erectors', 'personnel_count': 8, 'hours': 64, 'work_performed': 'Steel erection'},
            {'company': 'Case Concrete', 'personnel_count': 10, 'hours': 80, 'work_performed': 'Formwork/finish'},
            {'company': 'Site Utilities Inc', 'personnel_count': 4, 'hours': 32, 'work_performed': 'Trench backfill'},
        ],
        'equipment': [
            {'equipment_name': '80-ton Mobile Crane', 'quantity': 1, 'condition': 'Good'},
            {'equipment_name': 'Forklift 6k', 'quantity': 2, 'condition': 'Good'},
        ],
        'deliveries': [{'item': 'W12x26 steel columns', 'supplier': 'Gulf Steel', 'quantity': '18 pcs', 'notes': 'Received AM'}],
        'delays': [{'type': 'Weather', 'description': '30-min lightning stand-down', 'hours_lost': 0.5}],
        'scheduled_work': [
            {'activity': 'Structural Steel — Level 1', 'status': 'On Track', 'notes': '6 of 18 columns set'},
            {'activity': 'Underground Utilities', 'status': 'Ahead', 'notes': 'North trench closed'},
        ],
        'inspections': [{'type': 'Anchor Bolts', 'agency': 'Case QA', 'inspector': 'T. Bradley', 'result': 'Pass', 'notes': 'Template within tolerance'}],
    },
    {
        'weather': 'Scattered thunderstorms PM',
        'work_performed': (
            'Morning: completed SOG form oil and vapor barrier in Area B. '
            'Afternoon rain shut down exterior work at 1:30 PM. '
            'Interior block walls started at restrooms — grid A.'
        ),
        'notes': 'Documented weather delay in daily log; will track on next pay app if continued.',
        'manpower': [
            {'company': 'Case Concrete', 'personnel_count': 14, 'hours': 84, 'work_performed': 'SOG prep'},
            {'company': 'Masonry Sub', 'personnel_count': 6, 'hours': 36, 'work_performed': 'CMU walls'},
        ],
        'equipment': [{'equipment_name': 'Concrete Pump', 'quantity': 1, 'condition': 'Good'}],
        'delays': [{'type': 'Weather', 'description': 'Thunderstorms — exterior crane ops stopped', 'hours_lost': 3}],
        'scheduled_work': [
            {'activity': 'SOG Form & Pour — Area B', 'status': 'Behind', 'notes': 'Pour moved to Fri'},
            {'activity': 'CMU — Restrooms', 'status': 'On Track', 'notes': 'First lift to 8\'-0"'},
        ],
        'safety': [{'type': 'Observation', 'description': 'Crew cleared scaffold during lightning', 'action': 'Verified grounding protocol'}],
    },
    {
        'weather': 'Overcast, 84°F',
        'work_performed': (
            'Poured 4,200 SF SOG Area B — 5" slab with fiber mesh. '
            'Started curing compound application. '
            'Continued steel beam installation at elevation 14\'-0".'
        ),
        'notes': 'Concrete break tests sampled — set #447-B.',
        'manpower': [
            {'company': 'Case Concrete', 'personnel_count': 18, 'hours': 144, 'work_performed': 'SOG pour/finish'},
            {'company': 'Iron Works Erectors', 'personnel_count': 10, 'hours': 80, 'work_performed': 'Beams'},
        ],
        'equipment': [
            {'equipment_name': 'Concrete Pump', 'quantity': 1, 'condition': 'Good'},
            {'equipment_name': 'Laser Screed', 'quantity': 1, 'condition': 'Good'},
        ],
        'quantities': [{'description': 'SOG placed', 'quantity': '4200', 'unit': 'SF', 'cost_code': '03-300'}],
        'scheduled_work': [
            {'activity': 'SOG Form & Pour — Area B', 'status': 'Complete', 'notes': 'Poured — 7-day cure'},
            {'activity': 'Structural Steel — Level 1', 'status': 'On Track', 'notes': 'Beams 40% set'},
        ],
    },
    {
        'weather': 'Sunny, 86°F',
        'work_performed': (
            'Stripped SOG edge forms Area B; saw-cut control joints. '
            'Set remaining steel beams and initiated decking layout. '
            'Rough-in electrical underground to pad C completed.'
        ),
        'notes': 'Weekly coordination meeting held — lookahead updated for weeks 3–4.',
        'manpower': [
            {'company': 'Case Concrete', 'personnel_count': 8, 'hours': 64, 'work_performed': 'Strip/cure'},
            {'company': 'Iron Works Erectors', 'personnel_count': 10, 'hours': 80, 'work_performed': 'Steel/deck prep'},
            {'company': 'Spark Electric', 'personnel_count': 4, 'hours': 32, 'work_performed': 'Underground'},
        ],
        'equipment': [{'equipment_name': '80-ton Mobile Crane', 'quantity': 1, 'condition': 'Good'}],
        'visitors': [{'name': 'Sarah Chen', 'company': 'Owner', 'purpose': 'Weekly walk', 'time': '10:00 AM'}],
        'scheduled_work': [
            {'activity': 'Metal Deck — Level 1', 'status': 'Not Started', 'notes': 'Material on site Mon'},
            {'activity': 'Electrical Underground', 'status': 'Complete', 'notes': 'Pad C energized next week'},
        ],
        'phone_calls': [{'contact': 'Architect', 'company': 'Design Partners', 'subject': 'RFI #142 follow-up', 'notes': 'Response expected Monday'}],
    },
]


def seed_demo_daily_logs(db, Project, DailyLog, ManpowerEntry, EquipmentEntry, User, *, project_id=None, user_id=None, reference_date=None):
    """Insert Mon–Fri sample daily logs if none exist for that project/week."""
    project = Project.query.get(project_id) if project_id else Project.query.filter_by(status='Active').first()
    if not project:
        project = Project(
            number='DEMO-001',
            name='Lakeland Store #447',
            client='ALDI',
            address='4520 US Hwy 98',
            city='Lakeland',
            state='FL',
            zip_code='33809',
            status='Active',
            percent_complete=18,
            project_manager='Admin User',
            contract_value=4250000.0,
        )
        db.session.add(project)
        db.session.flush()

    user = User.query.get(user_id) if user_id else User.query.filter_by(role='Admin').first()
    if not user:
        return {'ok': False, 'error': 'No user found'}

    ref = reference_date or date.today()
    days = _weekday_logs(ref)
    created = 0
    skipped = 0

    for log_date, payload in zip(days, SAMPLE_LOGS):
        exists = DailyLog.query.filter_by(project_id=project.id, date=log_date).first()
        if exists:
            skipped += 1
            continue
        manpower = payload.get('manpower', [])
        equipment = payload.get('equipment', [])
        details = build_details(payload)
        log = DailyLog(
            project_id=project.id,
            user_id=user.id,
            date=log_date,
            weather=payload.get('weather'),
            work_performed=payload.get('work_performed'),
            notes=payload.get('notes'),
            status='Submitted',
            details_json=json.dumps(details),
        )
        db.session.add(log)
        db.session.flush()
        sync_manpower(db, ManpowerEntry, log.id, manpower)
        sync_equipment(db, EquipmentEntry, log.id, equipment)
        created += 1

    db.session.commit()
    return {
        'ok': True,
        'project_id': project.id,
        'project_name': project.name,
        'created': created,
        'skipped': skipped,
        'dates': [d.isoformat() for d in days],
    }


if __name__ == '__main__':
    from app import app, db, Project, DailyLog, ManpowerEntry, EquipmentEntry, User

    with app.app_context():
        result = seed_demo_daily_logs(db, Project, DailyLog, ManpowerEntry, EquipmentEntry, User)
        print(result)
