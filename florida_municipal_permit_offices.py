"""
Florida municipal building departments and inspection scheduling contacts.

Most field inspections are performed by the local city or county AHJ. Entries include
how to request inspections (phone, web portal, or both). Verify numbers and URLs with
the jurisdiction before reliance — contact details change.
"""

# schedule_method: phone | web | both
INSPECTION_SCHEDULING_OVERRIDES = {
  # ── Major counties ──────────────────────────────────────────────────────────
  'Miami-Dade': {
    'inspection_schedule_url': 'https://www.miamidade.gov/permits/',
    'schedule_method': 'both',
    'schedule_instructions': 'Request inspections online through the Miami-Dade permit portal or call (786) 315-2590.',
  },
  'Broward': {
    'inspection_schedule_url': 'https://www.broward.org/Building/Pages/default.aspx',
    'schedule_method': 'both',
    'schedule_instructions': 'Schedule inspections online via Broward County ePermits or call (954) 765-4400.',
  },
  'Hillsborough': {
    'inspection_schedule_url': 'https://www.hillsboroughcounty.org/en/residents/property-owners-and-renters/building-and-development/inspections',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated Hillsborough: schedule online or call (813) 272-5600. City limits may use city AHJ (Tampa, Plant City, Temple Terrace).',
  },
  'Orange': {
    'inspection_schedule_url': 'https://www.orangecountyfl.net/PermitsLicenses/DivisionOfBuildingSafety.aspx',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated Orange County: schedule online or call (407) 836-5520. Orlando, Winter Park, and Apopka have separate city departments.',
  },
  'Pinellas': {
    'inspection_schedule_url': 'https://www.pinellas.gov/departments/building-and-development-review-services/',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated Pinellas: online portal or (727) 464-3888. St. Petersburg, Clearwater, and Largo use city AHJs.',
  },
  'Duval': {
    'inspection_schedule_url': 'https://www.coj.net/departments/planning-and-development/building-inspection',
    'schedule_method': 'both',
    'schedule_instructions': 'Jacksonville consolidated city-county: schedule online or call (904) 255-8500.',
  },
  'Palm Beach': {
    'inspection_schedule_url': 'https://www.pbcgov.org/pzb/',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated Palm Beach County: online or (561) 233-5000. Many coastal cities have separate building departments.',
  },
  'Lee': {
    'inspection_schedule_url': 'https://www.leegov.com/government/departments/community-development',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated Lee County: online or (239) 533-8945. Cape Coral and Fort Myers city limits use city AHJs.',
  },
  'Polk': {
    'inspection_schedule_url': 'https://www.polk-county.net/departments/building-division',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated Polk County: call (863) 534-6082 or use the county permit portal. Lakeland and Winter Haven have city AHJs.',
  },
  'Brevard': {
    'inspection_schedule_url': 'https://www.brevardfl.gov/PlanningAndDevelopment',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated Brevard: (321) 633-2072 or online. Melbourne, Cocoa, and Palm Bay have city building departments.',
  },
  'Volusia': {
    'inspection_schedule_url': 'https://www.volusia.org/services/growth-and-resource-management/',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated Volusia: (386) 736-5929 or online. Daytona Beach and Deltona have city AHJs.',
  },
  'Seminole': {
    'inspection_schedule_url': 'https://www.seminolecountyfl.gov/departments/building-division/',
    'schedule_method': 'both',
    'schedule_instructions': 'Seminole County: call (407) 665-7050 or schedule through the county permit portal.',
  },
  'Osceola': {
    'inspection_schedule_url': 'https://www.osceola.org/agencies/permitting-services/',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated Osceola: (407) 742-0200 or online. Kissimmee city limits use the City of Kissimmee.',
  },
  'Collier': {
    'inspection_schedule_url': 'https://www.colliercountyfl.gov/government/county-departments/growth-management-division',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated Collier: (239) 252-2400 or online. Naples and Marco Island have city AHJs.',
  },
  'Sarasota': {
    'inspection_schedule_url': 'https://www.scgov.net/government/planning-and-development-services',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated Sarasota County: (941) 861-5000 or online. City of Sarasota has a separate building department.',
  },
  'Sarasota City': {
    'inspection_schedule_url': 'https://www.sarasotafl.gov/departments/planning-and-development',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Sarasota: online or call (941) 263-6413.',
  },
  'Manatee': {
    'inspection_schedule_url': 'https://www.mymanatee.org/departments/building-and-development-services',
    'schedule_method': 'both',
    'schedule_instructions': 'Manatee County: call (941) 748-4501 or use the county online permitting system.',
  },
  'Escambia': {
    'inspection_schedule_url': 'https://myescambia.com/our-services/planning-and-zoning',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated Escambia: (850) 595-3520 or online. City of Pensacola has a separate AHJ.',
  },
  'Leon': {
    'inspection_schedule_url': 'https://www.leoncountyfl.gov/departments/planning',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated Leon County: (850) 606-1300 or online. Tallahassee city limits use City of Tallahassee.',
  },
  'Alachua': {
    'inspection_schedule_url': 'https://www.alachuacounty.us/depts/css/planning_and_development/',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated Alachua County: (352) 374-5249 or online. Gainesville city limits use City of Gainesville.',
  },
  'St. Johns': {
    'inspection_schedule_url': 'https://www.sjcfl.us/departments/building-services/',
    'schedule_method': 'both',
    'schedule_instructions': 'St. Johns County: call (904) 827-6800 or schedule through the county permit portal.',
  },
  'St. Lucie': {
    'inspection_schedule_url': 'https://www.stlucieco.gov/departments-services/building',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated St. Lucie: (772) 462-1553 or online. Port St. Lucie city limits use city AHJ.',
  },
  'Marion': {
    'inspection_schedule_url': 'https://www.marioncountyfl.org/departments-agencies/department-a-g/growth-services',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated Marion: (352) 438-2400 or online. Ocala city limits use City of Ocala.',
  },
  'Lake': {
    'inspection_schedule_url': 'https://www.lakecountyfl.gov/departments/public_works/building_services/',
    'schedule_method': 'both',
    'schedule_instructions': 'Lake County: call (352) 343-9739 or use the county online permitting portal.',
  },
  'Pasco': {
    'inspection_schedule_url': 'https://www.pascocountyfl.net/377/Building-Construction-Services',
    'schedule_method': 'both',
    'schedule_instructions': 'Pasco County: (727) 847-8128 or schedule online through the county portal.',
  },
  'Hernando': {
    'inspection_schedule_url': 'https://www.hernandocounty.us/departments/building-division',
    'schedule_method': 'phone',
    'schedule_instructions': 'Call Hernando County Building at (352) 754-4050 to request inspections.',
  },
  'Bay': {
    'inspection_schedule_url': 'https://www.baycountyfl.gov/166/Building-Safety',
    'schedule_method': 'both',
    'schedule_instructions': 'Bay County: (850) 248-8350 or online. Publishes FBC minimum required inspections guide.',
  },
  'Okaloosa': {
    'inspection_schedule_url': 'https://www.myokaloosa.com/government/departments-g-z/growth-management',
    'schedule_method': 'both',
    'schedule_instructions': 'Unincorporated Okaloosa: (850) 689-5772 or online. Fort Walton Beach and Destin may have city AHJs.',
  },
  'Santa Rosa': {
    'inspection_schedule_url': 'https://www.santarosa.fl.gov/departments/building/',
    'schedule_method': 'phone',
    'schedule_instructions': 'Call Santa Rosa County Building at (850) 981-7000 to schedule inspections.',
  },
  'Monroe': {
    'inspection_schedule_url': 'https://www.monroecounty-fl.gov/142/Building',
    'schedule_method': 'both',
    'schedule_instructions': 'Monroe County (Florida Keys): (305) 289-2501 or online. Flood elevation certs are critical.',
  },
  # ── Major cities (independent AHJs) ─────────────────────────────────────────
  'Jacksonville': {
    'inspection_schedule_url': 'https://www.coj.net/departments/planning-and-development/building-inspection',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Jacksonville: schedule online or call (904) 255-8500.',
  },
  'Miami': {
    'inspection_schedule_url': 'https://www.miami.gov/Building',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Miami: online portal or call (305) 416-2060.',
  },
  'Tampa': {
    'inspection_schedule_url': 'https://www.tampa.gov/construction-services',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Tampa: schedule inspections online (Accela) or call (813) 274-3100.',
  },
  'Orlando': {
    'inspection_schedule_url': 'https://www.orlando.gov/Building-Development',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Orlando: online permitting portal or call (407) 246-4444.',
  },
  'St. Petersburg': {
    'inspection_schedule_url': 'https://www.stpete.org/business/building-permits.php',
    'schedule_method': 'both',
    'schedule_instructions': 'City of St. Petersburg: online or call (727) 893-7231.',
  },
  'Fort Lauderdale': {
    'inspection_schedule_url': 'https://www.fortlauderdale.gov/departments/sustainable-development/building-services',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Fort Lauderdale: online or call (954) 828-6520.',
  },
  'Cape Coral': {
    'inspection_schedule_url': 'https://www.capecoral.gov/department/community_development.php',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Cape Coral: online or call (239) 574-0546.',
  },
  'Tallahassee': {
    'inspection_schedule_url': 'https://www.talgov.com/permits',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Tallahassee: online or call (850) 891-7000.',
  },
  'Gainesville': {
    'inspection_schedule_url': 'https://www.gainesvillefl.gov/Government/Departments/Development-Services',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Gainesville: online or call (352) 334-5050.',
  },
  'Clearwater': {
    'inspection_schedule_url': 'https://www.myclearwater.com/government/departments/neighborhood-services-development/development-services',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Clearwater: online or call (727) 562-4740.',
  },
  'Lakeland': {
    'inspection_schedule_url': 'https://www.lakelandgov.net/department/building-inspection/',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Lakeland: online or call (863) 834-6012.',
  },
  'West Palm Beach': {
    'inspection_schedule_url': 'https://www.wpb.org/departments/development-services',
    'schedule_method': 'both',
    'schedule_instructions': 'City of West Palm Beach: online or call (561) 822-2200.',
  },
  'Port St. Lucie': {
    'inspection_schedule_url': 'https://www.cityofpsl.com/departments/building',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Port St. Lucie: online or call (772) 871-5132.',
  },
  'Daytona Beach': {
    'inspection_schedule_url': 'https://www.codb.us/departments/building-division',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Daytona Beach: online or call (386) 671-8140.',
  },
  'Kissimmee': {
    'inspection_schedule_url': 'https://www.kissimmee.gov/departments/building-permitting',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Kissimmee: online or call (407) 518-2120.',
  },
  'Pensacola': {
    'inspection_schedule_url': 'https://www.cityofpensacola.com/343/Development-Services',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Pensacola: online or call (850) 436-5500.',
  },
  'Ocala': {
    'inspection_schedule_url': 'https://www.ocalafl.org/government/city-departments-i-z/planning-inspections',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Ocala: online or call (352) 629-8400.',
  },
  'Melbourne': {
    'inspection_schedule_url': 'https://www.melbourneflorida.org/departments/development-services',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Melbourne: online or call (321) 608-7900.',
  },
  'Naples': {
    'inspection_schedule_url': 'https://www.naplesgov.com/departments/community-services/building',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Naples: online or call (239) 213-1036.',
  },
  'Plant City': {
    'inspection_schedule_url': 'https://www.plantcitygov.com/departments/building',
    'schedule_method': 'phone',
    'schedule_instructions': 'City of Plant City: call (813) 659-4200 to schedule inspections.',
  },
  'Temple Terrace': {
    'inspection_schedule_url': 'https://www.templeterrace.gov/181/Building',
    'schedule_method': 'phone',
    'schedule_instructions': 'City of Temple Terrace: call (813) 506-6480 to schedule inspections.',
  },
  'Winter Park': {
    'inspection_schedule_url': 'https://www.cityofwinterpark.org/departments/building-permits/',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Winter Park: online or call (407) 599-3237.',
  },
  'Apopka': {
    'inspection_schedule_url': 'https://www.apopka.net/departments/building',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Apopka: online or call (407) 703-1751.',
  },
  'Largo': {
    'inspection_schedule_url': 'https://www.largo.com/department/index.php?structureid=22',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Largo: online or call (727) 587-6740.',
  },
  'Winter Haven': {
    'inspection_schedule_url': 'https://www.mywinterhaven.com/departments/building',
    'schedule_method': 'phone',
    'schedule_instructions': 'City of Winter Haven: call (863) 291-5697 to schedule inspections.',
  },
  'Fort Myers': {
    'inspection_schedule_url': 'https://www.cityftmyers.com/departments/community-development/building',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Fort Myers: online or call (239) 321-7925.',
  },
  'Deltona': {
    'inspection_schedule_url': 'https://www.deltonafl.gov/departments/growth-management/building-division',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Deltona: online or call (386) 878-8100.',
  },
  'Hollywood': {
    'inspection_schedule_url': 'https://www.hollywoodfl.org/departments/building-division',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Hollywood: online or call (954) 921-3335.',
  },
  'Pembroke Pines': {
    'inspection_schedule_url': 'https://www.ppines.com/departments/building',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Pembroke Pines: online or call (954) 431-4500.',
  },
  'Coral Springs': {
    'inspection_schedule_url': 'https://www.coralsprings.gov/departments/building',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Coral Springs: online or call (954) 344-5920.',
  },
  'Boca Raton': {
    'inspection_schedule_url': 'https://www.myboca.us/departments/building-services',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Boca Raton: online or call (561) 393-7960.',
  },
  'Miami Beach': {
    'inspection_schedule_url': 'https://www.miamibeachfl.gov/city-hall/building/',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Miami Beach: online or call (305) 673-7610.',
  },
  'Hialeah': {
    'inspection_schedule_url': 'https://www.hialeahfl.gov/departments/building',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Hialeah: online or call (305) 883-5800.',
  },
  'Palm Bay': {
    'inspection_schedule_url': 'https://www.palmbayfl.gov/departments/development-services',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Palm Bay: online or call (321) 953-8924.',
  },
  'Cocoa': {
    'inspection_schedule_url': 'https://www.cocoafl.org/departments/development-services',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Cocoa: online or call (321) 433-8688.',
  },
  'Bradenton': {
    'inspection_schedule_url': 'https://www.bradenton.gov/departments/building',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Bradenton: online or call (941) 932-9400.',
  },
  'St. Augustine': {
    'inspection_schedule_url': 'https://www.citystaug.com/departments/building',
    'schedule_method': 'both',
    'schedule_instructions': 'City of St. Augustine: online or call (904) 825-1065.',
  },
  'Marco Island': {
    'inspection_schedule_url': 'https://www.cityofmarcoisland.com/departments/community-development',
    'schedule_method': 'both',
    'schedule_instructions': 'City of Marco Island: online or call (239) 389-5010.',
  },
}

# Additional Florida cities with independent building / permitting offices
FLORIDA_CITY_PERMIT_OFFICES = [
  {'name': 'Jacksonville', 'county': 'Duval', 'building_dept': 'Jacksonville Building Inspection Division', 'phone': '(904) 255-8500', 'url': 'https://www.coj.net/departments/planning-and-development/building-inspection'},
  {'name': 'Miami', 'county': 'Miami-Dade', 'building_dept': 'City of Miami Building Department', 'phone': '(305) 416-2060', 'url': 'https://www.miami.gov/Building'},
  {'name': 'Miami Beach', 'county': 'Miami-Dade', 'building_dept': 'Miami Beach Building Division', 'phone': '(305) 673-7610', 'url': 'https://www.miamibeachfl.gov/city-hall/building/'},
  {'name': 'Hialeah', 'county': 'Miami-Dade', 'building_dept': 'Hialeah Building Department', 'phone': '(305) 883-5800', 'url': 'https://www.hialeahfl.gov/departments/building'},
  {'name': 'Coral Gables', 'county': 'Miami-Dade', 'building_dept': 'Coral Gables Building Division', 'phone': '(305) 460-5086', 'url': 'https://www.coralgables.com/department/building'},
  {'name': 'Doral', 'county': 'Miami-Dade', 'building_dept': 'Doral Building Department', 'phone': '(305) 593-6700', 'url': 'https://www.cityofdoral.com/departments/building'},
  {'name': 'Homestead', 'county': 'Miami-Dade', 'building_dept': 'Homestead Building Department', 'phone': '(305) 224-4523', 'url': 'https://www.homesteadfl.gov/departments/building'},
  {'name': 'Tampa', 'county': 'Hillsborough', 'building_dept': 'City of Tampa Construction Services Center', 'phone': '(813) 274-3100', 'url': 'https://www.tampa.gov/construction-services'},
  {'name': 'Plant City', 'county': 'Hillsborough', 'building_dept': 'Plant City Building Department', 'phone': '(813) 659-4200', 'url': 'https://www.plantcitygov.com/departments/building'},
  {'name': 'Temple Terrace', 'county': 'Hillsborough', 'building_dept': 'Temple Terrace Building Department', 'phone': '(813) 506-6480', 'url': 'https://www.templeterrace.gov/181/Building'},
  {'name': 'Orlando', 'county': 'Orange', 'building_dept': 'City of Orlando Permitting Services', 'phone': '(407) 246-4444', 'url': 'https://www.orlando.gov/Building-Development'},
  {'name': 'Winter Park', 'county': 'Orange', 'building_dept': 'Winter Park Building Department', 'phone': '(407) 599-3237', 'url': 'https://www.cityofwinterpark.org/departments/building-permits/'},
  {'name': 'Apopka', 'county': 'Orange', 'building_dept': 'Apopka Building Department', 'phone': '(407) 703-1751', 'url': 'https://www.apopka.net/departments/building'},
  {'name': 'St. Petersburg', 'county': 'Pinellas', 'building_dept': 'St. Petersburg Development Services', 'phone': '(727) 893-7231', 'url': 'https://www.stpete.org/business/building-permits.php'},
  {'name': 'Clearwater', 'county': 'Pinellas', 'building_dept': 'Clearwater Development Services', 'phone': '(727) 562-4740', 'url': 'https://www.myclearwater.com/government/departments/neighborhood-services-development/development-services'},
  {'name': 'Largo', 'county': 'Pinellas', 'building_dept': 'Largo Community Development', 'phone': '(727) 587-6740', 'url': 'https://www.largo.com/department/index.php?structureid=22'},
  {'name': 'Fort Lauderdale', 'county': 'Broward', 'building_dept': 'Fort Lauderdale Building Services', 'phone': '(954) 828-6520', 'url': 'https://www.fortlauderdale.gov/departments/sustainable-development/building-services'},
  {'name': 'Hollywood', 'county': 'Broward', 'building_dept': 'Hollywood Building Division', 'phone': '(954) 921-3335', 'url': 'https://www.hollywoodfl.org/departments/building-division'},
  {'name': 'Pembroke Pines', 'county': 'Broward', 'building_dept': 'Pembroke Pines Building & Permitting', 'phone': '(954) 431-4500', 'url': 'https://www.ppines.com/departments/building'},
  {'name': 'Coral Springs', 'county': 'Broward', 'building_dept': 'Coral Springs Building Department', 'phone': '(954) 344-5920', 'url': 'https://www.coralsprings.gov/departments/building'},
  {'name': 'Miramar', 'county': 'Broward', 'building_dept': 'Miramar Building Department', 'phone': '(954) 602-3200', 'url': 'https://www.miramarfl.gov/departments/building'},
  {'name': 'Sunrise', 'county': 'Broward', 'building_dept': 'Sunrise Building Division', 'phone': '(954) 746-3232', 'url': 'https://www.sunrisefl.gov/departments/building'},
  {'name': 'Pompano Beach', 'county': 'Broward', 'building_dept': 'Pompano Beach Building Department', 'phone': '(954) 786-4010', 'url': 'https://www.pompanobeachfl.gov/departments/building'},
  {'name': 'Cape Coral', 'county': 'Lee', 'building_dept': 'Cape Coral Building Development Services', 'phone': '(239) 574-0546', 'url': 'https://www.capecoral.gov/department/community_development.php'},
  {'name': 'Fort Myers', 'county': 'Lee', 'building_dept': 'Fort Myers Building Department', 'phone': '(239) 321-7925', 'url': 'https://www.cityftmyers.com/departments/community-development/building'},
  {'name': 'Tallahassee', 'county': 'Leon', 'building_dept': 'Tallahassee Building Inspection', 'phone': '(850) 891-7000', 'url': 'https://www.talgov.com/permits'},
  {'name': 'Gainesville', 'county': 'Alachua', 'building_dept': 'Gainesville Building Inspection', 'phone': '(352) 334-5050', 'url': 'https://www.gainesvillefl.gov/Government/Departments/Development-Services'},
  {'name': 'Lakeland', 'county': 'Polk', 'building_dept': 'Lakeland Building Inspection', 'phone': '(863) 834-6012', 'url': 'https://www.lakelandgov.net/department/building-inspection/'},
  {'name': 'Winter Haven', 'county': 'Polk', 'building_dept': 'Winter Haven Building Department', 'phone': '(863) 291-5697', 'url': 'https://www.mywinterhaven.com/departments/building'},
  {'name': 'Palm Bay', 'county': 'Brevard', 'building_dept': 'Palm Bay Building Department', 'phone': '(321) 953-8924', 'url': 'https://www.palmbayfl.gov/departments/development-services'},
  {'name': 'Melbourne', 'county': 'Brevard', 'building_dept': 'Melbourne Development Services', 'phone': '(321) 608-7900', 'url': 'https://www.melbourneflorida.org/departments/development-services'},
  {'name': 'Cocoa', 'county': 'Brevard', 'building_dept': 'Cocoa Building Department', 'phone': '(321) 433-8688', 'url': 'https://www.cocoafl.org/departments/development-services'},
  {'name': 'West Palm Beach', 'county': 'Palm Beach', 'building_dept': 'West Palm Beach Development Services', 'phone': '(561) 822-2200', 'url': 'https://www.wpb.org/departments/development-services'},
  {'name': 'Boca Raton', 'county': 'Palm Beach', 'building_dept': 'Boca Raton Building Services', 'phone': '(561) 393-7960', 'url': 'https://www.myboca.us/departments/building-services'},
  {'name': 'Delray Beach', 'county': 'Palm Beach', 'building_dept': 'Delray Beach Building Department', 'phone': '(561) 243-7200', 'url': 'https://www.delraybeachfl.gov/departments/building'},
  {'name': 'Boynton Beach', 'county': 'Palm Beach', 'building_dept': 'Boynton Beach Building Division', 'phone': '(561) 742-6200', 'url': 'https://www.boynton-beach.org/departments/building'},
  {'name': 'Port St. Lucie', 'county': 'St. Lucie', 'building_dept': 'Port St. Lucie Building Department', 'phone': '(772) 871-5132', 'url': 'https://www.cityofpsl.com/departments/building'},
  {'name': 'Daytona Beach', 'county': 'Volusia', 'building_dept': 'Daytona Beach Building Division', 'phone': '(386) 671-8140', 'url': 'https://www.codb.us/departments/building-division'},
  {'name': 'Deltona', 'county': 'Volusia', 'building_dept': 'Deltona Building Division', 'phone': '(386) 878-8100', 'url': 'https://www.deltonafl.gov/departments/growth-management/building-division'},
  {'name': 'Kissimmee', 'county': 'Osceola', 'building_dept': 'Kissimmee Building & Permitting', 'phone': '(407) 518-2120', 'url': 'https://www.kissimmee.gov/departments/building-permitting'},
  {'name': 'Pensacola', 'county': 'Escambia', 'building_dept': 'Pensacola Development Services', 'phone': '(850) 436-5500', 'url': 'https://www.cityofpensacola.com/343/Development-Services'},
  {'name': 'Ocala', 'county': 'Marion', 'building_dept': 'Ocala Planning & Inspections', 'phone': '(352) 629-8400', 'url': 'https://www.ocalafl.org/government/city-departments-i-z/planning-inspections'},
  {'name': 'Naples', 'county': 'Collier', 'building_dept': 'Naples Building Department', 'phone': '(239) 213-1036', 'url': 'https://www.naplesgov.com/departments/community-services/building'},
  {'name': 'Marco Island', 'county': 'Collier', 'building_dept': 'Marco Island Community Development', 'phone': '(239) 389-5010', 'url': 'https://www.cityofmarcoisland.com/departments/community-development'},
  {'name': 'Sarasota', 'county': 'Sarasota', 'building_dept': 'City of Sarasota Building Division', 'phone': '(941) 263-6413', 'url': 'https://www.sarasotafl.gov/departments/planning-and-development'},
  {'name': 'Bradenton', 'county': 'Manatee', 'building_dept': 'Bradenton Building Department', 'phone': '(941) 932-9400', 'url': 'https://www.bradenton.gov/departments/building'},
  {'name': 'St. Augustine', 'county': 'St. Johns', 'building_dept': 'St. Augustine Building Department', 'phone': '(904) 825-1065', 'url': 'https://www.citystaug.com/departments/building'},
  {'name': 'Sanford', 'county': 'Seminole', 'building_dept': 'Sanford Building Department', 'phone': '(407) 688-5089', 'url': 'https://www.sanfordfl.gov/departments/building'},
  {'name': 'Altamonte Springs', 'county': 'Seminole', 'building_dept': 'Altamonte Springs Building Division', 'phone': '(407) 571-8150', 'url': 'https://www.altamonte.org/departments/building'},
  {'name': 'Fort Walton Beach', 'county': 'Okaloosa', 'building_dept': 'Fort Walton Beach Building Department', 'phone': '(850) 833-9590', 'url': 'https://www.fwb.org/departments/building'},
  {'name': 'Destin', 'county': 'Okaloosa', 'building_dept': 'Destin Building Department', 'phone': '(850) 837-4242', 'url': 'https://www.cityofdestin.com/departments/building'},
  {'name': 'Panama City', 'county': 'Bay', 'building_dept': 'Panama City Building Department', 'phone': '(850) 872-3025', 'url': 'https://www.panamacity.gov/departments/building'},
  {'name': 'Key West', 'county': 'Monroe', 'building_dept': 'Key West Building Department', 'phone': '(305) 809-3720', 'url': 'https://www.cityofkeywest-fl.gov/departments/building'},
]
