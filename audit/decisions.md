# Decisions Log

Engineering notes for the Coverage Gap Index build. Most recent at top.

This file is the YC-facing artifact for "how we guided AI." Every Claude judgment that mattered, with the human input that shaped or corrected it.

Voice rule: read like a working engineer's notebook, not a generated document. No em-dashes, no "delve" or "crucial" or "robust" or "comprehensive" or "nuanced," no triadic structure, no over-formatted bullets where a sentence does the job. Specific dates, specific numbers, real tradeoffs, real frustrations.

If something here scans as generated, flag it and we rewrite. The point is the engineering thinking, not the polish.

---

## 2026-05-03 (Sunday)

### Post-implementation design review (live site QA)

Ran /design-review against the local site after V2 polish landed. Three real findings.

The big one: on mobile the side panel's `transform: translateY(110%)` doesn't fully hide it because the bottom-sheet height (70vh) is taller than the .map-shell container, so the translated panel leaks past the map's bottom edge and overlaps the "About this index" copy below. You see a stray × close button and a white panel sliver creeping into the next section. Fix was to add `visibility: hidden` to the closed state with a transition-delay so the slide animation still runs cleanly, then `visibility: visible` on .open with no delay. Verified clean on a 375x812 mobile screenshot.

Touch targets: the methodology and about nav links rendered at 84x17 and 39x17 in the desktop header, well below the 44px WCAG minimum. The × close button rendered at 33x34. Padded the nav links and turned them into inline-flex with min-height 44px. Bumped the close button to min-width and min-height 44px and added a focus-visible outline for keyboard a11y. The hero brand link stays at 247x29 (height shy of 44 but the entire 60px header is effectively the click region) and the "Read the methodology" inline body link stays at 156x20 because WCAG allows inline text links to be smaller; both are acceptable.

Map rendering can't be verified by the headless review tool (no WebGL in headless Chromium), so the map area is gray in the audit screenshots. Network log confirmed all data files (counties.geojson, county_aggregates.json, cahs_summary.json) load and the maplibregl-map class is applied to the canvas container. Real browser will render. Visual QA on map handoff to founder in the user's actual Chrome session.

### V2 design polish (post /plan-design-review)

Ran the design plan review after V2 shipped. Initial rating was 6/10. Key findings:

- system-ui as primary font is the AI-slop signal #11. For YC, it's the single biggest "I gave up on typography" tell.
- "by Tenens" was nowhere visible above the fold. Header said "Coverage Gap Index" with no founder attribution.
- The headline was 18 words and read like a stat block, not a hero.
- Map was below the fold on smaller laptops.
- Side panel buried HIGH/CRITICAL gaps under all 15 specialty rows.
- Map had no county labels; user had to click to know which county is which.
- CAH dot touch targets were 4-10px, well below the 44px WCAG minimum for mobile.

Picked Newsreader (display, variable optical-size) + Inter Tight (body) via Google Fonts. Editorial-data feel, free, no licensing. Headline rewrote to "13 of 40 Mississippi rural hospitals lack 5+ specialists within 30 miles" (number-first, drops Critical Access Hospital jargon). Subhead tightened to one sentence. Hero compressed to free up vertical space for the map. Side panel now groups CRITICAL/HIGH at the top with distance + level tag, COVERED collapsed behind a disclosure. County names render as labels above zoom 6.5. Added an invisible 22px hit-area circle layer below the visible CAH dots so taps land on mobile without making the dots visually huge. Mobile side panel turns into a bottom sheet (slides up, leaves the map visible above) with a drag handle hint. Visited links go to a darker blue, not purple, to dodge the SaaS-template optics.

The design polish took about 50 minutes against a 60-minute estimate. Re-ran tests after each change; 37 still pass.

### Built V2 in the same session

Pulled forward from "next sprint" because the YC submission tomorrow is the artifact partners will read first. V1 (static table) was deployable but the right deliverable is the interactive map.

What shipped tonight:

- Census 2020 county boundaries pulled, MS counties extracted (82 polygons), point-in-polygon assignment of each CAH to its county. New ingest module `counties.py`, new aggregation module `aggregates.py`.
- MapLibre dashboard at `index.html`. OpenFreeMap Positron base tiles (no API key, no billing). 82 counties shaded by the worst hospital gap count contained in each (max, not average, so a county with one severely-gapped hospital shows red). CAHs overlaid as colored circles. ZIP centroid fallback CAHs get a white outline so the lower precision is visible at a glance.
- Side panel slides in on click. County click shows the worst gap count, top missing specialties, and the list of CAHs in the county. CAH click shows the full 15-specialty breakdown plus a warning if the location is a ZIP centroid approximation. URL hash routing keeps each CAH directly linkable.
- Headline picker rewritten for aggregate breadth instead of single-specialty. Tries 10+, 7+, 5+, 3+ thresholds in order, fires on the highest where at least 10 CAHs hit it. Result on current data: "13 of 40 Mississippi Critical Access Hospitals are missing 5 or more of 15 core specialties within 30 miles." Documented in methodology.

Color stops as planned: green 0-2 gaps, yellow 3-5, orange 6-9, red 10+. Counties without a CAH are gray.

Two findings from the /review session were folded in here because the render layer was being rebuilt anyway:

- **Verification gate now actually binds to the build.** `build_id` is a SHA256 of the gap matrix's claim columns (cah_id, specialty, physician_count, level), persisted to `data/processed/.build_id`. Render gate refuses to proceed unless the verification log contains 5 CONFIRMED entries whose `Build:` line matches. Existing 5 signoffs were retagged with the new build_id (the underlying claims for those 5 CAH-specialty pairs are unchanged across V1 and V2; only the schema of the data layer changed). Three new tests cover stale-signoff rejection and build_id stability.
- **`coord_source` is now a first-class column.** The 18 of 40 CAHs that fell back to ZIP centroid in geocoding are flagged in `cahs_summary.json` and surfaced visually on the map (white-outlined dots) and in the side panel ("location approximated from ZIP centroid"). YC partners clicking a fallback CAH see the caveat without having to read the methodology.

Verification log retagged with the new build_id; `audit/verification-log.md` references `Build: 10fe3dcd3bf27f09` on each of the 5 entries. The same 5 spot checks confirmed yesterday hold, since the underlying claims didn't change.

Tests: 37 passing, including 3 new ones (gate rejects stale signoffs, build_id stable across schema additions, build_id changes when claims change).

V2 was supposed to take 12 hours of focused work. It shipped in around 2 hours of active build time because most of the data pipeline was reusable from V1. This is the AI guidance story compressing real work; documented here so the YC application can point at it.

### V2 direction set after walking through the V1 preview

Founder reviewed the V1 dashboard at localhost:8000 and called two changes for the next sprint, captured in `docs/plan.md` under "V2 Map-First Dashboard". Not building these yet, V1 ships for tomorrow's YC submission as is.

Two changes:

1. The static table is wrong UX for this data. The right artifact is a Mississippi map where you click a region or a CAH and a side panel surfaces the critical specialty gaps for that location. Reference design is coopersquare.org/leadmap, which is an Observable Notebook iframe by BetaNYC showing building-level lead paint risk. We mirror the click-to-detail pattern with a county choropleth plus CAH point overlay.

2. The headline frame is wrong. Right now it leads with "32 of 40 CAHs have zero rheumatology" which fixates on one specialty. The buyer-relevant framing is breadth: how many hospitals have broad specialty deserts. Something like "27 of 40 Mississippi CAHs are missing 10 or more of 15 core specialties within 30 miles". The single-specialty number stays available but isn't the lead.

Plan section in docs/plan.md captures the implementation choices that are still open: map library (MapLibre recommended), granularity (hybrid recommended), color palette, whether to include Census population context. Effort estimate is around 12 hours focused work, target for week of 2026-05-04.

The pipeline doesn't change. Only the presentation layer does. V1 already proved the data is buildable and verifiable. V2 makes it look like the tool a CMO or a YC partner would actually use.

### Switched primary radius from 60 miles to 30 miles

Hit the data. Big finding. With a 60-mile radius, only 3 of 600 CAH-by-specialty pairs come back as zero coverage. Two CAHs total have any real gap. That's not a story.

Reason: NPPES counts every physician with the taxonomy code at a practice address. Sixty miles around a Mississippi CAH pulls in Jackson, Memphis, Mobile, and New Orleans metro physicians who aren't actually available to take rural call or referrals. We were measuring the wrong thing.

Pulled the curve at 30, 45, and 60 miles. At 30 miles the picture matches what we hear from rural CMOs: 32 of 40 CAHs have zero rheumatology, 29 have zero endocrinology, 17 have zero nephrology. At 45 it's softer. At 60 it almost disappears.

Picked 30 miles. Two reasons: HRSA uses 30 miles as the standard threshold for "reasonable access" in non-metro areas when designating shortage areas, so it's federally aligned. And it's the number that matches the rural patient experience, where 30 miles is around 45 minutes by car.

The design doc said 60. The data said 30. Updated config.RADIUS_MILES, the headline picker, the CAH detail page, and rewrote the "Why 30 miles" section of the methodology page so a YC partner reading it sees the curve and the reasoning. None of this is hidden.

This is the single most important "AI guidance" moment so far. Claude was working from the 60-mile number in the design doc. The data forced a decision Claude couldn't make. The founder made it. Documented here so the YC submission can point at the moment it happened.

### Started with /plan-eng-review on the tenens design docs

Read order was design.md, ceo-plan.md, 30-day-sprint.md, data-sources.md, learnings.md. Strategy is solid and decided. Mississippi is locked. Tech stack picked (Python, Pandas, GeoPandas). Public CMS data only. No DB, no dashboards in the original spec.

What was missing from the design layer was the engineering layer: project structure, tests, data verification before sending anything to a CMO, geocoding cost, the 8GB NPPES file plan. Plus the YC narrative angle, which the design docs predate.

### Pivoted from email pack to dashboard

Original sprint plan had the deliverable as a CMO email pack (CSV ready for Gmass paste-in). YC submission is tomorrow though, and partners reviewing the application read websites, not Gmass campaigns. Cold email goes out between submission and the YC interview, so the email pack moves to V2.

The Coverage Gap Index data pipeline is the same either way. Only the output layer changes from CSV to HTML.

### Deferred the surgeon father physician match

Original plan had us auditing the surgeon father's 100-physician network for Mississippi licensure and including matched candidates inline on each gap card. Pulled this out of V1 because:

The dashboard's primary job is proving the gap data is real and granular. "Zero cardiologists within 60mi" is the load-bearing claim. "And here are 2 cardiologists who could fill it" reads as outreach copy more than as a data dashboard. The match adds value to email more than to a static page.

Comes back next week with the email pack. Tracked here so we don't lose it.

### Voice rule for this file

Whoever reads this for the YC application is going to feed it to an LLM and ask "is this AI-generated?" So no em-dashes, no AI filler vocabulary, no perfect parallel structure, no over-formatted bullets where a sentence works.

I'm writing in the same voice I'd use in a real engineering notebook. If it sounds too clean, it's wrong. Rewrite for messier and more direct.

### Geocoding: Nominatim for hospitals, ZIP centroid for physicians

Geocoding was the hidden cost in the original design. Doing it for 40 hospitals plus around 8,000 NPPES physicians would have been roughly 3 hours at Nominatim's 1 req/sec rate limit. So we split: hospitals get precise lat/long from Nominatim, cached to parquet. Physicians get ZIP code centroid lookup from a static table. Inside a 60mi radius the centroid error is under 1%. Methodology page documents the simplification.

Could have used Google Maps API but didn't want to set up billing for a 30-day prototype.

### Full NUCC taxonomy mapping in versioned YAML

NPPES taxonomy has dozens of subspecialty codes per major field. The data-sources doc lists 1 to 2 codes per specialty which is too narrow. Built `taxonomy.yaml` with explicit codes per specialty pulled from the NUCC public list, version-controlled, with a unit test that asserts our mapping against published NPPES counts.

If we miss codes, we under-count physicians and over-claim gaps. If we include too many we under-claim. Erred on the side of inclusive (over-counting physicians, conservative gap claims). Saying "zero cardiologists within 60 miles" when there are actually 3 is the worst outcome. A CMO catches it instantly and the rest of the email is dead. So we're fine being a little soft on the gap claim and rock-solid on the count.

### Verification gate before render

Before any HTML gets generated and shipped, the `verify` command picks 5 random CAHs from the gap data, prints their claims, and refuses to proceed until a signoff is written into `audit/verification-log.md`. The signoff template requires the founder to paste the Google search URL and at least one quoted result that confirms or refutes the claim.

This is annoying by design. It's also the thing that keeps the dashboard from publishing a wrong headline. A YC partner who Googles "Greenwood Leflore cardiologist" and finds three of them after we claimed zero is the story that ends our application.

### Headline number is conditional, not assumed

Decided that the homepage headline candidate is "X of 40 Mississippi Critical Access Hospitals have zero [specialty] within 60 miles." But X is unknown until the data builds. If the verified number is X equals 2, the headline is too soft and we fall back to "Mississippi CAHs are missing N specialty positions across 15 core specialties." The render step picks the headline based on what the data supports. No headline gets hardcoded in advance.

### Local-first, Vercel later

V1 builds locally to `site/`. We verify, edit, sniff-test the audit log, then deploy via Vercel when we're ready to make it public. GitHub Pages won't work for a private repo on the free tier, and we want the repo private during voice review. tenenshealth.com is owned and points at the eventual deploy.

### Cut Medicare Part B PUF from V1 critical path

Demand weighting from the Part B aggregate utilization file is on the stretch list. If the rest of the pipeline lands by tomorrow noon, we add it. If not, V1 ships physician-count-only gap scoring. The headline claim ("zero cardiologists within 60mi") doesn't need demand weighting to be true. Demand weighting is load-bearing only when we're ranking which gap to lead with in cold emails next week.

### Scaffolding choice: Typer CLI, not Jupyter

Considered a notebook-first approach for speed on day 1. Rejected. Notebook code rots in two weeks, can't be tested, can't be reproduced from a clean clone. With Claude Code the package overhead is around 2 hours and we get reproducible builds, a CLI a non-author can run, and a real test suite. Better story for the YC technical breakdown too.

---

## How we guided AI in this session

Short list of moments where Claude's first move was wrong or insufficient and a founder call corrected it. This is the source for the YC application's "how we worked with AI" section.

1. Claude initially kept the email pack in V1 critical path. Founder steer: dashboard tomorrow, email defers.
2. Claude wanted to include surgeon-father network match in V1 cards. Founder steer: defer, that adds value to email outreach more than to a static dashboard.
3. Claude was about to write this audit log in default formal-academic voice. Founder steer: an LLM will read this for YC, must pass as human-authored. Voice rule established with explicit no-AI-tells list.
4. Claude hand-waved geocoding cost as trivial. Founder validated the Nominatim plus ZIP-centroid split and confirmed the under-1% accuracy tradeoff is acceptable inside a 60mi radius.
5. Claude proposed automated verification. Founder pushed for human-in-loop: founder Googles 5 random hospitals before render proceeds. Gate exists at both the technical level (refuses render without signoff entries) and the process level (signoff template requires a Google URL plus a quoted result).
6. Claude's initial homepage assumed the lead headline was "X of 40 CAHs have zero cardiologists" without knowing the data. Founder kept it conditional. The `headline_picker` function chooses based on what the data supports, defaults to softer framing if the strong number doesn't hold up.
7. Claude built the pipeline at the 60-mile radius from the design doc. When the gap matrix came back nearly empty (3 of 600 pairs), Claude flagged it instead of shipping a soft headline. Founder reviewed the 30/45/60 mile curve, picked 30 miles based on the HRSA HPSA convention, and the methodology page was rewritten to show the curve and the reasoning. The dashboard headline went from "won't land" to "32 of 40 MS CAHs have zero rheumatology within 30 miles" honestly, not by fudging the data.
