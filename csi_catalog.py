"""CSI MasterFormat divisions and major spec sections for estimating / RFP matching."""
from __future__ import annotations

CSI_DIVISIONS = [
    ('00', 'Procurement and Contracting Requirements'),
    ('01', 'General Requirements'),
    ('02', 'Existing Conditions'),
    ('03', 'Concrete'),
    ('04', 'Masonry'),
    ('05', 'Metals'),
    ('06', 'Wood, Plastics, and Composites'),
    ('07', 'Thermal and Moisture Protection'),
    ('08', 'Openings'),
    ('09', 'Finishes'),
    ('10', 'Specialties'),
    ('11', 'Equipment'),
    ('12', 'Furnishings'),
    ('13', 'Special Construction'),
    ('14', 'Conveying Equipment'),
    ('21', 'Fire Suppression'),
    ('22', 'Plumbing'),
    ('23', 'HVAC'),
    ('25', 'Integrated Automation'),
    ('26', 'Electrical'),
    ('27', 'Communications'),
    ('28', 'Electronic Safety and Security'),
    ('31', 'Earthwork'),
    ('32', 'Exterior Improvements'),
    ('33', 'Utilities'),
]

# Major bid-package spec sections (MasterFormat-style)
CSI_SPEC_SECTIONS = [
    # 00
    {'division': '00', 'code': '00 11 00', 'title': 'Advertisement for Bids'},
    {'division': '00', 'code': '00 31 00', 'title': 'Available Project Information'},
    # 01
    {'division': '01', 'code': '01 10 00', 'title': 'Summary of Work'},
    {'division': '01', 'code': '01 25 00', 'title': 'Substitution Procedures'},
    {'division': '01', 'code': '01 29 00', 'title': 'Payment Procedures'},
    {'division': '01', 'code': '01 32 00', 'title': 'Construction Progress Documentation'},
    {'division': '01', 'code': '01 45 00', 'title': 'Quality Control'},
    {'division': '01', 'code': '01 50 00', 'title': 'Temporary Facilities and Controls'},
    {'division': '01', 'code': '01 74 00', 'title': 'Cleaning and Waste Management'},
    # 02
    {'division': '02', 'code': '02 41 00', 'title': 'Demolition'},
    {'division': '02', 'code': '02 82 00', 'title': 'Asbestos Remediation'},
    # 03
    {'division': '03', 'code': '03 10 00', 'title': 'Concrete Forming and Accessories'},
    {'division': '03', 'code': '03 20 00', 'title': 'Concrete Reinforcing'},
    {'division': '03', 'code': '03 30 00', 'title': 'Cast-in-Place Concrete'},
    {'division': '03', 'code': '03 40 00', 'title': 'Precast Concrete'},
    {'division': '03', 'code': '03 50 00', 'title': 'Cast Decks and Underlayment'},
    # 04
    {'division': '04', 'code': '04 20 00', 'title': 'Unit Masonry'},
    {'division': '04', 'code': '04 40 00', 'title': 'Stone Assemblies'},
    # 05
    {'division': '05', 'code': '05 12 00', 'title': 'Structural Steel Framing'},
    {'division': '05', 'code': '05 21 00', 'title': 'Steel Joist Framing'},
    {'division': '05', 'code': '05 31 00', 'title': 'Steel Decking'},
    {'division': '05', 'code': '05 50 00', 'title': 'Metal Fabrications'},
    # 06
    {'division': '06', 'code': '06 10 00', 'title': 'Rough Carpentry'},
    {'division': '06', 'code': '06 20 00', 'title': 'Finish Carpentry'},
    {'division': '06', 'code': '06 40 00', 'title': 'Architectural Woodwork'},
    # 07
    {'division': '07', 'code': '07 10 00', 'title': 'Dampproofing and Waterproofing'},
    {'division': '07', 'code': '07 21 00', 'title': 'Thermal Insulation'},
    {'division': '07', 'code': '07 25 00', 'title': 'Weather Barriers'},
    {'division': '07', 'code': '07 42 00', 'title': 'Wall Panels'},
    {'division': '07', 'code': '07 50 00', 'title': 'Membrane Roofing'},
    {'division': '07', 'code': '07 62 00', 'title': 'Sheet Metal Flashing and Trim'},
    {'division': '07', 'code': '07 92 00', 'title': 'Joint Sealants'},
    # 08
    {'division': '08', 'code': '08 11 00', 'title': 'Metal Doors and Frames'},
    {'division': '08', 'code': '08 14 00', 'title': 'Wood Doors'},
    {'division': '08', 'code': '08 31 00', 'title': 'Access Doors and Panels'},
    {'division': '08', 'code': '08 41 00', 'title': 'Aluminum-Framed Entrances and Storefronts'},
    {'division': '08', 'code': '08 44 00', 'title': 'Curtain Wall and Glazed Assemblies'},
    {'division': '08', 'code': '08 51 00', 'title': 'Metal Windows'},
    {'division': '08', 'code': '08 71 00', 'title': 'Door Hardware'},
    {'division': '08', 'code': '08 80 00', 'title': 'Glazing'},
    # 09
    {'division': '09', 'code': '09 21 00', 'title': 'Plaster and Gypsum Board Assemblies'},
    {'division': '09', 'code': '09 22 00', 'title': 'Supports for Plaster and Gypsum Board'},
    {'division': '09', 'code': '09 29 00', 'title': 'Gypsum Board'},
    {'division': '09', 'code': '09 30 00', 'title': 'Tiling'},
    {'division': '09', 'code': '09 51 00', 'title': 'Acoustical Ceilings'},
    {'division': '09', 'code': '09 65 00', 'title': 'Resilient Flooring'},
    {'division': '09', 'code': '09 68 00', 'title': 'Carpeting'},
    {'division': '09', 'code': '09 91 00', 'title': 'Painting'},
    # 10
    {'division': '10', 'code': '10 14 00', 'title': 'Signage'},
    {'division': '10', 'code': '10 21 00', 'title': 'Compartments and Cubicles'},
    {'division': '10', 'code': '10 28 00', 'title': 'Toilet, Bath, and Laundry Accessories'},
    # 11
    {'division': '11', 'code': '11 13 00', 'title': 'Loading Dock Equipment'},
    {'division': '11', 'code': '11 40 00', 'title': 'Food Service Equipment'},
    # 12
    {'division': '12', 'code': '12 24 00', 'title': 'Window Shades'},
    {'division': '12', 'code': '12 36 00', 'title': 'Countertops'},
    # 13
    {'division': '13', 'code': '13 34 00', 'title': 'Fabricated Engineered Structures'},
    # 14
    {'division': '14', 'code': '14 20 00', 'title': 'Elevators'},
    # 21
    {'division': '21', 'code': '21 05 00', 'title': 'Common Work Results for Fire Suppression'},
    {'division': '21', 'code': '21 13 00', 'title': 'Fire-Suppression Sprinkler Systems'},
    # 22
    {'division': '22', 'code': '22 05 00', 'title': 'Common Work Results for Plumbing'},
    {'division': '22', 'code': '22 11 00', 'title': 'Facility Water Distribution'},
    {'division': '22', 'code': '22 13 00', 'title': 'Facility Sanitary Sewerage'},
    {'division': '22', 'code': '22 40 00', 'title': 'Plumbing Fixtures'},
    # 23
    {'division': '23', 'code': '23 05 00', 'title': 'Common Work Results for HVAC'},
    {'division': '23', 'code': '23 07 00', 'title': 'HVAC Insulation'},
    {'division': '23', 'code': '23 21 00', 'title': 'Hydronic Piping and Pumps'},
    {'division': '23', 'code': '23 34 00', 'title': 'HVAC Fans'},
    {'division': '23', 'code': '23 81 00', 'title': 'Decentralized Unitary HVAC Equipment'},
    # 26
    {'division': '26', 'code': '26 05 00', 'title': 'Common Work Results for Electrical'},
    {'division': '26', 'code': '26 09 00', 'title': 'Instrumentation and Control for Electrical Systems'},
    {'division': '26', 'code': '26 24 00', 'title': 'Switchboards and Panelboards'},
    {'division': '26', 'code': '26 27 00', 'title': 'Low-Voltage Distribution Equipment'},
    {'division': '26', 'code': '26 51 00', 'title': 'Interior Lighting'},
    # 27
    {'division': '27', 'code': '27 10 00', 'title': 'Structured Cabling'},
    {'division': '27', 'code': '27 40 00', 'title': 'Audio-Video Systems'},
    # 28
    {'division': '28', 'code': '28 31 00', 'title': 'Fire Detection and Alarm'},
    # 31
    {'division': '31', 'code': '31 20 00', 'title': 'Earth Moving'},
    {'division': '31', 'code': '31 23 00', 'title': 'Excavation and Fill'},
    # 32
    {'division': '32', 'code': '32 12 00', 'title': 'Flexible Paving'},
    {'division': '32', 'code': '32 31 00', 'title': 'Fences and Gates'},
    {'division': '32', 'code': '32 90 00', 'title': 'Planting'},
    # 33
    {'division': '33', 'code': '33 05 00', 'title': 'Common Work Results for Utilities'},
    {'division': '33', 'code': '33 41 00', 'title': 'Storm Utility Drainage Piping'},
]


def normalize_spec_code(code):
    return (code or '').replace(' ', '').upper()


def catalog_payload():
    divisions = [{'code': d[0], 'name': d[1]} for d in CSI_DIVISIONS]
    sections = []
    for row in CSI_SPEC_SECTIONS:
        sections.append({
            'division': row['division'],
            'code': row['code'],
            'title': row['title'],
            'label': f"{row['code']} — {row['title']}",
        })
    return {'divisions': divisions, 'spec_sections': sections}


def sections_for_division(division_code):
    div = str(division_code or '').strip().zfill(2)[:2]
    return [s for s in CSI_SPEC_SECTIONS if s['division'] == div]
