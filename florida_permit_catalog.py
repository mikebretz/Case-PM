"""
Florida Building Code (8th Ed.) inspection templates, permit trades, and authority types.

References: FBC Ch. 110 (Inspections), DBPR Florida Building Commission, local AHJ practice.
Verify jurisdiction-specific requirements — sequencing is determined by the Building Official (FBC 110.3).
"""

# ── Permit / trade categories (sub-permits) ──────────────────────────────────
PERMIT_TRADES = [
    {'key': 'building', 'label': 'Building / Structural', 'icon': 'fa-building', 'color': '#6366f1'},
    {'key': 'electrical', 'label': 'Electrical', 'icon': 'fa-bolt', 'color': '#f59e0b'},
    {'key': 'plumbing', 'label': 'Plumbing', 'icon': 'fa-faucet', 'color': '#0ea5e9'},
    {'key': 'mechanical', 'label': 'Mechanical / HVAC', 'icon': 'fa-fan', 'color': '#8b5cf6'},
    {'key': 'gas', 'label': 'Fuel Gas', 'icon': 'fa-fire-flame-simple', 'color': '#ef4444'},
    {'key': 'fire', 'label': 'Fire / Life Safety', 'icon': 'fa-fire-extinguisher', 'color': '#dc2626'},
    {'key': 'low_voltage', 'label': 'Low Voltage / Communications', 'icon': 'fa-network-wired', 'color': '#14b8a6'},
    {'key': 'roofing', 'label': 'Roofing', 'icon': 'fa-house-chimney', 'color': '#78716c'},
    {'key': 'pool', 'label': 'Swimming Pool / Spa', 'icon': 'fa-person-swimming', 'color': '#06b6d4'},
    {'key': 'demolition', 'label': 'Demolition', 'icon': 'fa-hammer', 'color': '#71717a'},
    {'key': 'accessibility', 'label': 'Accessibility (FBC Ch. 11)', 'icon': 'fa-wheelchair', 'color': '#a855f7'},
    {'key': 'energy', 'label': 'Energy / Insulation', 'icon': 'fa-leaf', 'color': '#22c55e'},
    {'key': 'flood', 'label': 'Flood / Elevation Cert', 'icon': 'fa-water', 'color': '#3b82f6'},
    {'key': 'threshold', 'label': 'Threshold Building (Ch. 553)', 'icon': 'fa-city', 'color': '#e11d48'},
    {'key': 'milestone', 'label': 'Milestone / CO / TCO', 'icon': 'fa-flag-checkered', 'color': '#10b981'},
    {'key': 'other', 'label': 'Other / Special', 'icon': 'fa-clipboard-list', 'color': '#52525b'},
]

STATUSES = (
    'Not Started', 'Application Submitted', 'In Review', 'Issued',
    'Scheduled', 'Inspection Requested', 'Passed', 'Failed',
    'Correction Required', 'Re-inspection Scheduled', 'Closed', 'Cancelled',
)

OPEN_STATUSES = (
    'Not Started', 'Application Submitted', 'In Review', 'Issued',
    'Scheduled', 'Inspection Requested', 'Failed', 'Correction Required', 'Re-inspection Scheduled',
)

JURISDICTION_LEVELS = (
    'state', 'county', 'city', 'special_district', 'utility', 'fire_district', 'water_management', 'health', 'fdot', 'private_utility',
)

# FBC 110.3 required inspections by trade — templates for "Add checklist from FBC"
FBC_INSPECTION_TEMPLATES = {
    'building': [
        {'phase': 'preliminary', 'title': 'Preliminary / Plan Review', 'fbc_ref': 'FBC 110.2', 'notes': 'Before permit issuance; site and existing conditions.'},
        {'phase': 'foundation', 'title': 'Foundation Inspection', 'fbc_ref': 'FBC 110.3 Building #1', 'notes': 'Stem wall, monolithic slab, pilings, footers, grade beams. Flood: elevation cert before vertical construction.'},
        {'phase': 'framing', 'title': 'Framing Inspection', 'fbc_ref': 'FBC 110.3 Building #2', 'notes': 'Roof/framing, fire-blocking, concealed wiring/pipes/ducts complete, before concealment.'},
        {'phase': 'sheathing', 'title': 'Sheathing / Dry-In Inspection', 'fbc_ref': 'FBC 110.3 Building #3', 'notes': 'Roof/wall sheathing, fasteners, dry-in.'},
        {'phase': 'exterior', 'title': 'Exterior Wall Coverings', 'fbc_ref': 'FBC 110.3 Building #4', 'notes': 'Wall coverings, veneers, soffit.'},
        {'phase': 'roofing', 'title': 'Roofing Inspection', 'fbc_ref': 'FBC 110.3 Building #5', 'notes': 'Dry-in, insulation, coverings, flashing.'},
        {'phase': 'impact', 'title': 'Impact-Resistant Coverings', 'fbc_ref': 'FBC 110.3 Building #10', 'notes': 'HVHZ — verify product approval and installation per manufacturer.'},
        {'phase': 'final', 'title': 'Building Final / CO', 'fbc_ref': 'FBC 110.3 Building #6', 'notes': 'Building complete, ready for occupancy. Flood: final elevation cert.'},
    ],
    'electrical': [
        {'phase': 'underground', 'title': 'Electrical Underground', 'fbc_ref': 'FBC 110.3 Electrical #1', 'notes': 'Trenches excavated, conduit/cable installed, before backfill.'},
        {'phase': 'rough_in', 'title': 'Electrical Rough-In', 'fbc_ref': 'FBC 110.3 Electrical #2', 'notes': 'After framing; before concealment. Includes bonding, grounding.'},
        {'phase': 'service', 'title': 'Electrical Service / Panel', 'fbc_ref': 'NEC 230', 'notes': 'Service entrance, main panel, meter coordination with utility.'},
        {'phase': 'temporary', 'title': 'Temporary Power', 'fbc_ref': 'Local AHJ', 'notes': 'Temp pole / construction power — utility connect after AHJ approval.'},
        {'phase': 'final', 'title': 'Electrical Final', 'fbc_ref': 'FBC 110.3 Electrical #3', 'notes': 'All fixtures/devices in place and connected.'},
    ],
    'plumbing': [
        {'phase': 'underground', 'title': 'Plumbing Underground', 'fbc_ref': 'FBC 110.3 Plumbing #1', 'notes': 'Piping in trenches before backfill.'},
        {'phase': 'rough_in', 'title': 'Plumbing Rough-In', 'fbc_ref': 'FBC 110.3 Plumbing #2', 'notes': 'DWV, water supply complete; before concealment. Pressure test per FBC 312.'},
        {'phase': 'top_out', 'title': 'Plumbing Top-Out / Stack', 'fbc_ref': 'Local AHJ', 'notes': 'Vertical stacks, venting through roof.'},
        {'phase': 'gas_rough', 'title': 'Gas Piping Rough (if applicable)', 'fbc_ref': 'Fuel Gas Code', 'notes': 'Pressure test before concealment.'},
        {'phase': 'final', 'title': 'Plumbing Final', 'fbc_ref': 'FBC 110.3 Plumbing #3', 'notes': 'All fixtures installed and connected.'},
    ],
    'mechanical': [
        {'phase': 'rough_in', 'title': 'Mechanical Rough-In', 'fbc_ref': 'FBC 110.3 Mechanical #1', 'notes': 'Ducts, refrigerant lines, equipment pads before concealment.'},
        {'phase': 'hood', 'title': 'Commercial Hood / Kitchen Exhaust', 'fbc_ref': 'IMC + Fire', 'notes': 'Coordinate with fire AHJ for Type I hoods.'},
        {'phase': 'final', 'title': 'Mechanical Final', 'fbc_ref': 'FBC 110.3 Mechanical #2', 'notes': 'Equipment operational, filters, condensate, access panels.'},
    ],
    'gas': [
        {'phase': 'rough_in', 'title': 'Fuel Gas Rough-In', 'fbc_ref': 'FBC Fuel Gas', 'notes': 'Piping pressure test before concealment.'},
        {'phase': 'line_pressure', 'title': 'Gas Line Pressure Test', 'fbc_ref': 'FBC Fuel Gas', 'notes': 'Air or inert gas test; witness by inspector.'},
        {'phase': 'final', 'title': 'Fuel Gas Final', 'fbc_ref': 'FBC Fuel Gas', 'notes': 'Appliances connected, leak check, venting verified.'},
    ],
    'fire': [
        {'phase': 'underground', 'title': 'Fire Underground / Fire Line', 'fbc_ref': 'NFPA 24 / Local Fire', 'notes': 'Fire mains, FDC, before backfill.'},
        {'phase': 'rough_in', 'title': 'Fire Sprinkler Rough-In', 'fbc_ref': 'NFPA 13', 'notes': 'Piping before concealment; hydrostatic test.'},
        {'phase': 'alarm_rough', 'title': 'Fire Alarm Rough-In', 'fbc_ref': 'NFPA 72', 'notes': 'Devices, wiring, FACP location.'},
        {'phase': 'hood', 'title': 'Hood Suppression System', 'fbc_ref': 'NFPA 96 / 17A', 'notes': 'Kitchen suppression — fire marshal witness.'},
        {'phase': 'final', 'title': 'Fire Final / Acceptance Test', 'fbc_ref': 'Florida Fire Prevention Code', 'notes': 'Sprinkler, alarm, smoke control acceptance.'},
    ],
    'low_voltage': [
        {'phase': 'rough_in', 'title': 'Low Voltage Rough-In', 'fbc_ref': 'NEC Ch. 8 / 725 / 800', 'notes': 'Data, security, AV cabling before concealment.'},
        {'phase': 'fire_alarm', 'title': 'Fire Alarm (Low Voltage)', 'fbc_ref': 'NFPA 72', 'notes': 'May be under separate fire permit.'},
        {'phase': 'final', 'title': 'Low Voltage Final', 'fbc_ref': 'Local AHJ', 'notes': 'Terminations, labeling, device operation.'},
    ],
    'roofing': [
        {'phase': 'dry_in', 'title': 'Roof Dry-In', 'fbc_ref': 'FBC Roofing', 'notes': 'Underlayment, secondary water barrier (HVHZ).'},
        {'phase': 'in_progress', 'title': 'Roof In-Progress', 'fbc_ref': 'FBC 110.3 Building #5', 'notes': 'Fasteners, product approval documentation on site.'},
        {'phase': 'final', 'title': 'Roofing Final', 'fbc_ref': 'FBC Roofing', 'notes': 'Complete assembly, flashing, penetrations.'},
    ],
    'pool': [
        {'phase': 'rough', 'title': 'Pool Steel / Bonding / Main Drain', 'fbc_ref': 'FBC 110.3 Building #7', 'notes': 'After excavation and steel; before gunite/shotcrete.'},
        {'phase': 'deck', 'title': 'Pool Deck / Coping', 'fbc_ref': 'FBC 454', 'notes': 'Bonding, equipotential grid.'},
        {'phase': 'barrier', 'title': 'Pool Barrier / Safety Features', 'fbc_ref': 'FBC 454.2.17', 'notes': 'Required safety features for residential pools.'},
        {'phase': 'final', 'title': 'Pool Final', 'fbc_ref': 'FBC 110.3 Building #7', 'notes': 'Pool complete, enclosure, electrical bonding.'},
    ],
    'demolition': [
        {'phase': 'pre_demo', 'title': 'Pre-Demolition', 'fbc_ref': 'FBC 110.3 Building #8', 'notes': 'Utilities disconnected/secured; asbestos survey if required.'},
        {'phase': 'final', 'title': 'Demolition Final', 'fbc_ref': 'FBC 110.3 Building #8', 'notes': 'Site cleared, safeguards removed.'},
    ],
    'flood': [
        {'phase': 'elevation_pre', 'title': 'Lowest Floor Elevation (Pre)', 'fbc_ref': 'FBC 110.3 / FEMA', 'notes': 'Before further vertical construction in flood hazard areas.'},
        {'phase': 'elevation_final', 'title': 'Final Elevation Certificate', 'fbc_ref': 'FEMA EC', 'notes': 'Submitted with final inspection.'},
        {'phase': 'dry_floodproof', 'title': 'Dry Floodproofing Cert', 'fbc_ref': 'FBC / FEMA', 'notes': 'Non-residential dry floodproofed structures.'},
    ],
    'threshold': [
        {'phase': 'threshold_review', 'title': 'Threshold Building Review', 'fbc_ref': 'F.S. 553.71', 'notes': 'Buildings >3 stories or >50 ft — special inspector program.'},
        {'phase': 'special_inspector', 'title': 'Special Inspector Report', 'fbc_ref': 'F.S. 553.79', 'notes': 'Continuous special inspections per structural plan.'},
        {'phase': 'milestone', 'title': 'Threshold Milestone Inspection', 'fbc_ref': 'F.S. 553.79', 'notes': 'Required milestone sign-offs.'},
    ],
    'milestone': [
        {'phase': 'tco', 'title': 'Temporary Certificate of Occupancy', 'fbc_ref': 'Local AHJ', 'notes': 'Partial occupancy — outstanding items documented.'},
        {'phase': 'co', 'title': 'Certificate of Occupancy', 'fbc_ref': 'Local AHJ', 'notes': 'All finals passed; CO issued.'},
        {'phase': 'cc', 'title': 'Certificate of Completion', 'fbc_ref': 'Local AHJ', 'notes': 'For alterations without full CO change.'},
    ],
}

# State-level governing bodies (Florida)
FLORIDA_STATE_AUTHORITIES = [
    {
        'id': 'dbpr-bcaib',
        'name': 'DBPR — Building Code Administrators & Inspectors Board',
        'role': 'Licenses building officials, inspectors, plans examiners statewide',
        'phone': '(850) 487-1395',
        'url': 'https://www2.myfloridalicense.com/building-code-administrators-and-inspectors/',
        'category': 'state',
    },
    {
        'id': 'florida-building-commission',
        'name': 'Florida Building Commission (via DBPR)',
        'role': 'Adopts and maintains Florida Building Code; product approval',
        'phone': '(850) 487-1824',
        'url': 'https://www2.myfloridalicense.com/building-codes-and-standards/',
        'category': 'state',
    },
    {
        'id': 'floridabuilding-org',
        'name': 'Florida Building Code Information System (BCIS)',
        'role': 'Online FBC, product approval, local amendments',
        'phone': '',
        'url': 'https://www.floridabuilding.org/',
        'category': 'state',
    },
    {
        'id': 'fl-fire-marshal',
        'name': 'Florida Division of State Fire Marshal',
        'role': 'State fire code; oversight of fire prevention bureaus',
        'phone': '(850) 413-2842',
        'url': 'https://www.myfloridacfo.com/division/sfm',
        'category': 'state',
    },
    {
        'id': 'dep',
        'name': 'Florida DEP — Environmental Permitting',
        'role': 'Environmental resource permits, stormwater (when not delegated)',
        'phone': '(850) 245-2118',
        'url': 'https://floridadep.gov/',
        'category': 'state',
    },
    {
        'id': 'fdot',
        'name': 'FDOT — Driveway / ROW Permits',
        'role': 'State road access, driveway connections, work in ROW',
        'phone': '',
        'url': 'https://www.fdot.gov/',
        'category': 'state',
    },
    {
        'id': 'fhud',
        'name': 'Florida Health — Septic / OSTDS',
        'role': 'On-site sewage treatment and disposal systems (county health depts implement)',
        'phone': '(850) 245-4444',
        'url': 'https://www.floridahealth.gov/environmental-health/onsite-sewage/',
        'category': 'health',
    },
]

# Major electric / gas utilities serving Florida
FLORIDA_UTILITIES = [
    {'id': 'fpl', 'name': 'Florida Power & Light (FPL)', 'type': 'electric', 'region': 'Southeast FL, East Coast, Panhandle (Gulf Power)', 'phone': '1-800-226-3547', 'url': 'https://www.fpl.com/', 'notes': 'Service connect / meter release after electrical final.'},
    {'id': 'duke-fl', 'name': 'Duke Energy Florida', 'type': 'electric', 'region': 'Central & North Florida, Tampa Bay area', 'phone': '1-800-700-8744', 'url': 'https://www.duke-energy.com/home/products/florida', 'notes': 'Construction service requests online.'},
    {'id': 'teco', 'name': 'Tampa Electric (TECO)', 'type': 'electric', 'region': 'Tampa / Hillsborough & parts of Polk, Pasco', 'phone': '1-877-588-1010', 'url': 'https://www.tampaelectric.com/', 'notes': ''},
    {'id': 'jea', 'name': 'JEA (Jacksonville Electric Authority)', 'type': 'electric_water', 'region': 'Jacksonville / Duval', 'phone': '(904) 665-6000', 'url': 'https://www.jea.com/', 'notes': 'Electric and water/wastewater.'},
    {'id': 'ouc', 'name': 'Orlando Utilities Commission (OUC)', 'type': 'electric_water', 'region': 'City of Orlando & parts of Orange', 'phone': '(407) 423-9018', 'url': 'https://www.ouc.com/', 'notes': ''},
    {'id': 'lakeland-electric', 'name': 'Lakeland Electric', 'type': 'electric', 'region': 'City of Lakeland', 'phone': '(863) 834-9535', 'url': 'https://www.lakelandelectric.com/', 'notes': ''},
    {'id': 'lcec', 'name': 'Lee County Electric Cooperative (LCEC)', 'type': 'electric', 'region': 'Lee, Collier, Charlotte, Broward areas', 'phone': '(239) 656-2300', 'url': 'https://www.lcec.net/', 'notes': ''},
    {'id': 'kua', 'name': 'Kissimmee Utility Authority', 'type': 'electric', 'region': 'Kissimmee / Osceola', 'phone': '(407) 933-9800', 'url': 'https://kua.com/', 'notes': ''},
    {'id': 'fpu', 'name': 'Florida Public Utilities', 'type': 'gas_electric', 'region': 'Northwest FL, Central FL gas', 'phone': '1-800-427-7712', 'url': 'https://fpuc.com/', 'notes': 'Natural gas service.'},
    {'id': 'peoples-gas', 'name': "TECO Peoples Gas", 'type': 'gas', 'region': 'Tampa Bay, Orlando, Jacksonville gas franchises', 'phone': '1-877-832-6747', 'url': 'https://www.peoplesgas.com/', 'notes': 'Fuel gas meter set after gas final.'},
    {'id': 'fng', 'name': 'Florida City Gas', 'type': 'gas', 'region': 'Miami-Dade, Broward, Brevard, others', 'phone': '1-888-352-5322', 'url': 'https://www.floridacitygas.com/', 'notes': ''},
    {'id': 'sec', 'name': 'Southeastern Gas (SEMCO)', 'type': 'gas', 'region': 'Parts of Central/North FL', 'phone': '', 'url': '', 'notes': 'Verify local franchise.'},
]

# Florida Water Management Districts
FLORIDA_WMD = [
    {'id': 'nwfwmd', 'name': 'Northwest Florida WMD', 'region': 'Panhandle', 'phone': '(850) 539-5999', 'url': 'https://www.nwfwater.com/'},
    {'id': 'srwmd', 'name': 'Suwannee River WMD', 'region': 'North Central FL', 'phone': '(386) 362-1001', 'url': 'https://www.mysuwanneeriver.com/'},
    {'id': 'sjrwmd', 'name': 'St. Johns River WMD', 'region': 'Northeast & Central FL', 'phone': '(904) 730-6200', 'url': 'https://www.sjrwmd.com/'},
    {'id': 'swfwmd', 'name': 'Southwest Florida WMD', 'region': 'Tampa Bay through Lee/Collier', 'phone': '(800) 423-1476', 'url': 'https://www.swfwmd.state.fl.us/'},
    {'id': 'sfwmd', 'name': 'South Florida WMD', 'region': 'SE Florida, Everglades', 'phone': '(561) 686-8800', 'url': 'https://www.sfwmd.gov/'},
]


def get_trade(key):
    return next((t for t in PERMIT_TRADES if t['key'] == key), None)


def get_fbc_template(trade_key):
    return FBC_INSPECTION_TEMPLATES.get(trade_key, [])


def all_catalog_trades():
    return list(PERMIT_TRADES)


def build_checklist_items(trade_key, jurisdiction=None):
    """Return dicts ready to become PermitInspectionItem rows."""
    templates = get_fbc_template(trade_key)
    items = []
    for t in templates:
        items.append({
            'record_kind': 'inspection',
            'trade': trade_key,
            'inspection_phase': t['phase'],
            'title': t['title'],
            'description': t.get('notes', ''),
            'fbc_reference': t.get('fbc_ref', ''),
            'status': 'Not Started',
            'jurisdiction_name': (jurisdiction or {}).get('name', ''),
            'authority_name': (jurisdiction or {}).get('building_dept', ''),
            'authority_phone': (jurisdiction or {}).get('phone', ''),
            'authority_url': (jurisdiction or {}).get('url', ''),
        })
    return items
