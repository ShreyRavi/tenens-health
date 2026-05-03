"""Mississippi county boundaries from Census TIGER cartographic files.

Downloads cb_2020_us_county_500k.zip (~4MB), extracts MS counties (STATEFP=28),
and writes data/processed/ms_counties.geojson for the dashboard map.
"""

import json
import zipfile
from pathlib import Path

import geopandas as gpd
import requests

from coverage_gap.config import COUNTIES_URL, PROCESSED_DIR, RAW_DIR, TARGET_STATE_FIPS


def download_counties(target_dir: Path | None = None, force: bool = False) -> Path:
    target_dir = target_dir or RAW_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    out = target_dir / "counties.zip"
    if out.exists() and not force:
        return out
    resp = requests.get(COUNTIES_URL, timeout=120)
    resp.raise_for_status()
    out.write_bytes(resp.content)
    return out


def filter_ms_counties(zip_path: Path, output_path: Path | None = None) -> Path:
    """Extract MS counties from the national TIGER file, write GeoJSON."""
    output_path = output_path or (PROCESSED_DIR / "ms_counties.geojson")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(zip_path.parent / "counties_unzip")
    extract_dir = zip_path.parent / "counties_unzip"
    shp_path = next(extract_dir.glob("*.shp"))

    gdf = gpd.read_file(shp_path)
    ms = gdf[gdf["STATEFP"] == TARGET_STATE_FIPS].copy()
    ms = ms[["GEOID", "NAME", "NAMELSAD", "geometry"]].rename(
        columns={"GEOID": "fips", "NAME": "name", "NAMELSAD": "full_name"}
    )
    # Reproject to WGS84 lat/lon for web mapping; TIGER files ship in NAD83.
    ms = ms.to_crs(epsg=4326)
    ms.to_file(output_path, driver="GeoJSON")

    # Also write a slimmed JSON without geometry for joins.
    summary = ms.drop(columns=["geometry"]).to_dict(orient="records")
    (PROCESSED_DIR / "ms_counties_summary.json").write_text(json.dumps(summary, indent=2))
    return output_path
