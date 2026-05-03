# Verification Log

Each render of the Coverage Gap Index dashboard requires manual spot-checks against ground truth before the site is published. Every check goes here.

The render command refuses to proceed unless the latest build has at least 5 confirmed entries from the current data version.

Signoff template:

```
## YYYY-MM-DD HH:MM signed off by [name]

Build: [git short SHA, or data/processed/.build_id]
CAH: [hospital name and Medicare provider number]
Claim on dashboard: "[exact text as it appears on the gap card]"
Source consulted: [Google search URL or AHA directory URL]
Quoted evidence: "[at least one snippet that confirms or refutes the claim]"
Result: [CONFIRMED | DISPUTED | INCONCLUSIVE]
Action: [DEPLOY | HOLD | INVESTIGATE]
Notes: [optional]
```

A `DISPUTED` or `INCONCLUSIVE` result on any of the 5 sampled CAHs blocks the render until the underlying issue is fixed and re-verified.

---

## Entries

## 2026-05-03 17:00 signed off by Amar

Build: 10fe3dcd3bf27f09
CAH: FIELD HEALTH SYSTEM, Medicare provider 251309 (Centreville, Wilkinson County, MS)
Claim on dashboard: "0 nephrologists within 30 miles, level HIGH"
Source consulted: Google search "nephrology nephrologist Centreville Mississippi OR Wilkinson County MS"
Quoted evidence: "the search results don't show nephrologists specifically located in Centreville or Wilkinson County, MS"; closest practices are Central Nephrology Clinic in Flowood (around 80 miles north) and UMMC in Jackson.
Result: CONFIRMED
Action: DEPLOY
Notes: Wilkinson County is in extreme southwestern MS, near the LA border. Closest urban specialty care is Baton Rouge LA (around 60 miles), still outside our 30 mile radius.

## 2026-05-03 17:00 signed off by Amar

Build: 10fe3dcd3bf27f09
CAH: RALEIGH COMMUNITY HOSPITAL, Medicare provider 251301 (Raleigh, Smith County, MS)
Claim on dashboard: "0 neurologists within 30 miles, level HIGH"
Source consulted: Google search "neurologist neurology Raleigh Mississippi OR Smith County Magee MS"
Quoted evidence: "the results did not show specific neurologists or practices located directly in Raleigh or Smith County"; closest are Hattiesburg Clinic neurologists (around 50 miles southeast) and Mississippi Neurological Institute in Jackson (around 60 miles west).
Result: CONFIRMED
Action: DEPLOY

## 2026-05-03 17:00 signed off by Amar

Build: 10fe3dcd3bf27f09
CAH: OCHSNER LAIRD HOSPITAL, Medicare provider 251322 (Union, Newton County, MS)
Claim on dashboard: "0 orthopedic surgeons within 30 miles, level HIGH"
Source consulted: Google search "orthopedic surgery surgeon Union Mississippi OR Newton County MS"
Quoted evidence: Mississippi Sports Medicine in Flowood (around 70 miles west) and Specialty Orthopedic Group in Tupelo (around 100 miles north) are the nearest hits. The "Baptist Memorial Hospital-Union County" reference in the results is in Tupelo (Lee County), not the Union, MS in Newton County.
Result: CONFIRMED
Action: DEPLOY
Notes: Worth flagging: Mississippi has both a town named "Union" in Newton County and a separate "Union County" in the north. The hospital in our claim is in Newton County's Union, MS.

## 2026-05-03 17:00 signed off by Amar

Build: 10fe3dcd3bf27f09
CAH: CLAIBORNE COUNTY HOSPITAL, Medicare provider 251320 (Port Gibson, Claiborne County, MS)
Claim on dashboard: "0 oncologists within 30 miles, level HIGH"
Source consulted: Google search "oncology oncologist Claiborne County Mississippi OR Port Gibson MS cancer specialist"
Quoted evidence: "the search results don't indicate that the hospital has dedicated oncologists on staff"; nearest oncology is in Jackson (around 45 to 60 miles north, just outside our 30 mile radius) or the Gulf Coast (200+ miles south).
Result: CONFIRMED
Action: DEPLOY

## 2026-05-03 17:00 signed off by Amar

Build: 10fe3dcd3bf27f09
CAH: NORTH SUNFLOWER MEDICAL CENTER CAH, Medicare provider 251318 (Ruleville, Sunflower County, MS)
Claim on dashboard: "0 endocrinologists within 30 miles, level HIGH"
Source consulted: Google search "endocrinology endocrinologist Ruleville Mississippi OR Sunflower County MS diabetes specialist"
Quoted evidence: "the search results don't show specialists specifically located in Ruleville or Sunflower County"; closest endocrine clinics are in Jackson (around 110 miles south).
Result: CONFIRMED
Action: DEPLOY
Notes: Sunflower County is in the MS Delta. The Delta is a known specialty care desert; this matches our finding.
