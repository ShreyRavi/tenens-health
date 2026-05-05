"""Tests for county-level rollups built from the gap matrix."""

import json

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Polygon

from coverage_gap.aggregates import (
    assign_cah_to_counties,
    compute_cah_summaries,
    compute_county_aggregates,
    severity_bucket_for,
    write_aggregates,
)


@pytest.fixture
def counties_geojson(tmp_path):
    """Build a tiny two-county GeoJSON. County A covers x in [0,1], County B covers [1,2]."""
    county_a = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    county_b = Polygon([(1, 0), (2, 0), (2, 1), (1, 1)])
    gdf = gpd.GeoDataFrame(
        {
            "fips": ["28001", "28003"],
            "name": ["Adams", "Alcorn"],
            "full_name": ["Adams County", "Alcorn County"],
            "geometry": [county_a, county_b],
        },
        crs="EPSG:4326",
    )
    path = tmp_path / "counties.geojson"
    gdf.to_file(path, driver="GeoJSON")
    return path


@pytest.fixture
def cahs_df():
    return pd.DataFrame([
        # Falls inside county_a (lon=0.5, lat=0.5).
        {"provider_num": "MS001", "name": "A General", "city": "Adamsville",
         "address": "1 Main", "state": "MS", "zip": "38900", "zip5": "38900",
         "lat": 0.5, "lon": 0.5, "coord_source": "nominatim"},
        # Falls inside county_b (lon=1.5).
        {"provider_num": "MS002", "name": "B General", "city": "Alcornville",
         "address": "2 Main", "state": "MS", "zip": "38901", "zip5": "38901",
         "lat": 0.5, "lon": 1.5, "coord_source": "zip_centroid"},
        # Outside any county polygon.
        {"provider_num": "MS003", "name": "Off-Map", "city": "Nowhere",
         "address": "3 Main", "state": "MS", "zip": "38902", "zip5": "38902",
         "lat": 5.0, "lon": 5.0, "coord_source": "nominatim"},
        # Missing coordinates entirely.
        {"provider_num": "MS004", "name": "No Coords", "city": "Lost",
         "address": "4 Main", "state": "MS", "zip": "38903", "zip5": "38903",
         "lat": None, "lon": None, "coord_source": "none"},
    ])


@pytest.fixture
def gap_matrix_df():
    """A small gap matrix covering the four CAHs above."""
    return pd.DataFrame([
        {"cah_id": "MS001", "specialty": "cardiology", "physician_count": 0,
         "level": "HIGH", "nearest_distance_mi": 95.0},
        {"cah_id": "MS001", "specialty": "neurology", "physician_count": 0,
         "level": "CRITICAL", "nearest_distance_mi": 70.0},
        {"cah_id": "MS001", "specialty": "psychiatry", "physician_count": 5,
         "level": "COVERED", "nearest_distance_mi": 10.0},
        {"cah_id": "MS001", "specialty": "ob_gyn", "physician_count": 1,
         "level": "MODERATE", "nearest_distance_mi": 12.0},
        {"cah_id": "MS002", "specialty": "cardiology", "physician_count": 4,
         "level": "COVERED", "nearest_distance_mi": 5.0},
        {"cah_id": "MS002", "specialty": "neurology", "physician_count": 0,
         "level": "HIGH", "nearest_distance_mi": float("nan")},
    ])


def test_severity_bucket_for_low():
    bucket = severity_bucket_for(0)
    assert bucket["key"] == "low"
    assert severity_bucket_for(2)["key"] == "low"


def test_severity_bucket_for_moderate_high_critical():
    assert severity_bucket_for(3)["key"] == "moderate"
    assert severity_bucket_for(7)["key"] == "high"
    assert severity_bucket_for(10)["key"] == "critical"


def test_severity_bucket_for_above_max_returns_last():
    """A count past the highest bucket's max falls through to the last bucket."""
    bucket = severity_bucket_for(999)
    assert bucket["key"] == "critical"


def test_assign_cah_to_counties_uses_point_in_polygon(cahs_df, counties_geojson):
    out = assign_cah_to_counties(cahs_df, counties_geojson=counties_geojson)
    by_id = {row["provider_num"]: row for _, row in out.iterrows()}
    assert by_id["MS001"]["county_fips"] == "28001"
    assert by_id["MS001"]["county_name"] == "Adams"
    assert by_id["MS002"]["county_fips"] == "28003"
    # Outside any polygon -> None (pandas may convert to NaN when joined into an
    # otherwise-string column, so check pd.isna).
    assert pd.isna(by_id["MS003"]["county_fips"])
    # Missing lat/lon -> None.
    assert pd.isna(by_id["MS004"]["county_fips"])
    # Original frame is not mutated.
    assert "county_fips" not in cahs_df.columns


def test_compute_cah_summaries_counts_gaps_and_sorts(cahs_df, gap_matrix_df, counties_geojson):
    cahs = assign_cah_to_counties(cahs_df, counties_geojson=counties_geojson)
    cahs = cahs[cahs["provider_num"].isin(["MS001", "MS002"])]
    out = compute_cah_summaries(cahs, gap_matrix_df)
    by_id = {r["id"]: r for r in out}

    ms001 = by_id["MS001"]
    # 2 of 4 specialties are HIGH or CRITICAL.
    assert ms001["gap_count"] == 2
    # Bucket 'low' covers 0-2 gaps.
    assert ms001["bucket"] == "low"
    # CRITICAL/HIGH come before MODERATE/COVERED in the per-CAH spec list.
    levels = [s["level"] for s in ms001["specialties"]]
    assert levels.index("CRITICAL") < levels.index("MODERATE")
    assert levels.index("HIGH") < levels.index("COVERED")
    # nearest_mi is rounded to one decimal; the COVERED specialty uses 10.0.
    psych = next(s for s in ms001["specialties"] if s["key"] == "psychiatry")
    assert psych["nearest_mi"] == 10.0
    # County metadata flows through.
    assert ms001["county_fips"] == "28001"
    # Top missing is sorted by nearest_distance_mi descending (NaN first).
    assert "Cardiology" in ms001["top_missing"]
    assert "Neurology" in ms001["top_missing"]

    ms002 = by_id["MS002"]
    # NaN nearest_distance_mi must serialize to None.
    neuro = next(s for s in ms002["specialties"] if s["key"] == "neurology")
    assert neuro["nearest_mi"] is None


def test_compute_cah_summaries_handles_missing_optional_fields():
    """A CAH with no name/city/coord_source still produces a stable record."""
    cahs = pd.DataFrame([
        {"provider_num": "MS999", "lat": 0.5, "lon": 0.5},
    ])
    matrix = pd.DataFrame([
        {"cah_id": "MS999", "specialty": "cardiology", "physician_count": 0,
         "level": "HIGH", "nearest_distance_mi": 50.0},
    ])
    out = compute_cah_summaries(cahs, matrix)
    assert out[0]["name"] == ""
    assert out[0]["city"] == ""
    # Defaults applied when columns are absent.
    assert out[0]["coord_source"] == "unknown"
    assert out[0]["county_fips"] is None
    assert out[0]["lat"] == 0.5


def test_compute_county_aggregates_includes_no_data_counties(
    cahs_df, gap_matrix_df, counties_geojson
):
    cahs = assign_cah_to_counties(cahs_df, counties_geojson=counties_geojson)
    out = compute_county_aggregates(cahs, gap_matrix_df, counties_geojson=counties_geojson)
    by_fips = {c["fips"]: c for c in out}

    a = by_fips["28001"]
    assert a["cah_count"] == 1
    # MS001 has 2 HIGH/CRITICAL gaps -> bucket 'low'.
    assert a["max_gaps"] == 2
    assert a["bucket"] == "low"
    assert "MS001" in a["cahs"]
    # Top missing is ranked by count of CAHs lacking the specialty.
    assert "Cardiology" in a["top_missing"]

    b = by_fips["28003"]
    assert b["cah_count"] == 1
    assert b["max_gaps"] == 1
    assert b["bucket"] == "low"


def test_compute_county_aggregates_county_with_no_cahs(tmp_path):
    """Counties with no CAH inside their polygon get a 'none' bucket and gray fill."""
    # No CAH falls inside any polygon — they're all at lon=10.
    cahs = pd.DataFrame([
        {"provider_num": "MS999", "lat": 10.0, "lon": 10.0,
         "county_fips": None, "county_name": None},
    ])
    matrix = pd.DataFrame([
        {"cah_id": "MS999", "specialty": "cardiology", "physician_count": 0,
         "level": "HIGH", "nearest_distance_mi": 50.0},
    ])
    county_a = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    gdf = gpd.GeoDataFrame(
        {"fips": ["28001"], "name": ["Adams"], "full_name": ["Adams County"],
         "geometry": [county_a]},
        crs="EPSG:4326",
    )
    counties_path = tmp_path / "counties.geojson"
    gdf.to_file(counties_path, driver="GeoJSON")
    out = compute_county_aggregates(cahs, matrix, counties_geojson=str(counties_path))
    assert out[0]["cah_count"] == 0
    assert out[0]["bucket"] == "none"
    assert out[0]["color"] == "#d0d0d0"
    assert out[0]["max_gaps"] is None
    assert out[0]["top_missing"] == []
    assert out[0]["cahs"] == []


def test_write_aggregates_emits_two_json_files(
    cahs_df, gap_matrix_df, counties_geojson, monkeypatch, tmp_path
):
    """write_aggregates calls assign_cah_to_counties (which uses PROCESSED_DIR) and
    writes both summary files. Patch PROCESSED_DIR so the geojson lookup finds our
    test file."""
    from coverage_gap import aggregates

    fake_processed = tmp_path / "processed"
    fake_processed.mkdir()
    # The aggregates module reads ms_counties.geojson from PROCESSED_DIR. Copy ours in.
    (fake_processed / "ms_counties.geojson").write_text(counties_geojson.read_text())
    monkeypatch.setattr(aggregates, "PROCESSED_DIR", fake_processed)

    cah_path, county_path = write_aggregates(
        cahs_df.dropna(subset=["lat", "lon"]),
        gap_matrix_df,
    )
    assert cah_path.exists()
    assert county_path.exists()

    cah_records = json.loads(cah_path.read_text())
    county_records = json.loads(county_path.read_text())
    assert {r["id"] for r in cah_records} >= {"MS001", "MS002"}
    assert {c["fips"] for c in county_records} == {"28001", "28003"}


def test_write_aggregates_accepts_explicit_output_dir(
    cahs_df, gap_matrix_df, counties_geojson, monkeypatch, tmp_path
):
    """When output_dir is supplied, the summary files land there; PROCESSED_DIR is
    still used to find ms_counties.geojson."""
    from coverage_gap import aggregates

    fake_processed = tmp_path / "processed"
    fake_processed.mkdir()
    (fake_processed / "ms_counties.geojson").write_text(counties_geojson.read_text())
    monkeypatch.setattr(aggregates, "PROCESSED_DIR", fake_processed)

    out_dir = tmp_path / "explicit_out"
    cah_path, county_path = write_aggregates(
        cahs_df.dropna(subset=["lat", "lon"]),
        gap_matrix_df,
        output_dir=out_dir,
    )
    assert cah_path.parent == out_dir
    assert county_path.parent == out_dir
