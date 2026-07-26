"""
Florida jurisdiction directory — all 67 counties, major cities, utilities, and state authorities.

Contact details should be verified with the jurisdiction before reliance; phone/URL may change.
Sources: Florida Association of Counties, DBPR, county building department websites.
"""

from florida_permit_catalog import (
    FLORIDA_STATE_AUTHORITIES, FLORIDA_UTILITIES, FLORIDA_WMD,
)
from florida_municipal_permit_offices import (
    FLORIDA_CITY_PERMIT_OFFICES,
    INSPECTION_SCHEDULING_OVERRIDES,
)

SCHEDULE_METHOD_LABELS = {
    'phone': 'Call to schedule inspections',
    'web': 'Schedule inspections online',
    'both': 'Call or schedule online',
}


def enrich_jurisdiction(entry, entry_type='county'):
    """Add permit office + inspection scheduling fields for workflow UI."""
    out = dict(entry)
    key = out.get('name', '')
    if entry_type == 'city' and key == 'Sarasota':
        override = INSPECTION_SCHEDULING_OVERRIDES.get('Sarasota City', {})
    else:
        override = INSPECTION_SCHEDULING_OVERRIDES.get(key, {})

    phone = out.get('inspection_phone') or override.get('inspection_phone') or out.get('phone', '')
    permit_url = out.get('permit_url') or out.get('url', '')
    inspection_url = (
        out.get('inspection_schedule_url')
        or override.get('inspection_schedule_url')
        or ''
    )

    method = out.get('schedule_method') or override.get('schedule_method')
    if not method:
        if inspection_url and phone:
            method = 'both'
        elif inspection_url:
            method = 'web'
        else:
            method = 'phone'

    instructions = out.get('schedule_instructions') or override.get('schedule_instructions')
    if not instructions:
        if method == 'phone':
            instructions = (
                f'Call {phone} during business hours to request inspections.'
                if phone else 'Contact the building department by phone to schedule inspections.'
            )
        elif method == 'web':
            instructions = (
                'Use the online inspection scheduling portal (link below).'
                if inspection_url else 'Visit the building department website to schedule inspections online.'
            )
        else:
            if phone and inspection_url:
                instructions = f'Call {phone} or use the online portal to request inspections.'
            elif phone:
                instructions = f'Call {phone} to request inspections.'
            else:
                instructions = 'Contact the permitting office to schedule inspections.'

    out.update({
        'permit_url': permit_url,
        'inspection_phone': phone,
        'inspection_schedule_url': inspection_url,
        'schedule_method': method,
        'schedule_method_label': SCHEDULE_METHOD_LABELS.get(method, method),
        'schedule_instructions': instructions,
        'type': entry_type,
    })
    return out


def jurisdiction_to_item_details(jurisdiction):
    """Map a directory entry to permit/inspection item detail fields."""
    j = enrich_jurisdiction(jurisdiction, jurisdiction.get('type', 'county'))
    return {
        'jurisdiction_name': j.get('display') or j.get('name', ''),
        'authority_name': j.get('building_dept') or j.get('name', ''),
        'authority_phone': j.get('inspection_phone') or j.get('phone', ''),
        'authority_url': j.get('permit_url') or j.get('url', ''),
        'scheduling': {
            'schedule_method': j.get('schedule_method', 'phone'),
            'schedule_method_label': j.get('schedule_method_label', ''),
            'schedule_instructions': j.get('schedule_instructions', ''),
            'inspection_phone': j.get('inspection_phone', ''),
            'inspection_schedule_url': j.get('inspection_schedule_url', ''),
            'permit_url': j.get('permit_url', ''),
        },
    }

# All 67 Florida counties — county seat + building/permitting contact
FLORIDA_COUNTIES = [
    {'name': 'Alachua', 'seat': 'Gainesville', 'building_dept': 'Alachua County Growth Management / City of Gainesville', 'phone': '(352) 374-5249', 'url': 'https://www.alachuacounty.us/', 'notes': 'Gainesville has separate city building dept.'},
    {'name': 'Baker', 'seat': 'Macclenny', 'building_dept': 'Baker County Building Department', 'phone': '(904) 259-3613', 'url': 'https://www.bakercountyfl.org/', 'notes': ''},
    {'name': 'Bay', 'seat': 'Panama City', 'building_dept': 'Bay County Building Safety Division', 'phone': '(850) 248-8350', 'url': 'https://www.baycountyfl.gov/', 'notes': 'Publishes FBC minimum required inspections guide.'},
    {'name': 'Bradford', 'seat': 'Starke', 'building_dept': 'Bradford County Building Department', 'phone': '(904) 966-6220', 'url': 'https://www.bradfordcountyfl.gov/', 'notes': ''},
    {'name': 'Brevard', 'seat': 'Titusville', 'building_dept': 'Brevard County Planning & Development', 'phone': '(321) 633-2072', 'url': 'https://www.brevardfl.gov/', 'notes': 'Cities: Melbourne, Cocoa, Palm Bay have own depts.'},
    {'name': 'Broward', 'seat': 'Fort Lauderdale', 'building_dept': 'Broward County Building Code Services', 'phone': '(954) 765-4400', 'url': 'https://www.broward.org/Building/', 'notes': 'Many municipalities have separate building departments.'},
    {'name': 'Calhoun', 'seat': 'Blountstown', 'building_dept': 'Calhoun County Building Department', 'phone': '(850) 674-4545', 'url': 'https://www.calhouncountyfl.org/', 'notes': ''},
    {'name': 'Charlotte', 'seat': 'Punta Gorda', 'building_dept': 'Charlotte County Community Development', 'phone': '(941) 743-1201', 'url': 'https://www.charlottecountyfl.gov/', 'notes': ''},
    {'name': 'Citrus', 'seat': 'Inverness', 'building_dept': 'Citrus County Building Division', 'phone': '(352) 527-5310', 'url': 'https://www.citrusbocc.com/', 'notes': ''},
    {'name': 'Clay', 'seat': 'Green Cove Springs', 'building_dept': 'Clay County Building Department', 'phone': '(904) 269-6300', 'url': 'https://www.claycountygov.com/', 'notes': 'Orange Park / Middleburg area.'},
    {'name': 'Collier', 'seat': 'East Naples', 'building_dept': 'Collier County Growth Management', 'phone': '(239) 252-2400', 'url': 'https://www.colliercountyfl.gov/', 'notes': 'Naples / Marco Island have city depts.'},
    {'name': 'Columbia', 'seat': 'Lake City', 'building_dept': 'Columbia County Building Department', 'phone': '(386) 758-1025', 'url': 'https://www.columbiacountyfla.com/', 'notes': ''},
    {'name': 'DeSoto', 'seat': 'Arcadia', 'building_dept': 'DeSoto County Building Department', 'phone': '(863) 993-4800', 'url': 'https://www.desotobocc.com/', 'notes': ''},
    {'name': 'Dixie', 'seat': 'Cross City', 'building_dept': 'Dixie County Building Department', 'phone': '(352) 498-1200', 'url': 'https://www.dixiecogov.com/', 'notes': ''},
    {'name': 'Duval', 'seat': 'Jacksonville', 'building_dept': 'City of Jacksonville — Building Inspection Division', 'phone': '(904) 255-8500', 'url': 'https://www.coj.net/departments/planning-and-development/building-inspection', 'notes': 'Consolidated city-county; Duval has no separate county building dept.'},
    {'name': 'Escambia', 'seat': 'Pensacola', 'building_dept': 'Escambia County Development Services', 'phone': '(850) 595-3520', 'url': 'https://myescambia.com/', 'notes': 'City of Pensacola separate AHJ for city limits.'},
    {'name': 'Flagler', 'seat': 'Bunnell', 'building_dept': 'Flagler County Growth Management', 'phone': '(386) 313-4000', 'url': 'https://www.flaglercounty.gov/', 'notes': ''},
    {'name': 'Franklin', 'seat': 'Apalachicola', 'building_dept': 'Franklin County Building Department', 'phone': '(850) 653-9783', 'url': 'https://www.franklincountyflorida.com/', 'notes': ''},
    {'name': 'Gadsden', 'seat': 'Quincy', 'building_dept': 'Gadsden County Building Department', 'phone': '(850) 627-7651', 'url': 'https://www.gadcoclerk.com/', 'notes': ''},
    {'name': 'Gilchrist', 'seat': 'Trenton', 'building_dept': 'Gilchrist County Building Department', 'phone': '(352) 463-3176', 'url': 'https://www.gilchrist.fl.us/', 'notes': ''},
    {'name': 'Glades', 'seat': 'Moore Haven', 'building_dept': 'Glades County Building Department', 'phone': '(863) 946-6012', 'url': 'https://www.myglades.com/', 'notes': ''},
    {'name': 'Gulf', 'seat': 'Port St. Joe', 'building_dept': 'Gulf County Building Department', 'phone': '(850) 229-6114', 'url': 'https://www.gulfcounty-fl.gov/', 'notes': ''},
    {'name': 'Hamilton', 'seat': 'Jasper', 'building_dept': 'Hamilton County Building Department', 'phone': '(386) 792-1280', 'url': 'https://www.hamiltoncountyfl.com/', 'notes': ''},
    {'name': 'Hardee', 'seat': 'Wauchula', 'building_dept': 'Hardee County Building Department', 'phone': '(863) 773-3236', 'url': 'https://www.hardeecountyfl.gov/', 'notes': ''},
    {'name': 'Hendry', 'seat': 'LaBelle', 'building_dept': 'Hendry County Building Department', 'phone': '(863) 675-5247', 'url': 'https://www.hendryfla.net/', 'notes': ''},
    {'name': 'Hernando', 'seat': 'Brooksville', 'building_dept': 'Hernando County Building Department', 'phone': '(352) 754-4050', 'url': 'https://www.hernandocounty.us/', 'notes': ''},
    {'name': 'Highlands', 'seat': 'Sebring', 'building_dept': 'Highlands County Building Department', 'phone': '(863) 402-6641', 'url': 'https://www.hcbcc.net/', 'notes': ''},
    {'name': 'Hillsborough', 'seat': 'Tampa', 'building_dept': 'Hillsborough County Construction Services / City of Tampa', 'phone': '(813) 272-5600', 'url': 'https://www.hillsboroughcounty.org/', 'notes': 'Tampa, Temple Terrace, Plant City have city AHJs.'},
    {'name': 'Holmes', 'seat': 'Bonifay', 'building_dept': 'Holmes County Building Department', 'phone': '(850) 547-1111', 'url': 'https://www.holmescountyfl.org/', 'notes': ''},
    {'name': 'Indian River', 'seat': 'Vero Beach', 'building_dept': 'Indian River County Building Division', 'phone': '(772) 226-1260', 'url': 'https://www.indianriver.gov/', 'notes': ''},
    {'name': 'Jackson', 'seat': 'Marianna', 'building_dept': 'Jackson County Building Department', 'phone': '(850) 482-9633', 'url': 'https://www.jacksoncountyfl.com/', 'notes': ''},
    {'name': 'Jefferson', 'seat': 'Monticello', 'building_dept': 'Jefferson County Building Department', 'phone': '(850) 342-0218', 'url': 'https://www.jeffersoncountyfl.gov/', 'notes': ''},
    {'name': 'Lafayette', 'seat': 'Mayo', 'building_dept': 'Lafayette County Building Department', 'phone': '(386) 294-1600', 'url': 'https://www.lafayettecountyfl.org/', 'notes': ''},
    {'name': 'Lake', 'seat': 'Tavares', 'building_dept': 'Lake County Building Services', 'phone': '(352) 343-9739', 'url': 'https://www.lakecountyfl.gov/', 'notes': ''},
    {'name': 'Lee', 'seat': 'Fort Myers', 'building_dept': 'Lee County Community Development', 'phone': '(239) 533-8945', 'url': 'https://www.leegov.com/', 'notes': 'Cape Coral, Fort Myers city depts in city limits.'},
    {'name': 'Leon', 'seat': 'Tallahassee', 'building_dept': 'Leon County Development Support / City of Tallahassee', 'phone': '(850) 606-1300', 'url': 'https://www.leoncountyfl.gov/', 'notes': ''},
    {'name': 'Levy', 'seat': 'Bronson', 'building_dept': 'Levy County Building Department', 'phone': '(352) 486-5266', 'url': 'https://www.levycounty.org/', 'notes': ''},
    {'name': 'Liberty', 'seat': 'Bristol', 'building_dept': 'Liberty County Building Department', 'phone': '(850) 643-2215', 'url': 'https://www.libertycountyflorida.com/', 'notes': ''},
    {'name': 'Madison', 'seat': 'Madison', 'building_dept': 'Madison County Building Department', 'phone': '(850) 973-3176', 'url': 'https://www.madisoncountyfl.com/', 'notes': ''},
    {'name': 'Manatee', 'seat': 'Bradenton', 'building_dept': 'Manatee County Building & Development Services', 'phone': '(941) 748-4501', 'url': 'https://www.mymanatee.org/', 'notes': ''},
    {'name': 'Marion', 'seat': 'Ocala', 'building_dept': 'Marion County Growth Services', 'phone': '(352) 438-2400', 'url': 'https://www.marioncountyfl.org/', 'notes': 'Ocala city AHJ in city limits.'},
    {'name': 'Martin', 'seat': 'Stuart', 'building_dept': 'Martin County Growth Management', 'phone': '(772) 288-5500', 'url': 'https://www.martin.fl.us/', 'notes': ''},
    {'name': 'Miami-Dade', 'seat': 'Miami', 'building_dept': 'Miami-Dade County Regulatory & Economic Resources', 'phone': '(786) 315-2590', 'url': 'https://www.miamidade.gov/permits/', 'notes': 'Largest FL jurisdiction; many municipalities have own depts.'},
    {'name': 'Monroe', 'seat': 'Key West', 'building_dept': 'Monroe County Building Department', 'phone': '(305) 289-2501', 'url': 'https://www.monroecounty-fl.gov/', 'notes': 'Keys — flood/elevation certs critical.'},
    {'name': 'Nassau', 'seat': 'Fernandina Beach', 'building_dept': 'Nassau County Building Department', 'phone': '(904) 530-6300', 'url': 'https://www.nassaucountyfl.com/', 'notes': ''},
    {'name': 'Okaloosa', 'seat': 'Crestview', 'building_dept': 'Okaloosa County Growth Management', 'phone': '(850) 689-5772', 'url': 'https://www.myokaloosa.com/', 'notes': 'Fort Walton Beach, Destin may have city depts.'},
    {'name': 'Okeechobee', 'seat': 'Okeechobee', 'building_dept': 'Okeechobee County Building Department', 'phone': '(863) 763-5548', 'url': 'https://www.okeechobeecountyfl.gov/', 'notes': ''},
    {'name': 'Orange', 'seat': 'Orlando', 'building_dept': 'Orange County Division of Building Safety', 'phone': '(407) 836-5520', 'url': 'https://www.orangecountyfl.net/PermitsLicenses/DivisionOfBuildingSafety.aspx', 'notes': 'Orlando, Winter Park, Apopka have city AHJs.'},
    {'name': 'Osceola', 'seat': 'Kissimmee', 'building_dept': 'Osceola County Permitting Services', 'phone': '(407) 742-0200', 'url': 'https://www.osceola.org/', 'notes': 'Kissimmee city AHJ in city limits.'},
    {'name': 'Palm Beach', 'seat': 'West Palm Beach', 'building_dept': 'Palm Beach County Planning, Zoning & Building', 'phone': '(561) 233-5000', 'url': 'https://www.pbcgov.org/pzb/', 'notes': 'Many coastal cities have separate depts.'},
    {'name': 'Pasco', 'seat': 'Dade City', 'building_dept': 'Pasco County Building Construction Services', 'phone': '(727) 847-8128', 'url': 'https://www.pascocountyfl.net/', 'notes': ''},
    {'name': 'Pinellas', 'seat': 'Clearwater', 'building_dept': 'Pinellas County Building & Development Review Services', 'phone': '(727) 464-3888', 'url': 'https://www.pinellas.gov/', 'notes': 'St. Pete, Clearwater, Largo have city depts.'},
    {'name': 'Polk', 'seat': 'Bartow', 'building_dept': 'Polk County Building Division', 'phone': '(863) 534-6082', 'url': 'https://www.polk-county.net/', 'notes': 'Lakeland, Winter Haven city AHJs.'},
    {'name': 'Putnam', 'seat': 'Palatka', 'building_dept': 'Putnam County Building Department', 'phone': '(386) 329-0300', 'url': 'https://www.putnam-fl.com/', 'notes': ''},
    {'name': 'Santa Rosa', 'seat': 'Milton', 'building_dept': 'Santa Rosa County Building Department', 'phone': '(850) 981-7000', 'url': 'https://www.santarosa.fl.gov/', 'notes': ''},
    {'name': 'Sarasota', 'seat': 'Sarasota', 'building_dept': 'Sarasota County Planning & Development Services', 'phone': '(941) 861-5000', 'url': 'https://www.scgov.net/', 'notes': 'City of Sarasota separate AHJ.'},
    {'name': 'Seminole', 'seat': 'Sanford', 'building_dept': 'Seminole County Building Division', 'phone': '(407) 665-7050', 'url': 'https://www.seminolecountyfl.gov/', 'notes': ''},
    {'name': 'St. Johns', 'seat': 'St. Augustine', 'building_dept': 'St. Johns County Building Services', 'phone': '(904) 827-6800', 'url': 'https://www.sjcfl.us/', 'notes': ''},
    {'name': 'St. Lucie', 'seat': 'Fort Pierce', 'building_dept': 'St. Lucie County Building Department', 'phone': '(772) 462-1553', 'url': 'https://www.stlucieco.gov/', 'notes': 'Port St. Lucie city AHJ.'},
    {'name': 'Sumter', 'seat': 'Bushnell', 'building_dept': 'Sumter County Building Department', 'phone': '(352) 689-4400', 'url': 'https://www.sumtercountyfl.gov/', 'notes': 'The Villages area — verify jurisdiction.'},
    {'name': 'Suwannee', 'seat': 'Live Oak', 'building_dept': 'Suwannee County Building Department', 'phone': '(386) 362-0520', 'url': 'https://www.suwanneecounty.org/', 'notes': ''},
    {'name': 'Taylor', 'seat': 'Perry', 'building_dept': 'Taylor County Building Department', 'phone': '(850) 838-3500', 'url': 'https://www.taylorcountygov.com/', 'notes': ''},
    {'name': 'Union', 'seat': 'Lake Butler', 'building_dept': 'Union County Building Department', 'phone': '(386) 496-2676', 'url': 'https://www.unioncountyfl.gov/', 'notes': ''},
    {'name': 'Volusia', 'seat': 'DeLand', 'building_dept': 'Volusia County Growth and Resource Management', 'phone': '(386) 736-5929', 'url': 'https://www.volusia.org/', 'notes': 'Daytona Beach, Deltona city depts.'},
    {'name': 'Wakulla', 'seat': 'Crawfordville', 'building_dept': 'Wakulla County Building Department', 'phone': '(850) 926-3695', 'url': 'https://www.wakullacounty.gov/', 'notes': ''},
    {'name': 'Walton', 'seat': 'DeFuniak Springs', 'building_dept': 'Walton County Building Department', 'phone': '(850) 892-8160', 'url': 'https://www.co.walton.fl.us/', 'notes': ''},
    {'name': 'Washington', 'seat': 'Chipley', 'building_dept': 'Washington County Building Department', 'phone': '(850) 638-6240', 'url': 'https://www.washingtonfl.com/', 'notes': ''},
]

# Major Florida cities with independent building departments (in addition to county)
FLORIDA_MAJOR_CITIES = FLORIDA_CITY_PERMIT_OFFICES


def search_directory(query='', category='all'):
    """Search counties, cities, utilities, state authorities."""
    q = (query or '').strip().lower()
    results = []

    def match(text):
        return not q or q in (text or '').lower()

    if category in ('all', 'county'):
        for c in FLORIDA_COUNTIES:
            blob = f"{c['name']} {c['seat']} {c['building_dept']}"
            if match(blob):
                row = enrich_jurisdiction({**c, 'type': 'county', 'display': f"{c['name']} County — {c['seat']}"}, 'county')
                results.append(row)
    if category in ('all', 'city'):
        for c in FLORIDA_MAJOR_CITIES:
            blob = f"{c['name']} {c['county']} {c['building_dept']}"
            if match(blob):
                row = enrich_jurisdiction({**c, 'type': 'city', 'display': f"{c['name']} ({c['county']} Co.)"}, 'city')
                results.append(row)
    if category in ('all', 'utility'):
        for u in FLORIDA_UTILITIES:
            if match(f"{u['name']} {u['region']} {u['type']}"):
                results.append(enrich_jurisdiction({**u, 'type': 'utility', 'display': u['name']}, 'utility'))
    if category in ('all', 'state'):
        for a in FLORIDA_STATE_AUTHORITIES:
            if match(f"{a['name']} {a['role']}"):
                results.append(enrich_jurisdiction({**a, 'type': 'state', 'display': a['name']}, 'state'))
    if category in ('all', 'water_management'):
        for w in FLORIDA_WMD:
            if match(f"{w['name']} {w['region']}"):
                results.append(enrich_jurisdiction({**w, 'type': 'water_management', 'display': w['name']}, 'water_management'))
    return results


def get_full_directory():
    counties = [enrich_jurisdiction({**c, 'display': f"{c['name']} County — {c['seat']}"}, 'county') for c in FLORIDA_COUNTIES]
    cities = [enrich_jurisdiction({**c, 'display': f"{c['name']} ({c['county']} Co.)"}, 'city') for c in FLORIDA_MAJOR_CITIES]
    return {
        'counties': counties,
        'cities': cities,
        'utilities': FLORIDA_UTILITIES,
        'state_authorities': FLORIDA_STATE_AUTHORITIES,
        'water_management_districts': FLORIDA_WMD,
        'county_count': len(FLORIDA_COUNTIES),
        'city_count': len(FLORIDA_MAJOR_CITIES),
        'schedule_method_labels': SCHEDULE_METHOD_LABELS,
    }
