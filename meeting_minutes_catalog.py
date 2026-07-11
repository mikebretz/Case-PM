"""
Meeting minutes catalog — types, statuses, agenda templates.

Patterns from common construction meeting workflows,
e-Builder, Viewpoint, Smartsheet, Monday.com, and Microsoft Project.
"""

MEETING_TYPES = [
    {'key': 'oac', 'label': 'OAC (Owner-Architect-Contractor)', 'icon': 'fa-people-group', 'color': '#6366f1'},
    {'key': 'oac_weekly', 'label': 'OAC Weekly Progress', 'icon': 'fa-calendar-week', 'color': '#8b5cf6'},
    {'key': 'superintendent', 'label': 'Superintendent / Field', 'icon': 'fa-hard-hat', 'color': '#f59e0b'},
    {'key': 'owner', 'label': 'Owner Meeting', 'icon': 'fa-building-user', 'color': '#0ea5e9'},
    {'key': 'subcontractor', 'label': 'Subcontractor Coordination', 'icon': 'fa-truck-field', 'color': '#14b8a6'},
    {'key': 'precon', 'label': 'Pre-Construction', 'icon': 'fa-clipboard-list', 'color': '#a855f7'},
    {'key': 'safety', 'label': 'Safety Meeting', 'icon': 'fa-shield-halved', 'color': '#ef4444'},
    {'key': 'toolbox_talk', 'label': 'Toolbox / Tailgate Talk', 'icon': 'fa-toolbox', 'color': '#f97316'},
    {'key': 'design', 'label': 'Design Coordination / BIM', 'icon': 'fa-compass-drafting', 'color': '#06b6d4'},
    {'key': 'schedule', 'label': 'Schedule / CPM Review', 'icon': 'fa-chart-gantt', 'color': '#22c55e'},
    {'key': 'submittal', 'label': 'Submittal Review', 'icon': 'fa-file-circle-check', 'color': '#84cc16'},
    {'key': 'closeout', 'label': 'Closeout / Punch', 'icon': 'fa-flag-checkered', 'color': '#10b981'},
    {'key': 'internal', 'label': 'Internal Team', 'icon': 'fa-users', 'color': '#71717a'},
    {'key': 'stakeholder', 'label': 'Client / Stakeholder', 'icon': 'fa-handshake', 'color': '#ec4899'},
    {'key': 'other', 'label': 'Other', 'icon': 'fa-ellipsis', 'color': '#52525b'},
]

STATUSES = (
    'Draft', 'Scheduled', 'In Progress', 'Completed', 'Distributed', 'Cancelled',
)

OPEN_STATUSES = ('Draft', 'Scheduled', 'In Progress')

ACTION_STATUSES = ('Open', 'In Progress', 'Complete', 'Deferred', 'Cancelled')

ACTION_PRIORITIES = ('Low', 'Normal', 'High', 'Critical')

DEFAULT_SPEAKERS = [
    {'id': 'sp1', 'label': 'Person 1', 'name': '', 'color': '#6366f1'},
    {'id': 'sp2', 'label': 'Person 2', 'name': '', 'color': '#f59e0b'},
    {'id': 'sp3', 'label': 'Person 3', 'name': '', 'color': '#14b8a6'},
]

# Default agenda templates by meeting type
AGENDA_TEMPLATES = {
    'oac': [
        {'topic': 'Call to order / attendance', 'presenter': '', 'minutes': 5},
        {'topic': 'Review of previous meeting minutes & action items', 'presenter': '', 'minutes': 10},
        {'topic': 'Safety / site conditions', 'presenter': 'Superintendent', 'minutes': 10},
        {'topic': 'Schedule update & critical path', 'presenter': 'PM / Scheduler', 'minutes': 15},
        {'topic': 'Budget / change orders / pay apps', 'presenter': 'PM', 'minutes': 15},
        {'topic': 'RFIs, submittals, design issues', 'presenter': 'PM / Architect', 'minutes': 20},
        {'topic': 'New business / owner directives', 'presenter': 'Owner', 'minutes': 15},
        {'topic': 'Action items recap & adjournment', 'presenter': 'PM', 'minutes': 5},
    ],
    'oac_weekly': [
        {'topic': 'Attendance & safety moment', 'presenter': '', 'minutes': 5},
        {'topic': 'Progress since last meeting (photos / percent complete)', 'presenter': 'Superintendent', 'minutes': 15},
        {'topic': 'Look-ahead (2-week)', 'presenter': 'Superintendent', 'minutes': 10},
        {'topic': 'Open RFIs & submittals', 'presenter': 'PM', 'minutes': 15},
        {'topic': 'Coordination issues / conflicts', 'presenter': 'Superintendent', 'minutes': 15},
        {'topic': 'Action items', 'presenter': 'PM', 'minutes': 10},
    ],
    'superintendent': [
        {'topic': 'Daily safety & manpower', 'presenter': 'Superintendent', 'minutes': 5},
        {'topic': 'Work planned today / tomorrow', 'presenter': 'Superintendent', 'minutes': 10},
        {'topic': 'Deliveries & crane / equipment', 'presenter': 'Superintendent', 'minutes': 10},
        {'topic': 'Trade coordination & conflicts', 'presenter': 'Superintendent', 'minutes': 15},
        {'topic': 'Inspections & permits', 'presenter': 'Superintendent', 'minutes': 10},
        {'topic': 'Action items', 'presenter': '', 'minutes': 5},
    ],
    'owner': [
        {'topic': 'Project status summary', 'presenter': 'PM', 'minutes': 15},
        {'topic': 'Schedule & milestones', 'presenter': 'PM', 'minutes': 15},
        {'topic': 'Budget & contingency', 'presenter': 'PM', 'minutes': 15},
        {'topic': 'Decisions required from owner', 'presenter': 'Owner', 'minutes': 20},
        {'topic': 'Next steps', 'presenter': 'PM', 'minutes': 10},
    ],
    'subcontractor': [
        {'topic': 'Attendance & scope review', 'presenter': 'PM', 'minutes': 5},
        {'topic': 'Schedule commitments by trade', 'presenter': 'Superintendent', 'minutes': 15},
        {'topic': 'Coordination & access', 'presenter': 'Superintendent', 'minutes': 15},
        {'topic': 'Quality / punch / rework', 'presenter': 'PM', 'minutes': 10},
        {'topic': 'Action items & follow-up date', 'presenter': 'PM', 'minutes': 10},
    ],
    'safety': [
        {'topic': 'Toolbox topic / OSHA focus', 'presenter': 'Safety', 'minutes': 10},
        {'topic': 'Incidents / near-miss review', 'presenter': 'Safety', 'minutes': 10},
        {'topic': 'Hazards on site this week', 'presenter': 'Superintendent', 'minutes': 10},
        {'topic': 'PPE & compliance', 'presenter': 'Safety', 'minutes': 5},
        {'topic': 'Action items', 'presenter': '', 'minutes': 5},
    ],
    'toolbox_talk': [
        {'topic': 'Roll call / attendance & sign-in', 'presenter': 'Foreman / Safety', 'minutes': 3},
        {'topic': 'Safety moment — topic of the day', 'presenter': 'Safety', 'minutes': 5},
        {'topic': 'Work planned today & associated hazards', 'presenter': 'Superintendent', 'minutes': 8},
        {'topic': 'JHA / safe work procedures review', 'presenter': 'Foreman', 'minutes': 7},
        {'topic': 'PPE requirements for today\'s tasks', 'presenter': 'Safety', 'minutes': 5},
        {'topic': 'Equipment & tool safety checks', 'presenter': 'Foreman', 'minutes': 5},
        {'topic': 'Housekeeping, access & fall protection', 'presenter': 'Superintendent', 'minutes': 5},
        {'topic': 'Emergency response & muster point', 'presenter': 'Safety', 'minutes': 3},
        {'topic': 'Questions, concerns & crew feedback', 'presenter': '', 'minutes': 4},
        {'topic': 'Sign-off & documentation', 'presenter': 'Foreman', 'minutes': 2},
    ],
    'precon': [
        {'topic': 'Project goals & constraints', 'presenter': 'PM', 'minutes': 15},
        {'topic': 'Logistics & phasing', 'presenter': 'Superintendent', 'minutes': 15},
        {'topic': 'Long-lead items & procurement', 'presenter': 'PM', 'minutes': 15},
        {'topic': 'Permits & AHJ strategy', 'presenter': 'PM', 'minutes': 10},
        {'topic': 'Action items', 'presenter': 'PM', 'minutes': 10},
    ],
    'design': [
        {'topic': 'Design status by discipline', 'presenter': 'Architect', 'minutes': 15},
        {'topic': 'Clashes / BIM coordination', 'presenter': 'BIM Lead', 'minutes': 20},
        {'topic': 'Outstanding design decisions', 'presenter': 'Architect', 'minutes': 15},
        {'topic': 'Action items', 'presenter': 'PM', 'minutes': 10},
    ],
    'schedule': [
        {'topic': 'Baseline vs actual', 'presenter': 'Scheduler', 'minutes': 15},
        {'topic': 'Critical path & float', 'presenter': 'Scheduler', 'minutes': 15},
        {'topic': 'Recovery plan (if applicable)', 'presenter': 'PM', 'minutes': 15},
        {'topic': 'Action items', 'presenter': 'PM', 'minutes': 10},
    ],
    'submittal': [
        {'topic': 'Submittals log review', 'presenter': 'PM', 'minutes': 20},
        {'topic': 'Approvals pending / revisions', 'presenter': 'Architect', 'minutes': 20},
        {'topic': 'Procurement impacts', 'presenter': 'PM', 'minutes': 10},
        {'topic': 'Action items', 'presenter': 'PM', 'minutes': 10},
    ],
    'closeout': [
        {'topic': 'Punch list status', 'presenter': 'PM', 'minutes': 15},
        {'topic': 'O&M manuals & warranties', 'presenter': 'PM', 'minutes': 15},
        {'topic': 'Training & commissioning', 'presenter': 'PM', 'minutes': 10},
        {'topic': 'Final pay / retainage / lien waivers', 'presenter': 'PM', 'minutes': 15},
        {'topic': 'Action items', 'presenter': 'PM', 'minutes': 10},
    ],
    'internal': [
        {'topic': 'Project pulse / risks', 'presenter': 'PM', 'minutes': 10},
        {'topic': 'Staffing & assignments', 'presenter': 'PM', 'minutes': 10},
        {'topic': 'Client / owner issues', 'presenter': 'PM', 'minutes': 10},
        {'topic': 'Action items', 'presenter': '', 'minutes': 5},
    ],
    'stakeholder': [
        {'topic': 'Introductions & objectives', 'presenter': 'PM', 'minutes': 10},
        {'topic': 'Project overview & status', 'presenter': 'PM', 'minutes': 20},
        {'topic': 'Q&A', 'presenter': '', 'minutes': 20},
        {'topic': 'Next steps', 'presenter': 'PM', 'minutes': 10},
    ],
    'other': [
        {'topic': 'Agenda item 1', 'presenter': '', 'minutes': 15},
        {'topic': 'Agenda item 2', 'presenter': '', 'minutes': 15},
        {'topic': 'Action items', 'presenter': '', 'minutes': 10},
    ],
}


def get_agenda_template(meeting_type):
    return [dict(x) for x in AGENDA_TEMPLATES.get(meeting_type, AGENDA_TEMPLATES['other'])]
