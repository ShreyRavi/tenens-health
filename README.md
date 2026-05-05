# Tenens Health: Coverage Gap Index

## Live demo

- Production: [https://tenenshealth.com](https://tenenshealth.com)

The live site is the Coverage Gap Index for Mississippi: hospital-level, specialty-level shortage data for all 40 Critical Access Hospitals in the state, built from public CMS sources.

## What this repository is

This repository is a demonstrative artifact, not the company. It is one slide of an eventual pitch deck made interactive: hospital-by-hospital, specialty-by-specialty shortage data for one state, derived from public CMS sources. The Mississippi map serves as the public-data baseline. It is the part of the Tenens Health value proposition that can be shown without operating the agency yet.

The full Tenens Health product is a service-first business with product augmentation, not an app in isolation. The service is an AI-Native locum tenens agency that places physicians where the data shows care is missing. The product is the intelligence layer that learns from those placements and gets sharper over time. Every customer interaction generates proprietary demand-signal data that public datasets cannot produce, and that data is the long-term moat. The pitch a chief medical officer eventually sees is personalized to their hospital and county, drawing on the public-data baseline shown here together with Tenens' own placement data once the agency is operating. This static demo is the public-data baseline only; the personalization layer comes from running the service. The philosophy is straightforward: solve a real access problem through service, augmented by product, rather than the other way around. Incumbents profit from the shortage. Tenens is structured as a Public Benefit Corporation to eliminate it.

## About Tenens Health

Tenens Health is a physician shortage intelligence platform for rural America, paired with an AI-native locum tenens agency that makes the data operational. The company is service-first and product-augmented: the agency does the placement work, and the product layer learns from each placement.

The thesis is straightforward. Rural America has roughly 30 physicians per 100,000 residents, against 263 in cities. The institutions with power to change that ratio (medical schools setting residency counts, HRSA allocating workforce funding, hospital systems planning specialty departments) make multi-year commitments from data that is state-level and years stale. Hospital-level reality hides inside those state and county averages, so the wrong placements get prioritized and the shortage regenerates itself.

The agency is the wedge. Each placement runs the same loop: a chief medical officer describes the specific gap, AI agents surface matched physicians from a curated pool, credentialing is coordinated across state lines, and outcomes are tracked after the assignment closes. Each step generates ground-truth demand data (which specialty, which county, which hospital, which acuity profile, what was actually accepted, what was declined and why) that no public dataset can produce.

The intelligence layer learns from those placements over time. Matching gets sharper as the placement history grows, and the system surfaces predictive shortage signals (which specialty in which geography in which quarter at which acuity) that no incumbent has, because incumbents hoard placement data as a competitive moat. Aggregate, anonymized demand data flows from the intelligence layer to the institutions whose decisions move physician supply on long horizons: HRSA, AAMC, medical school residency planners, and hospital capital planners. That sharing is the go-to-market for the intelligence platform, not a threat to it.

Tenens is structured as a Public Benefit Corporation. Incumbents (CHG Healthcare, AMN Healthcare, Barton Associates) profit from the continuation of the shortage, so they cannot share placement data with HRSA or advocate for reforms (IMLC expansion, J-1 visa waiver optimization, GME funding reform) that would shrink their market. A fiduciary-bound PBC can. The PBC structure is part of the business model, not a values statement.

## Methodology

The methodology below is the public-data baseline. It is what the dashboard at tenenshealth.com computes and renders, and it is the version of the gap picture that can be reproduced from sources anyone can download. A more detailed treatment of each step lives in `src/coverage_gap/render/templates/methodology.html` and on the live site.

### Data sources

The pipeline assembles five public inputs.

- **NPPES** (National Plan and Provider Enumeration System): CMS's authoritative registry of every licensed United States physician, with NUCC taxonomy codes, practice addresses, and license states. Sourced from `download.cms.gov/nppes/`. The full release is roughly 8 GB uncompressed, refreshed monthly. The pipeline filters to active providers in Mississippi and four adjacent states (Louisiana, Alabama, Arkansas, Tennessee) so that catchment-area neighbors are not silently dropped.
- **CAH Provider of Services file**: the federal registry of every Medicare-certified facility, including Critical Access Hospital designation. Sourced from `data.cms.gov`. The current quarterly CSV is resolved programmatically from the data.json catalog and filtered to Mississippi CAHs by category code (`PRVDR_CTGRY_CD = 01`, `PRVDR_CTGRY_SBTYP_CD = 11`).
- **HRSA HPSA designations**: Health Professional Shortage Area designations from the Health Resources and Services Administration. Used to escalate gap severity for CAHs whose county carries a relevant HPSA designation.
- **Census 2020 ZCTA gazetteer**: ZIP Code Tabulation Area centroid coordinates, used to geocode physician practice addresses and as a fallback for hospital addresses Nominatim cannot resolve.
- **Census 2020 county boundaries**: the `cb_2020_us_county_500k` cartographic file, filtered to Mississippi (`STATEFP 28`). Used to render the choropleth layer and to assign each CAH to its county via point-in-polygon intersection.

### Specialty taxonomy mapping

NPPES encodes provider specialty using NUCC (National Uniform Claim Committee) taxonomy codes. The index tracks 15 core specialties chosen to align with HRSA HPSA shortage categories. Each specialty is defined as a set of NUCC codes that includes its relevant subspecialties; the complete mapping is published in `taxonomy.yaml`. The taxonomy is intentionally inclusive, meaning more codes are mapped per specialty than a strict definition would require. The result is a slight overcount of available physicians, which keeps gap claims defensible: any reported gap survives a charitable counting rule.

### Geographic distance

Hospital coordinates are resolved to latitude and longitude via Nominatim (OpenStreetMap). Roughly half of Mississippi CAHs carry rural highway-style addresses (for example, "25117 HIGHWAY 51") that Nominatim cannot geocode; those hospitals fall back to their ZIP centroid. Inside a 30-mile radius, the centroid fallback introduces less than one mile of positional error. CAHs using the centroid fallback are marked with an outlined map symbol so that approximate positions are identifiable. Physician locations are geocoded using the Census 2020 ZCTA gazetteer. All distances are computed using the haversine great-circle formula.

### Why 30 miles

Specialty coverage is measured within a 30-mile radius of each hospital. The threshold is not arbitrary. HRSA applies 30 miles as its standard definition of "reasonable access" in non-metropolitan areas when designating Health Professional Shortage Areas, the federal mechanism that governs loan forgiveness placements, J-1 visa waivers, and related workforce interventions. An earlier draft used 60 miles. At that radius, the catchment areas of Jackson, Memphis, Mobile, and New Orleans begin to overlap with rural Mississippi CAHs, and the gaps that rural patients actually face are masked by metropolitan supply they cannot reach. At 30 miles, the index produces a picture consistent with what rural CMOs report from operational experience.

### Gap scoring

Each (CAH, specialty) pair receives one of four severity classifications, based on the count of active physicians of that specialty within 30 miles of the hospital.

- **CRITICAL**: zero active physicians within 30 miles, and the CAH's county carries an HRSA HPSA designation.
- **HIGH**: zero active physicians within 30 miles.
- **MODERATE**: one or two active physicians within 30 miles.
- **COVERED**: three or more active physicians within 30 miles.

### Map severity buckets

Each CAH is assigned a gap count equal to the number of its 15 tracked specialties classified HIGH or CRITICAL. County shading on the map reflects the highest gap count among all CAHs in the county. The choice to use the maximum, not the mean, is deliberate: a county that contains one severely gapped CAH should not be averaged away by a healthier neighbor, because patients of the gapped facility do not benefit from the neighbor's coverage. Counties without a federally designated CAH are not scored and render gray.

### Verification

Before each dashboard build is published, five hospital-specialty pairs are selected at random and reviewed manually against external sources to confirm or refute the underlying gap claim. Confirmations are logged in `audit/verification-log.md`, keyed to a build identifier derived from a hash of the gap matrix's claim columns. Signoffs issued against a prior build are rejected by the render gate, which means verification is always specific to the data version being published. A wrong "zero cardiologists within 30 miles" claim in a CMO outreach email is the kind of error that ends a hospital relationship before it starts; the gate exists to prevent that specific failure mode.

### Known limitations

- NPPES is refreshed monthly. A physician who relocated to Mississippi recently may not appear in the index until the following release cycle.
- NPPES records practice addresses, not hospital staff privileges or rural call coverage. A physician whose address falls within 30 miles of a CAH is not guaranteed to hold privileges at that hospital. Operationally verified placement data is what closes that gap; the dashboard represents the public-data baseline only.
- Medicare Part B aggregate utilization has not yet been incorporated for demand weighting. That refinement is planned for V2.5.
- ZIP centroid geocoding is slightly conservative for physicians located near a ZIP boundary. Inside a 30-mile radius the resulting measurement error is under one percent.
- Hancock Medical Center (Bay Saint Louis) carries a PO Box ZIP code that does not appear in the Census ZCTA gazetteer, and its street address could not be resolved by Nominatim. It is excluded from the current build.

The baseline shown here represents the public-data picture of where care is and is not, computed conservatively. It does not represent operational reality at the hospital level (privileges, call coverage, real wait times), and it is not the fully personalized analysis a CMO will see once Tenens is operating.

## Local setup

The dashboard can be reproduced end-to-end from a clean checkout in under ten minutes once dependencies are cached.

### Prerequisites

- macOS or Linux. Windows is not tested; WSL2 should work.
- Python 3.11 or newer.
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/), the Python package manager. Install via Homebrew:
  ```
  brew install uv
  ```
  Or via curl:
  ```
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- An internet connection for the CMS, HRSA, and Census downloads.
- About 12 GB of free disk space. The NPPES monthly release alone is roughly 8 GB uncompressed.

### Clone and install

```
git clone https://github.com/ShreyRavi/tenens-health.git
cd tenens-health
uv sync --all-extras
```

`uv sync --all-extras` installs both runtime dependencies and the dev extras (pytest, pytest-cov, ruff).

### Run the pipeline

The CLI is registered as `coverage-gap` and exposes five commands, intended to run in order on a fresh checkout.

```
uv run coverage-gap download    # pulls NPPES, CAH POS, ZIP centroids, county boundaries into data/raw/
uv run coverage-gap build       # filters, geocodes, joins, scores into data/processed/
uv run coverage-gap verify      # prints 5 random CAH x specialty pairs for human signoff
uv run coverage-gap render      # writes the static site into site/
uv run coverage-gap serve       # serves site/ at http://localhost:8000
```

`download` is the long step. Expect several minutes on a typical home connection, dominated by the NPPES file. `build` takes one to two minutes for the geocode pass on the first run, then seconds on subsequent runs because coordinates are cached in the parquet outputs. `verify` is interactive: it prints five hospital-specialty pairs and expects a signoff in `audit/verification-log.md` against the current build identifier before `render` will produce output. `render` and `serve` are seconds each.

Once `serve` is running, open `http://localhost:8000` in a browser. The map should match the production deployment.

### Tests

```
uv run pytest
```

Tests cover the scoring rubric, the verification gate, and the geocoding fallback. The render gate is exercised in tests as a regression guard.

### Deploy

The site is pre-rendered, so deployment is a static upload. Production is on Vercel:

```
cd site
vercel --prod
```

DNS for the apex domain is configured at Namecheap with an A record `@ -> 76.76.21.21` and a CNAME `www -> cname.vercel-dns.com`. While the apex propagates, the site is reachable at `https://tenens-health.vercel.app`.

## How we guided AI

This codebase was scaffolded with Claude Code. The audit trail is deliberate, not decorative. Every Claude judgment that mattered (specialty taxonomy choices, distance threshold, severity thresholds, render gate semantics) is logged in `audit/decisions.md` along with the human input that shaped or corrected it. Every gap claim that goes on the dashboard passes through `audit/verification-log.md` before render, keyed to a build identifier so a signoff cannot silently follow the data forward.

The reason the trail is built into the pipeline rather than kept in a notebook is operational. A wrong gap claim in a CMO email is not a recoverable mistake. The trail is what makes the dashboard claims defensible to the chief medical officer, the academic reader, and any future auditor.

## Status

V1 shipped, Mississippi only. All 50 states next. Locum tenens placement and the broader intelligence platform follow.
