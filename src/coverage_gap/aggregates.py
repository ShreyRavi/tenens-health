"""County-level rollups for the dashboard map.

For each MS county:
- find which CAHs sit inside its boundary (point-in-polygon)
- compute the worst CAH-level gap count in the county
- assign a severity bucket
- list the top missing specialties

Counties without a CAH show as "no data" (gray) on the map.
"""

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point

from coverage_gap.config import PROCESSED_DIR, SEVERITY_BUCKETS
from coverage_gap.taxonomy import specialty_label


def severity_bucket_for(gap_count: int) -> dict:
    """Return the severity bucket dict containing this CAH-level gap count."""
    for bucket in SEVERITY_BUCKETS:
        if bucket["min"] <= gap_count <= bucket["max"]:
            return bucket
    return SEVERITY_BUCKETS[-1]


def assign_cah_to_counties(
    cahs: pd.DataFrame,
    counties_geojson: Path | None = None,
) -> pd.DataFrame:
    """Add county_fips and county_name columns to the CAH dataframe via point-in-polygon."""
    counties_geojson = counties_geojson or (PROCESSED_DIR / "ms_counties.geojson")
    counties = gpd.read_file(counties_geojson)
    cahs = cahs.copy()

    fips_col = []
    name_col = []
    for _, cah in cahs.iterrows():
        if pd.isna(cah.get("lat")) or pd.isna(cah.get("lon")):
            fips_col.append(None)
            name_col.append(None)
            continue
        point = Point(cah["lon"], cah["lat"])
        match = counties[counties.contains(point)]
        if match.empty:
            fips_col.append(None)
            name_col.append(None)
        else:
            fips_col.append(match.iloc[0]["fips"])
            name_col.append(match.iloc[0]["name"])
    cahs["county_fips"] = fips_col
    cahs["county_name"] = name_col
    return cahs


def compute_cah_summaries(
    cahs: pd.DataFrame,
    gap_matrix: pd.DataFrame,
) -> list[dict]:
    """Build the per-CAH side panel records the frontend consumes."""
    out = []
    for _, cah in cahs.iterrows():
        cah_gaps = gap_matrix[gap_matrix["cah_id"] == cah["provider_num"]]
        gap_count = int(cah_gaps["level"].isin(["CRITICAL", "HIGH"]).sum())
        bucket = severity_bucket_for(gap_count)
        missing = cah_gaps[cah_gaps["level"].isin(["CRITICAL", "HIGH"])]
        missing = missing.sort_values("nearest_distance_mi", ascending=False, na_position="first")
        all_specs = []
        for _, g in cah_gaps.iterrows():
            all_specs.append({
                "key": g["specialty"],
                "label": specialty_label(g["specialty"]),
                "level": g["level"],
                "physician_count": int(g["physician_count"]),
                "nearest_mi": (
                    None if pd.isna(g["nearest_distance_mi"])
                    else round(float(g["nearest_distance_mi"]), 1)
                ),
            })
        all_specs.sort(key=lambda s: ["CRITICAL", "HIGH", "MODERATE", "COVERED"].index(s["level"]))
        out.append({
            "id": str(cah["provider_num"]),
            "name": cah.get("name", ""),
            "city": cah.get("city", ""),
            "county_fips": cah.get("county_fips") or None,
            "county_name": cah.get("county_name") or None,
            "lat": float(cah["lat"]) if pd.notna(cah.get("lat")) else None,
            "lon": float(cah["lon"]) if pd.notna(cah.get("lon")) else None,
            "coord_source": cah.get("coord_source") or "unknown",
            "gap_count": gap_count,
            "bucket": bucket["key"],
            "color": bucket["color"],
            "top_missing": [specialty_label(s) for s in missing["specialty"].head(5).tolist()],
            "specialties": all_specs,
        })
    return out


def compute_county_aggregates(
    cahs: pd.DataFrame,
    gap_matrix: pd.DataFrame,
    counties_geojson: Path | None = None,
) -> list[dict]:
    """Build per-county summaries for the choropleth and county-click side panel."""
    counties_geojson = counties_geojson or (PROCESSED_DIR / "ms_counties.geojson")
    counties = gpd.read_file(counties_geojson)
    out = []
    for _, county in counties.iterrows():
        in_county = cahs[cahs["county_fips"] == county["fips"]]
        cah_ids = in_county["provider_num"].tolist()
        if not cah_ids:
            out.append({
                "fips": county["fips"],
                "name": county["name"],
                "full_name": county["full_name"],
                "cah_count": 0,
                "max_gaps": None,
                "bucket": "none",
                "color": "#d0d0d0",
                "top_missing": [],
                "cahs": [],
            })
            continue
        county_gaps = gap_matrix[gap_matrix["cah_id"].isin(cah_ids)]
        per_cah_gap_count = (
            county_gaps[county_gaps["level"].isin(["CRITICAL", "HIGH"])]
            .groupby("cah_id")
            .size()
        )
        max_gaps = int(per_cah_gap_count.max()) if not per_cah_gap_count.empty else 0
        bucket = severity_bucket_for(max_gaps)
        # Top missing across the county: specialties where any CAH has HIGH or CRITICAL.
        missing_counts = (
            county_gaps[county_gaps["level"].isin(["CRITICAL", "HIGH"])]
            .groupby("specialty")
            .size()
            .sort_values(ascending=False)
        )
        top_missing = [specialty_label(s) for s in missing_counts.head(5).index.tolist()]
        out.append({
            "fips": county["fips"],
            "name": county["name"],
            "full_name": county["full_name"],
            "cah_count": len(cah_ids),
            "max_gaps": max_gaps,
            "bucket": bucket["key"],
            "color": bucket["color"],
            "top_missing": top_missing,
            "cahs": [str(x) for x in cah_ids],
        })
    return out


def write_aggregates(
    cahs: pd.DataFrame,
    gap_matrix: pd.DataFrame,
    output_dir: Path | None = None,
) -> tuple[Path, Path]:
    """Write cahs_summary.json and county_aggregates.json into PROCESSED_DIR."""
    output_dir = output_dir or PROCESSED_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    cahs = assign_cah_to_counties(cahs)
    cah_records = compute_cah_summaries(cahs, gap_matrix)
    county_records = compute_county_aggregates(cahs, gap_matrix)

    cahs_path = output_dir / "cahs_summary.json"
    counties_path = output_dir / "county_aggregates.json"
    cahs_path.write_text(json.dumps(cah_records, indent=2))
    counties_path.write_text(json.dumps(county_records, indent=2))
    return cahs_path, counties_path
