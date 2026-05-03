"""Paths and constants for the Coverage Gap Index pipeline."""

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
SITE_DIR = PROJECT_ROOT / "site"
AUDIT_DIR = PROJECT_ROOT / "audit"

TARGET_STATE = "MS"
ADJACENT_STATES = ["LA", "AL", "AR", "TN"]
# 30 miles matches the HRSA HPSA "reasonable access" threshold for non-metro
# specialty shortage designation. The 60-mile radius from the original design
# pulled in Jackson, Memphis, Mobile, and New Orleans metros which masked gaps.
RADIUS_MILES = 30.0

# Mississippi has 40 federally designated CAHs (per CMS POS file).
EXPECTED_CAH_COUNT = 40

# NPPES is published monthly. We scrape the index for the latest filename
# rather than hardcoding a URL that rotates. See ingest/nppes.py.
NPPES_INDEX_URL = "https://download.cms.gov/nppes/NPI_Files.html"
NPPES_BASE_URL = "https://download.cms.gov/nppes/"

# CAH POS file is on data.cms.gov. Hospital dataset UUID is stable; the actual
# CSV URL rotates quarterly, so we resolve it via the data.json catalog.
# See ingest/cah_pos.py.
CMS_DATA_JSON_URL = "https://data.cms.gov/data.json"
CAH_POS_DATASET_UUID = "8ba0f9b4-9493-4aa0-9f82-44ea9468d1b5"

# CAH identification: hospital category code plus CAH subtype.
CAH_CATEGORY_CD = "01"
CAH_SUBTYPE_CD = "11"

HRSA_HPSA_URL = "https://data.hrsa.gov/Data/Download?dataDownloadTypeId=BCD"

# Census 2020 ZCTA gazetteer, one file per US ZIP code with INTPTLAT/INTPTLONG.
ZIP_CENTROIDS_URL = (
    "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/"
    "2020_Gazetteer/2020_Gaz_zcta_national.zip"
)

# Census 2020 cartographic boundary file for US counties at 1:500k resolution.
# We download all US counties then filter to MS (STATEFP=28).
COUNTIES_URL = (
    "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_county_500k.zip"
)
TARGET_STATE_FIPS = "28"  # Mississippi

# Aggregate severity buckets for the dashboard map. Tuned against the V1 30-mile
# build where the average MS CAH has gaps in roughly 5-7 of 15 core specialties.
SEVERITY_BUCKETS = [
    {"key": "low", "label": "0-2 gaps", "min": 0, "max": 2, "color": "#27ae60"},
    {"key": "moderate", "label": "3-5 gaps", "min": 3, "max": 5, "color": "#f1c40f"},
    {"key": "high", "label": "6-9 gaps", "min": 6, "max": 9, "color": "#e67e22"},
    {"key": "critical", "label": "10+ gaps", "min": 10, "max": 15, "color": "#c0392b"},
]
SEVERITY_NO_DATA_COLOR = "#d0d0d0"

# 15 specialties tracked in the dashboard. See taxonomy.yaml for code mapping.
CORE_SPECIALTIES = [
    "general_surgery",
    "orthopedic_surgery",
    "cardiology",
    "pulmonology_critical_care",
    "neurology",
    "psychiatry",
    "ob_gyn",
    "oncology",
    "gastroenterology",
    "urology",
    "rheumatology",
    "endocrinology",
    "nephrology",
    "dermatology",
    "emergency_medicine",
]
