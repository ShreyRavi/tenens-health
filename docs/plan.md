# Coverage Gap Index, V1 Implementation Plan

Generated 2026-05-03 from `/plan-eng-review` on the tenens 30-day sprint design docs.
Target ship: 2026-05-04 (YC submission day).
Status: greenfield, `tenens-health/` repo is empty.

## What we're building (V1)

A static HTML dashboard rendered to `site/` showing, for each of Mississippi's 40 Critical Access Hospitals, which of 15 core specialties have zero in-network coverage within 60 miles. Built from public CMS data only (NPPES, CAH Provider of Services, optionally HRSA HPSA and Medicare Part B PUF). Local-first. Repo private. Vercel deploy follows after voice review of the audit log.

Strategic context lives in `../tenens/docs/design.md` and `../tenens/docs/ceo-plan.md`. This document is engineering-only.

## What already exists

- Strategy and design in `../tenens/docs/{design,ceo-plan,30-day-sprint,data-sources,learnings}.md`. Treat as source of truth for problem framing, scope, target user.
- Empty git repo at `tenens-health/`. Greenfield Python build.

## NOT in scope for V1

1. Cold email pack (`email_pack.csv` for Gmass). Reason: dashboard is the YC submission artifact; email goes out between submission and the YC interview. Returns in V2.
2. Surgeon father network YAML and locum match logic. Reason: load-bearing claim is the gap data itself. Adds credibility to email more than to a static dashboard. Returns in V2.
3. Public deploy (Vercel + tenenshealth.com). Reason: repo is private during voice review of audit log. Local-only V1, Vercel later.
4. Medicare Part B PUF demand weighting. Reason: dashboard headlines work on physician counts alone. First on the cut list if 24hr budget tightens. Returns post-YC.
5. HRSA HPSA county overlay. Reason: nice-to-have urgency multiplier on the gap score. Second on the cut list if budget tightens.
6. Map visualization. Reason: time risk. V1 is a sortable table by CAH, by specialty, by gap severity. Map comes after deploy.
7. Auth, payments, user accounts, dynamic backend. Reason: never (per design doc).

## Architecture

### Project layout

```
tenens-health/
├── pyproject.toml
├── README.md
├── .gitignore
├── docs/
│   └── plan.md                          # this file
├── src/coverage_gap/
│   ├── __init__.py
│   ├── cli.py                           # Typer: download, build, verify, render, serve
│   ├── config.py                        # paths, constants, target state, radius
│   ├── ingest/
│   │   ├── __init__.py
│   │   ├── nppes.py
│   │   ├── cah_pos.py
│   │   ├── hrsa_hpsa.py                 # stretch
│   │   └── medicare_puf.py              # stretch
│   ├── taxonomy.py                      # NPPES code to specialty mapping
│   ├── taxonomy.yaml                    # the source of truth for codes
│   ├── geo.py                           # Nominatim wrapper, ZIP centroid, haversine
│   ├── scoring.py                       # gap_score(cah, specialty)
│   ├── verification.py                  # spot-check signoff gate
│   └── render/
│       ├── __init__.py
│       ├── build.py                     # Jinja2 site builder
│       ├── templates/
│       │   ├── base.html
│       │   ├── index.html
│       │   ├── cah_detail.html
│       │   ├── methodology.html
│       │   └── about.html
│       └── static/
│           └── style.css
├── data/
│   ├── raw/                             # gitignored, large CMS files
│   └── processed/                       # gitignored, parquet artifacts
├── site/                                # gitignored, render output
├── tests/
│   ├── __init__.py
│   ├── fixtures/                        # tiny CMS samples checked in
│   ├── test_taxonomy.py
│   ├── test_scoring.py
│   ├── test_geo.py
│   └── test_verification.py
└── audit/
    ├── decisions.md                     # YC-facing engineering log, hand voiced
    └── verification-log.md              # signoffs before each render
```

### Data flow

```
NPPES (8GB)        ──filter MS+adj states──▶  ms_physicians.parquet  ──┐
CAH POS file       ──filter MS, CAH only──▶  ms_cahs.parquet (~40)  ──┤
HRSA HPSA          ──MS counties──▶  hpsa_overlay.parquet  ───────────┼──▶  scoring  ──▶  gap_matrix.parquet (40 x 15)
Medicare Part B    ──aggregate, stretch──▶  demand_proxy.parquet  ───┘                        │
                                                                                              │
                                                  geocoder (Nominatim)  ─cached─▶  cah_geo.parquet
                                                                                              │
                                                                                              ▼
                                                                            verification gate (manual signoff)
                                                                                              │
                                                                                              ▼
                                                                            Jinja2 render  ──▶  site/
                                                                                              │
                                                                                              ▼
                                                                            local serve  /  Vercel (later)
```

### Module responsibilities

| Module | Responsibility | LOC est |
|---|---|---|
| `cli.py` | Typer commands: download, build, verify, render, serve | ~150 |
| `config.py` | Paths, constants, target state, radius, specialty list | ~50 |
| `ingest/nppes.py` | Download NPPES, filter MS+adj, write parquet | ~120 |
| `ingest/cah_pos.py` | Pull CAH POS file, filter to MS CAHs | ~80 |
| `ingest/hrsa_hpsa.py` | HRSA HPSA designations for MS counties | ~60 |
| `taxonomy.py` | YAML-backed NPPES code to specialty mapping | ~80 |
| `geo.py` | Nominatim wrapper (cached), ZIP centroid, haversine | ~150 |
| `scoring.py` | gap_score returns CRITICAL/HIGH/MOD/COVERED | ~100 |
| `verification.py` | Random sample picker, signoff gate against audit log | ~100 |
| `render/build.py` | Jinja2 builder, writes `site/` | ~120 |
| Templates + CSS | base, index, cah_detail, methodology, about | ~300 markup |

Total estimate: ~1500 lines code + ~300 markup + tests.

## Decisions (see `audit/decisions.md` for context)

| # | Decision | Status |
|---|---|---|
| D1 | Python package with Typer CLI, not notebooks | accepted |
| D2 | Golden tests + manual verification gate before render | accepted |
| D3 | Nominatim for hospitals, ZIP centroid for physicians | accepted |
| D4 | Full NUCC taxonomy mapping in versioned YAML | accepted |
| D5 | Defer surgeon-father physician network to V2 | deferred |
| D6 | `audit/decisions.md` in working-engineer voice (no AI tells) | accepted |
| D7 | Headline number conditional on verified data, not assumed | accepted |
| D8 | Local-first, Vercel deploy after voice review | accepted |
| D9 | Cut Medicare Part B PUF first if 24hr budget tightens | conditional |
| D10 | Primary radius 30 miles (HRSA convention), not 60 | accepted post-data |

## Test coverage diagram

```
CODE PATHS                                                          COVERAGE
[+] src/coverage_gap/taxonomy.py
  ├── load_taxonomy()                                               [TEST] YAML loads, all 15 specialties present
  ├── nppes_code_to_specialty()                                     [TEST] golden mapping for known codes
  ├── unknown_code_handling()                                       [TEST] returns None, doesn't raise
  └── missing_yaml_file()                                           [TEST] raises with clear error

[+] src/coverage_gap/geo.py
  ├── haversine(p1, p2)                                             [TEST] known distances (Jackson MS to Greenwood MS)
  ├── geocode_nominatim(address)                                    [TEST] mock response, error handling, retry on timeout
  ├── zip_centroid(zip_code)                                        [TEST] known zip centroids
  ├── geocode_or_centroid_fallback()                                [TEST] fallback path when Nominatim fails
  └── cache_hit_path()                                              [TEST] returns cached without HTTP call

[+] src/coverage_gap/scoring.py
  ├── gap_score(cah, specialty, physicians, radius_mi)              [TEST] golden: known CAH + known specialty -> known score
  ├── critical_threshold (0 within 60mi AND HPSA designated)        [TEST] both met -> CRITICAL
  ├── high_threshold (0 within 60mi, no HPSA)                       [TEST] -> HIGH
  ├── moderate_threshold (1-2 within 60mi)                          [TEST] -> MODERATE
  ├── covered_threshold (3+ within 60mi)                            [TEST] -> COVERED
  └── radius_edge (physician at exactly 60.0 miles)                 [TEST] inclusive, counts as COVERED

[+] src/coverage_gap/verification.py
  ├── pick_random_sample(n=5)                                       [TEST] deterministic with seed
  ├── format_for_human_review()                                     [TEST] output snapshot
  ├── check_signoff_present()                                       [TEST] passes when log entry exists, fails when missing
  └── refuse_render_without_signoff()                               [TEST] raises VerificationGateError

[+] src/coverage_gap/ingest/nppes.py
  ├── filter_to_ms_region()                                         [TEST] fixture with 100 rows -> ~30 MS rows
  ├── parse_taxonomy_field()                                        [TEST] handles multi-code field
  └── write_parquet()                                               [TEST] roundtrip read/write

[+] src/coverage_gap/ingest/cah_pos.py
  ├── filter_ms_cahs()                                              [TEST] fixture -> known MS CAH count
  └── extract_address_for_geocoding()                               [TEST] address concatenation

[+] src/coverage_gap/render/build.py
  ├── build_index_page()                                            [SMOKE] renders without exception
  ├── build_cah_pages()                                             [SMOKE] one page per CAH, count matches input
  └── headline_picker()                                             [TEST] data X -> headline (a), data Y -> (b)

USER FLOWS
[+] Build pipeline end to end
  └── download -> build -> verify -> render -> serve                [SMOKE] runs against fixture data, site/ produced

[+] Verification gate UX
  ├── render fails before signoff                                   [TEST] integration: render exits 1 with helpful message
  └── render passes after signoff                                   [TEST] integration: signoff written, render proceeds

COVERAGE TARGET: 18 of 22 paths tested at V1 ship (~82%)
QUALITY: golden tests on the 4 paths that produce numbers shown to users (taxonomy, scoring, geo, headline_picker)
```

Legend: `[TEST]` full unit test with assertions, `[SMOKE]` runs without exception.

## Failure modes

For each codepath, one realistic production failure:

| Codepath | Failure | Test? | Handled? | User sees |
|---|---|---|---|---|
| `ingest/nppes.py` | NPPES URL is down or 404s | yes (mock) | retry then fail loud | clear error, no partial data |
| `ingest/nppes.py` | NPPES file format changes column names | no | no | crash with KeyError. CRITICAL GAP if it ships untested |
| `taxonomy.py` | YAML has typo in specialty code | yes (golden test) | test catches before deploy | dev sees test fail |
| `taxonomy.py` | NUCC adds new code we missed | no (no way to detect) | manual periodic refresh | gap is over-claimed (worst direction). LOG IN AUDIT |
| `geo.py` | Nominatim rate limits us | yes (retry test) | tenacity retry with backoff | one-off retry, succeeds |
| `geo.py` | Address can't be geocoded ("Rural Route 4 Box 17") | yes (fallback test) | fall back to ZIP centroid | accuracy degrades, methodology page documents |
| `scoring.py` | CAH has zero physicians of any kind in NPPES | yes (edge test) | returns CRITICAL on every specialty | dashboard shows "zero coverage everywhere" |
| `scoring.py` | NPPES rows include retired or inactive providers | yes (filter test) | filter on active deactivation date | counts reflect active providers only |
| `verification.py` | Render runs without signoff | yes (gate test) | refuses to proceed | dev sees error, must sign off |
| `verification.py` | Signoff is written without an actual Google check | no (process gap) | no | dashboard publishes wrong claim. CRITICAL HUMAN-PROCESS GAP |
| `render/build.py` | Template missing variable | no | Jinja raises at render | dev sees error |

CRITICAL gaps (no test, no error handling, would silently ship wrong data):

1. NPPES schema drift. If CMS renames a column we crash, but worse, if they add a column with similar meaning we might silently ignore it. Mitigation: pin to a specific NPPES file date in `data/raw/.versions.json`, and a CI test that asserts column names against the pinned schema.
2. Verification signoff is a process control, not a technical control. Mitigation: signoff template requires founder to paste the Google search URL plus at least one quoted result. Doesn't make fraud impossible, makes it harder to fake by accident.

## Hour-by-hour critical path (24hr window)

| Block | Work | Est | Checkpoint |
|---|---|---|---|
| 1 | Scaffold pyproject + .gitignore + module skeletons + serve cmd | 1h | `uv sync` succeeds, `uv run pytest` runs (0 tests, 0 fails) |
| 2 | NPPES download + Mississippi-region filter (start in background early) | 2h | `data/processed/ms_physicians.parquet` exists with rows |
| 3 | CAH POS pull + filter to 40 MS CAHs | 30m | `data/processed/ms_cahs.parquet` has ~40 rows |
| 4 | Taxonomy YAML + tests | 2h | `pytest tests/test_taxonomy.py` passes |
| 5 | Geocode 40 CAHs (Nominatim, cached) + ZIP centroid table for physicians | 1h | `data/processed/cah_geo.parquet` has 40 rows with lat/lng |
| 6 | Scoring + golden tests on 3 hard-coded CAHs | 1.5h | gap matrix produced, golden tests pass |
| 7 | Jinja templates + CSS + render command | 2h | `site/index.html` and `site/cah/*.html` exist |
| 8 | Manual verification of 5 random CAHs vs Google | 1h | `audit/verification-log.md` has 5 signoffs |
| 9 | Local serve + visual review | 30m | dashboard loads at `localhost:8000` |
| 10 | Final `audit/decisions.md` voice review | 30m | sniff-test passed |

Sum: 12.5h with 2h slack inside the 24hr window. If we slip past 14h, cut Medicare PUF first, then HRSA HPSA.

Each block has a checkpoint that lets you sanity-check before moving on. If a checkpoint fails, we don't proceed.

## Worktree parallelization

Sequential. One technical founder, no parallel git workstreams. Inside blocks 4-7 there is room for overlap (taxonomy YAML can be authored while NPPES download runs in another shell), but no separate worktrees needed.

## How AI was guided (the YC narrative)

Six places in this session where Claude's first instinct was wrong or insufficient and a founder decision corrected it. This list is the basis for the YC application section "How we worked with AI."

1. **Initial scope kept email pack in V1 critical path.** Founder steer: dashboard ships tomorrow for the YC submission, email defers to the gap between submission and interview.
2. **Claude wanted surgeon-father network match in V1 cards.** Founder steer: defer. The dashboard's load-bearing claim is the gap data itself. Locum candidate matching adds value to email outreach more than to a static dashboard.
3. **Claude was about to write the audit log in default formal voice.** Founder steer: an LLM will read this for the YC submission and judge whether it reads as human-authored. Voice rule established: no em-dashes, no AI vocabulary list, no triadic phrasing, no over-formatted bullets. Working engineer's notebook only.
4. **Claude hand-waved geocoding cost.** Founder validated the Nominatim-for-hospitals + ZIP-centroid-for-physicians split, accepting the under-1% accuracy loss inside a 60mi radius and documenting the tradeoff on the methodology page.
5. **Claude proposed automated verification.** Founder pushed for human-in-loop: founder must Google 5 random hospitals before render proceeds. Verification gate exists at the technical level (refuses render without log entries) and at the process level (signoff template requires a Google URL plus a quoted result).
6. **Claude's initial headline assumed "X of 40 CAHs have zero cardiologists" was the dashboard lead.** Founder kept it conditional. The `headline_picker` function chooses from three candidates based on what the verified data supports. If X is too small to carry the page, we fall back to softer framing.

## Open risks for the next 24 hours

1. NPPES download time. The full file is 8GB. On a slow connection this could blow the budget. Mitigation: kick off download in the background while we work on taxonomy and tests.
2. Taxonomy mapping wrong. If we miss subspecialty codes we under-count physicians and falsely claim a gap. Mitigation: golden test against known NPPES counts for two specialties (cardiology, general surgery) where we can validate against AMA workforce snapshots.
3. Verification surfaces a real bug. If we Google a hospital and find we claimed zero where the answer is two, we have to debug and reship before deadline. Mitigation: run verification at hour 8, not hour 13. Surfaces problems with time to fix.
4. Voice review fails. If `audit/decisions.md` reads as AI-generated to the founder, we rewrite. Mitigation: founder reviews early, not late. Allow 30m budget for iteration.
5. Vercel deploy slip. We're not deploying tomorrow but the code should be deploy-ready (clean build output, no broken paths, no absolute file refs) so a future deploy is one command.

---

---

## V2 — Map-First Dashboard

Captured 2026-05-03 from founder review of the V1 local preview. **Shipped same day.** This section reflects the original plan; see `audit/decisions.md` for the V2 build entry and the two /review findings that were folded in (build_id binding, coord_source flag).

### What changes from V1

1. The sortable table on the homepage becomes a full-page interactive Mississippi map. Clicking a region (or a hospital point) opens a side panel with the critical specialty needs for that area.
2. The headline drops the single-specialty framing ("32 of 40 CAHs have zero rheumatology"). It moves to an aggregate frame: how many hospitals have broad specialty deserts, not which one specialty is most missing. The single-specialty number stays available on the methodology page or in a secondary tile, but it isn't the lead.
3. The CAH detail pages become side panel content rendered into the same single-page experience. URL hash routing keeps each CAH directly linkable for cold emails.

### Visual reference

coopersquare.org/leadmap. Implemented as an Observable Notebook iframe by BetaNYC. Building-level lead paint risk for NYC, with click-to-detail. Same vibe we want: a serious data tool, not a marketing page.

### Map design

Geographic granularity is the first decision. Three viable layers:

| Approach | Visual | Pros | Cons |
|---|---|---|---|
| County choropleth | 82 MS counties shaded by gap intensity | Familiar map shape, easy to scan, matches HRSA HPSA county designations | County-level averages a CAH that has 12 gaps with another in the same county that has 2 |
| CAH point map | 40 hospitals as scaled circles | The buyer-relevant unit (CMO buys for one hospital, not a county) | Sparse in some counties, hard to see at MS-state zoom |
| Hybrid | County choropleth + CAH points overlaid | Geography plus specifics in one view | Two visual systems to design well; legend gets busy |

Recommend hybrid. County shading gives the eye the shape of the problem. CAH points are where the YC partner clicks to see the actual hospital they would email.

Library is the second decision:

| Library | Bundle | Notes |
|---|---|---|
| MapLibre GL JS | ~150KB | Vector tiles, open source, no API key. Best polish for a YC artifact |
| Leaflet + GeoJSON | ~40KB | Simpler, raster tiles, easier to debug, less polished |
| Mapbox GL JS | ~200KB | Prettiest of the three, but requires API key + billing setup |

Recommend MapLibre. No billing dependency, polished output, fully static so it deploys to Vercel as-is.

Side panel on click should show:
- Region name (county or CAH name + city)
- Aggregate severity: "N of 15 core specialties have HIGH or CRITICAL gaps within 30 miles"
- The top 5 missing specialties as a list, with each linking to a methodology note about that specialty
- For CAH clicks: Medicare provider number, address, and (V2.5) a "Compose CMO email" link that pre-fills the email pack body
- For county clicks: list of CAHs in the county and their individual gap counts

### Aggregate framing redesign

Replace the single-specialty headline with an aggregate one. Three candidate framings:

| Candidate | Example | Buyer salience |
|---|---|---|
| Hospital-level breadth | "27 of 40 Mississippi CAHs are missing 10 or more of 15 core specialties within 30 miles" | High; CMO sees "we are one of 27" |
| County-level breadth | "Y of 82 Mississippi counties have no specialty coverage in 5+ core specialties" | Medium; abstract for a CMO |
| Combined | "A counties with 10+ gaps, B CAHs with 10+ gaps. Click to see which" | Low; two numbers compete |

Recommend hospital-level. CMOs buy services for one hospital, not for a county. The headline should match the unit of decision.

The table on the index page (currently per-specialty columns) becomes:
- Hospital name
- City + county
- Total HIGH/CRITICAL gap count (out of 15)
- Three most-missing specialties as comma-separated text
- Sortable by total gap count

The per-specialty granularity moves to the side panel on click, where it belongs.

### What stays from V1

The whole pipeline. NPPES + CAH POS + ZIP centroids ingest, taxonomy, scoring, verification gate, audit log discipline, 30 mile radius, HRSA convention reasoning. The data layer doesn't change. Only the presentation and headline framing do.

### New data the V2 needs

- Mississippi county GeoJSON (Census TIGER cb_2020_us_county_500k, filter to MS). Around 80KB.
- CAH lat/lon already produced by V1.
- (Optional) Census ACS county population estimates if we want population-served context. ACS 5-year tables, free.

### Implementation effort estimate

About 12 hours of focused work. Block breakdown:

| Block | Work | Est |
|---|---|---|
| 1 | Add MapLibre GL JS, set up base style and MS bbox | 1h |
| 2 | Pull Census MS county GeoJSON, simplify to web-friendly size | 1h |
| 3 | Add ingest module to compute county aggregates (CAH gap rollup by county) | 1.5h |
| 4 | Choropleth shading by gap intensity | 1h |
| 5 | CAH point overlay with scaled markers | 1h |
| 6 | Click handlers + side panel layout + URL hash routing | 2.5h |
| 7 | Aggregate headline picker rewrite | 1h |
| 8 | Index table redesign (drop per-specialty cols, add aggregate) | 1h |
| 9 | Mobile responsive (map gets stacked above panel on small screens) | 1h |
| 10 | Visual polish (legend, color palette, typography) | 1h |
| 11 | Verification re-run against new aggregate claims, sign off, render | 1h |

### Distribution

Vercel deploy from `site/`. Static HTML plus map JS works on free tier. Custom domain tenenshealth.com points at the deployment. Mobile responsiveness matters because CMOs read email on phones.

### Open decisions for the founder before V2 starts

1. Map library: MapLibre (recommended) vs Leaflet vs Mapbox
2. Granularity: hybrid (recommended) vs county-only vs CAH-points-only
3. Headline framing: hospital-level breadth (recommended) vs county-level vs combined
4. Whether to include Census ACS population-served context per region (V2 vs V2.5)
5. Whether the "compose CMO email" link ships with V2 or waits for the email pack work
6. Color palette for the choropleth (suggest a perceptually uniform sequential scale like Viridis-trim or a healthcare-conventional red-orange-yellow-green for severity)

### What this means for the YC submission going out tomorrow

V1 stays the deployable artifact for the YC application. V2 is the next sprint, week of 2026-05-04. The V1 dashboard already supports the YC narrative ("we built this from public data, here is the gap, here is the methodology"). V2 is what the YC partner sees if they come back to the link a week later.

---

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope and strategy | prior | clean (in tenens repo) | already approved, see `../tenens/docs/ceo-plan.md` |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | not run | optional |
| Eng Review | `/plan-eng-review` | Architecture and tests (required) | 1 | clean | this document |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | not run | recommended before Vercel deploy (V2) |
| DX Review | `/plan-devex-review` | Developer experience gaps | 0 | not run | not applicable, internal tool |

UNRESOLVED: 0
VERDICT: ENG CLEARED. Recommend `/plan-design-review` before V2 Vercel deploy.
