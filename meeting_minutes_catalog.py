"""
Meeting minutes catalog — types, statuses, agenda templates.
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
        {'topic': 'Roll call / attendance & sign-in sheet', 'presenter': 'Foreman / Safety', 'minutes': 3},
        {'topic': 'Review prior meeting action items', 'presenter': 'Foreman', 'minutes': 3},
        {'topic': 'Safety moment — topic of the day (OSHA focus)', 'presenter': 'Safety', 'minutes': 5},
        {'topic': 'Work planned today & associated hazards (JHA)', 'presenter': 'Superintendent', 'minutes': 8},
        {'topic': 'Safe work procedures & permit requirements', 'presenter': 'Foreman', 'minutes': 5},
        {'topic': 'PPE requirements for today\'s tasks', 'presenter': 'Safety', 'minutes': 5},
        {'topic': 'Equipment, tools & inspection checks', 'presenter': 'Foreman', 'minutes': 5},
        {'topic': 'Housekeeping, access, slips/trips & fall protection', 'presenter': 'Superintendent', 'minutes': 5},
        {'topic': 'Emergency response, muster point & first aid', 'presenter': 'Safety', 'minutes': 3},
        {'topic': 'Questions, concerns & crew feedback', 'presenter': '', 'minutes': 4},
        {'topic': 'New action items & sign-off / documentation', 'presenter': 'Foreman', 'minutes': 4},
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
    rows = [dict(x) for x in AGENDA_TEMPLATES.get(meeting_type, AGENDA_TEMPLATES['other'])]
    if meeting_type == 'toolbox_talk':
        for row in rows:
            key = row.get('briefing_key') or _briefing_key_for_topic(row.get('topic', ''))
            brief = TOOLBOX_AGENDA_BRIEFINGS.get(key)
            if brief:
                row['briefing_key'] = key
                row['briefing'] = brief.get('briefing', '')
                row['checklist'] = brief.get('checklist', [])
                row['talking_points'] = brief.get('talking_points', [])
    return rows


def _briefing_key_for_topic(topic):
    t = (topic or '').lower()
    if 'roll call' in t or 'attendance' in t:
        return 'roll_call'
    if 'prior' in t and 'action' in t:
        return 'prior_actions'
    if 'safety moment' in t or 'topic of the day' in t:
        return 'safety_moment'
    if 'jha' in t or 'hazards' in t and 'planned' in t:
        return 'jha_hazards'
    if 'safe work' in t or 'permit' in t:
        return 'safe_work'
    if 'ppe' in t:
        return 'ppe'
    if 'equipment' in t or 'tool' in t:
        return 'equipment'
    if 'housekeeping' in t or 'fall protection' in t:
        return 'housekeeping'
    if 'emergency' in t or 'muster' in t or 'first aid' in t:
        return 'emergency'
    if 'question' in t or 'feedback' in t:
        return 'questions'
    if 'action item' in t or 'sign-off' in t or 'documentation' in t:
        return 'wrap_up'
    return 'general'


# Built-in briefing scripts for each standard toolbox agenda item (meeting runner).
TOOLBOX_AGENDA_BRIEFINGS = {
    'roll_call': {
        'briefing': 'Welcome crew. Confirm everyone is present and signed in. Verify visitors and new workers are accounted for. Note any absentees and whether they received briefing notes.',
        'talking_points': ['Pass around sign-in sheet or use digital attendance', 'Confirm crew size matches work plan', 'Identify any workers new to this task or site'],
        'checklist': ['Sign-in sheet started', 'All trades represented', 'Visitors identified'],
    },
    'prior_actions': {
        'briefing': 'Review open action items from the last toolbox talk or safety meeting. Confirm each item is closed, in progress, or carried forward with an owner and due date.',
        'talking_points': ['Read each open action item aloud', 'Ask responsible person for status', 'Escalate overdue items to superintendent'],
        'checklist': ['Prior actions reviewed', 'Owners confirmed', 'New due dates set'],
    },
    'safety_moment': {
        'briefing': 'Present today\'s focused safety topic. Use the topic library to cover OSHA requirements, real-world examples, and site-specific hazards. Allow questions.',
        'talking_points': ['State the topic clearly', 'Cover key hazards and controls', 'Reference applicable OSHA standard', 'Tie topic to work planned today'],
        'checklist': ['Topic stated', 'Hazards discussed', 'Questions answered'],
    },
    'jha_hazards': {
        'briefing': 'Walk through work planned today by area and trade. Identify hazards for each activity using JHA thinking: what can go wrong, and how do we prevent it?',
        'talking_points': ['Review today\'s critical activities', 'Identify top hazards per activity', 'Confirm permits (hot work, confined space, excavation)', 'Coordinate overlapping trades'],
        'checklist': ['Work areas identified', 'Hazards listed per task', 'Permits verified'],
    },
    'safe_work': {
        'briefing': 'Review safe work procedures, SOPs, and permit requirements for today\'s high-risk tasks. Confirm only qualified workers perform restricted work.',
        'talking_points': ['Review applicable SOPs', 'Confirm permit status', 'Verify competent persons assigned', 'Stop work if conditions change'],
        'checklist': ['SOPs referenced', 'Permits in place', 'Qualified personnel confirmed'],
    },
    'ppe': {
        'briefing': 'State required PPE for each task today. Inspect PPE condition. No exemptions without written approval and substitution per hazard assessment.',
        'talking_points': ['Hard hat, eye, foot protection minimums', 'Task-specific PPE (respirator, harness, etc.)', 'Inspect before use — replace damaged PPE', 'High-vis in active zones'],
        'checklist': ['PPE requirements stated', 'Crew PPE inspected', 'Specialty PPE available'],
    },
    'equipment': {
        'briefing': 'Confirm tools and equipment are inspected, guarded, and operated by trained users. Tag out defective equipment. Review lifting/rigging plans if applicable.',
        'talking_points': ['Pre-use inspection', 'Guards and safety devices in place', 'Qualified operators only', 'Spotters and exclusion zones for lifts'],
        'checklist': ['Equipment inspected', 'Defective items tagged out', 'Lift plan reviewed if needed'],
    },
    'housekeeping': {
        'briefing': 'Maintain clean walkways, secure materials, and proper fall protection at edges and openings. Good housekeeping prevents slips, trips, and falls.',
        'talking_points': ['Clear access/egress routes', 'Secure materials and debris', 'Cover/protect floor openings', 'Fall protection at leading edges'],
        'checklist': ['Walkways clear', 'Openings covered', 'Fall protection verified'],
    },
    'emergency': {
        'briefing': 'Confirm everyone knows the emergency plan: muster point, first aid kit/AED location, how to report injuries, and who to call. Verify communication works on site.',
        'talking_points': ['Muster point location', 'First aid / AED location', 'Emergency contacts posted', 'Report all injuries immediately — no matter how minor'],
        'checklist': ['Muster point confirmed', 'First aid location known', 'Emergency numbers posted'],
    },
    'questions': {
        'briefing': 'Open the floor for questions, concerns, and near-miss reports. Encourage speaking up — no retaliation. Document all concerns raised.',
        'talking_points': ['Ask "Does anyone see a hazard we missed?"', 'Welcome near-miss reports', 'Document concerns for follow-up'],
        'checklist': ['Questions answered', 'Concerns documented', 'Near misses captured'],
    },
    'wrap_up': {
        'briefing': 'Summarize new action items with owners and due dates. Confirm everyone understands today\'s hazards and controls. Complete sign-in sheet and file this record.',
        'talking_points': ['Recap top hazards', 'Assign action items', 'Collect sign-in sheet', 'Adjourn — work safe'],
        'checklist': ['Action items assigned', 'Sign-in complete', 'Record filed'],
    },
    'general': {
        'briefing': 'Discuss this agenda item with the crew. Cover relevant hazards, controls, and any site-specific requirements.',
        'talking_points': ['State the topic', 'Cover hazards and controls', 'Confirm understanding'],
        'checklist': ['Topic covered', 'Questions answered'],
    },
}


# OSHA / Cal-OSHA aligned toolbox talk reference library.
TOOLBOX_COMPLIANCE = {
    'title': 'Toolbox / Tailgate Safety Meeting',
    'osha_refs': [
        '29 CFR 1926.21(b)(2) — safety training and hazard recognition',
        '29 CFR 1926.20(b) — accident prevention programs',
        'Cal/OSHA Title 8 §1509 — tailgate safety meetings (construction)',
    ],
    'duration_minutes': '10–15',
    'requirements': [
        'Hold before shift or when work/tasks change',
        'Document date, topic, presenter, attendees, and hazards discussed',
        'Review prior action items; record new hazards and follow-ups',
        'Keep records on site — typical retention 3+ years',
    ],
}

TOOLBOX_TOPIC_LIBRARY = [
    {
        'category': 'Fall Protection',
        'topics': [
            {'title': 'Leading edge & unprotected sides', 'osha_ref': '1926.501', 'points': ['6 ft trigger height', 'Guardrails, nets, or PFAS', 'Hole covers secured and labeled'], 'ppe': ['Harness', 'Lanyard / SRL', 'Hard hat']},
            {'title': 'Ladders & stairways', 'osha_ref': '1926.1053', 'points': ['3-point contact', 'Extend 3 ft above landing', 'Do not use top step'], 'ppe': ['Hard hat', 'Non-slip footwear']},
            {'title': 'Scaffolds', 'osha_ref': '1926.451', 'points': ['Competent person inspection', 'Full planking & guardrails', 'No climbing cross-braces'], 'ppe': ['Hard hat', 'Harness when required']},
        ],
    },
    {
        'category': 'Excavation & Trenching',
        'topics': [
            {'title': 'Trenching & excavation', 'osha_ref': '1926.651', 'points': ['Competent person daily', 'Sloping/benching/shoring/shielding', 'Keep spoils 2 ft back', 'Access/egress every 25 ft'], 'ppe': ['Hard hat', 'High-vis', 'Boots']},
            {'title': 'Utility locate & potholing', 'osha_ref': '1926.651', 'points': ['Call 811 / verify locates', 'Hand dig within tolerance zone', 'Stop work if unmarked line'], 'ppe': ['Hard hat', 'Gloves', 'Eye protection']},
        ],
    },
    {
        'category': 'Electrical',
        'topics': [
            {'title': 'Electrical safety & GFCI', 'osha_ref': '1926.404', 'points': ['GFCI on temp power', 'Inspect cords — no frays', 'Maintain clearance from lines'], 'ppe': ['Insulated gloves when required', 'Arc-rated PPE for qualified work']},
            {'title': 'Lockout / tagout awareness', 'osha_ref': '1926.417', 'points': ['Only authorized LOTO', 'Verify zero energy', 'Never remove another\'s lock'], 'ppe': ['As required by task']},
        ],
    },
    {
        'category': 'Cranes & Rigging',
        'topics': [
            {'title': 'Crane & hoist safety', 'osha_ref': '1926.1400', 'points': ['Lift director / signal person', 'Stay out of swing radius', 'Never walk under suspended load'], 'ppe': ['Hard hat', 'High-vis', 'Steel-toe']},
            {'title': 'Rigging & slings', 'osha_ref': '1926.251', 'points': ['Inspect slings before use', 'Know load weight & center of gravity', 'Proper hitch & angle limits'], 'ppe': ['Hard hat', 'Gloves', 'High-vis']},
        ],
    },
    {
        'category': 'PPE & Health',
        'topics': [
            {'title': 'Head, eye & face protection', 'osha_ref': '1926.100–102', 'points': ['Hard hats where overhead hazard', 'Safety glasses — side shields', 'Face shield for grinding/cutting'], 'ppe': ['Hard hat', 'Safety glasses', 'Face shield']},
            {'title': 'Hearing conservation', 'osha_ref': '1926.52', 'points': ['85 dBA action level', 'Double protection in high noise', 'Limit exposure time'], 'ppe': ['Earplugs', 'Earmuffs']},
            {'title': 'Silica & dust control', 'osha_ref': '1926.1153', 'points': ['Wet methods / vacuum / enclosure', 'Table 1 controls when applicable', 'No dry sweeping'], 'ppe': ['Respirator per exposure assessment']},
            {'title': 'Heat illness prevention', 'osha_ref': '1926.28', 'points': ['Water, rest, shade', 'Acclimatization for new workers', 'Buddy system in high heat'], 'ppe': ['Light-colored clothing', 'Sun protection']},
        ],
    },
    {
        'category': 'Site Conditions',
        'topics': [
            {'title': 'Housekeeping & slips/trips', 'osha_ref': '1926.25', 'points': ['Clear walkways & stairs', 'Secure cords and hoses', 'Dispose of debris promptly'], 'ppe': ['Non-slip footwear', 'Hard hat']},
            {'title': 'Traffic control & flagging', 'osha_ref': '1926.200', 'points': ['Approved TCP / MOT plan', 'High-vis and escape route', 'Stay alert in work zones'], 'ppe': ['Class 2/3 high-vis', 'Hard hat']},
            {'title': 'Fire prevention & hot work', 'osha_ref': '1926.352', 'points': ['Hot work permit', 'Fire watch 30 min after', 'Extinguishers within 25 ft'], 'ppe': ['Welding hood', 'Fire-resistant clothing', 'Gloves']},
            {'title': 'Confined space awareness', 'osha_ref': '1926.1200', 'points': ['Permit-required spaces identified', 'Never enter without authorization', 'Atmospheric testing & attendant'], 'ppe': ['As required by entry permit']},
        ],
    },
    {
        'category': 'Tools & Equipment',
        'topics': [
            {'title': 'Hand & power tools', 'osha_ref': '1926.300', 'points': ['Inspect before use', 'Guards in place', 'Right tool for the job'], 'ppe': ['Eye protection', 'Gloves', 'Hearing protection']},
            {'title': 'Aerial & scissor lifts', 'osha_ref': '1926.453', 'points': ['Trained operators only', 'Tie-off in boom lifts', 'Survey ground & overhead'], 'ppe': ['Harness & lanyard in boom', 'Hard hat']},
            {'title': 'Forklifts / PIT', 'osha_ref': '1926.602', 'points': ['Certified operators', 'No riders unless designed', 'Sound horn at intersections'], 'ppe': ['Hard hat', 'High-vis', 'Steel-toe']},
        ],
    },
    {
        'category': 'Emergency & General',
        'topics': [
            {'title': 'Emergency action & muster', 'osha_ref': '1926.35', 'points': ['Know muster point & routes', 'Report all injuries immediately', 'AED / first aid location'], 'ppe': []},
            {'title': 'Near-miss reporting', 'osha_ref': '1926.20', 'points': ['Report near misses same day', 'No blame — fix the hazard', 'Share lessons with crew'], 'ppe': []},
            {'title': 'Hazard communication (GHS)', 'osha_ref': '1926.59', 'points': ['Read SDS before use', 'Label secondary containers', 'Wash after chemical contact'], 'ppe': ['Chemical gloves', 'Goggles', 'Respirator per SDS']},
        ],
    },
]


def get_toolbox_topic_library():
    return [dict(cat, topics=[dict(t) for t in cat['topics']]) for cat in TOOLBOX_TOPIC_LIBRARY]
