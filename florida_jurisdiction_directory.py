"""
Florida jurisdiction directory — all 67 counties, major cities, utilities, and state authorities.

Contact details should be verified with the jurisdiction before reliance; phone/URL may change.
Sources: Florida Association of Counties, DBPR, county building department websites.
"""

from florida_permit_catalog import (
    FLORIDA_STATE_AUTHORITIES, FLORIDA_UTILITIES, FLORIDA_WMD,
)

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
FLORIDA_MAJOR_CITIES = [
    {'name': 'Jacksonville', 'county': 'Duval', 'building_dept': 'Jacksonville Building Inspection Division', 'phone': '(904) 255-8500', 'url': 'https://www.coj.net/departments/planning-and-development/building-inspection'},
    {'name': 'Miami', 'county': 'Miami-Dade', 'building_dept': 'City of Miami Building Department', 'phone': '(305) 416-2060', 'url': 'https://www.miami.gov/Building'},
    {'name': 'Tampa', 'county': 'Hillsborough', 'building_dept': 'City of Tampa Construction Services Center', 'phone': '(813) 274-3100', 'url': 'https://www.tampa.gov/construction-services'},
    {'name': 'Orlando', 'county': 'Orange', 'building_dept': 'City of Orlando Permitting Services', 'phone': '(407) 246-4444', 'url': 'https://www.orlando.gov/Building-Development'},
    {'name': 'St. Petersburg', 'county': 'Pinellas', 'building_dept': 'St. Petersburg Development Services', 'phone': '(727) 893-7231', 'url': 'https://www.stpete.org/'},
    {'name': 'Hialeah', 'county': 'Miami-Dade', 'building_dept': 'Hialeah Building Department', 'phone': '(305) 883-5800', 'url': 'https://www.hialeahfl.gov/'},
    {'name': 'Fort Lauderdale', 'county': 'Broward', 'building_dept': 'Fort Lauderdale Building Services', 'phone': '(954) 828-6520', 'url': 'https://www.fortlauderdale.gov/'},
    {'name': 'Cape Coral', 'county': 'Lee', 'building_dept': 'Cape Coral Building Development Services', 'phone': '(239) 574-0546', 'url': 'https://www.capecoral.gov/'},
    {'name': 'Tallahassee', 'county': 'Leon', 'building_dept': 'Tallahassee Building Inspection', 'phone': '(850) 891-7000', 'url': 'https://www.talgov.com/'},
    {'name': 'Hollywood', 'county': 'Broward', 'building_dept': 'Hollywood Building Division', 'phone': '(954) 921-3335', 'url': 'https://www.hollywoodfl.org/'},
    {'name': 'Gainesville', 'county': 'Alachua', 'building_dept': 'Gainesville Building Inspection', 'phone': '(352) 334-5050', 'url': 'https://www.gainesvillefl.gov/'},
    {'name': 'Pembroke Pines', 'county': 'Broward', 'building_dept': 'Pembroke Pines Building & Permitting', 'phone': '(954) 431-4500', 'url': 'https://www.ppines.com/'},
    {'name': 'Clearwater', 'county': 'Pinellas', 'building_dept': 'Clearwater Development Services', 'phone': '(727) 562-4740', 'url': 'https://www.myclearwater.com/'},
    {'name': 'Lakeland', 'county': 'Polk', 'building_dept': 'Lakeland Building Inspection', 'phone': '(863) 834-6012', 'url': 'https://www.lakelandgov.net/'},
    {'name': 'Palm Bay', 'county': 'Brevard', 'building_dept': 'Palm Bay Building Department', 'phone': '(321) 953-8924', 'url': 'https://www.palmbayfl.gov/'},
    {'name': 'West Palm Beach', 'county': 'Palm Beach', 'building_dept': 'West Palm Beach Development Services', 'phone': '(561) 822-2200', 'url': 'https://www.wpb.org/'},
    {'name': 'Port St. Lucie', 'county': 'St. Lucie', 'building_dept': 'Port St. Lucie Building Department', 'phone': '(772) 871-5132', 'url': 'https://www.cityofpsl.com/'},
    {'name': 'Boca Raton', 'county': 'Palm Beach', 'building_dept': 'Boca Raton Building Services', 'phone': '(561) 393-7960', 'url': 'https://www.myboca.us/'},
    {'name': 'Daytona Beach', 'county': 'Volusia', 'building_dept': 'Daytona Beach Building Division', 'phone': '(386) 671-8140', 'url': 'https://www.codb.us/'},
    {'name': 'Kissimmee', 'county': 'Osceola', 'building_dept': 'Kissimmee Building & Permitting', 'phone': '(407) 518-2120', 'url': 'https://www.kissimmee.gov/'},
]


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
                results.append({**c, 'type': 'county', 'display': f"{c['name']} County — {c['seat']}"})
    if category in ('all', 'city'):
        for c in FLORIDA_MAJOR_CITIES:
            blob = f"{c['name']} {c['county']} {c['building_dept']}"
            if match(blob):
                results.append({**c, 'type': 'city', 'display': f"{c['name']} ({c['county']} Co.)"})
    if category in ('all', 'utility'):
        for u in FLORIDA_UTILITIES:
            if match(f"{u['name']} {u['region']} {u['type']}"):
                results.append({**u, 'type': 'utility', 'display': u['name']})
    if category in ('all', 'state'):
        for a in FLORIDA_STATE_AUTHORITIES:
            if match(f"{a['name']} {a['role']}"):
                results.append({**a, 'type': 'state', 'display': a['name']})
    if category in ('all', 'water_management'):
        for w in FLORIDA_WMD:
            if match(f"{w['name']} {w['region']}"):
                results.append({**w, 'type': 'water_management', 'display': w['name']})
    return results


def get_full_directory():
    return {
        'counties': FLORIDA_COUNTIES,
        'cities': FLORIDA_MAJOR_CITIES,
        'utilities': FLORIDA_UTILITIES,
        'state_authorities': FLORIDA_STATE_AUTHORITIES,
        'water_management_districts': FLORIDA_WMD,
        'county_count': len(FLORIDA_COUNTIES),
    }
