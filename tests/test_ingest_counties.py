"""Tests for the Census TIGER counties ingest."""

import json
import zipfile

import geopandas as gpd
import pytest
from shapely.geometry import Polygon

from coverage_gap.ingest import counties


class _FakeResponse:
    def __init__(self, content=b"", status=200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


def test_download_counties_returns_cached(tmp_path):
    (tmp_path / "counties.zip").write_bytes(b"cached-zip")
    out = counties.download_counties(target_dir=tmp_path, force=False)
    assert out.read_bytes() == b"cached-zip"


def test_download_counties_writes_when_force(tmp_path, monkeypatch):
    monkeypatch.setattr(
        counties.requests, "get",
        lambda url, timeout=None: _FakeResponse(content=b"new-zip"),
    )
    out = counties.download_counties(target_dir=tmp_path, force=True)
    assert out.read_bytes() == b"new-zip"


@pytest.fixture
def fake_counties_zip(tmp_path):
    """Write a tiny shapefile zip with two MS counties + one out-of-state county."""
    poly_a = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
    poly_b = Polygon([(1, 0), (2, 0), (2, 1), (1, 1)])
    poly_la = Polygon([(3, 0), (4, 0), (4, 1), (3, 1)])
    gdf = gpd.GeoDataFrame(
        {
            "STATEFP": ["28", "28", "22"],
            "GEOID": ["28001", "28003", "22001"],
            "NAME": ["Adams", "Alcorn", "Acadia"],
            "NAMELSAD": ["Adams County", "Alcorn County", "Acadia Parish"],
            "geometry": [poly_a, poly_b, poly_la],
        },
        crs="EPSG:4269",  # NAD83 — counties.py reprojects to 4326.
    )
    shp_dir = tmp_path / "shp"
    shp_dir.mkdir()
    shp_path = shp_dir / "cb_2020_us_county_500k.shp"
    gdf.to_file(shp_path)
    zip_path = tmp_path / "counties.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in shp_dir.iterdir():
            zf.write(f, arcname=f.name)
    return zip_path


def test_filter_ms_counties_extracts_only_ms(fake_counties_zip, tmp_path, monkeypatch):
    """filter_ms_counties should keep only rows where STATEFP == 28."""
    # Patch PROCESSED_DIR so the summary JSON doesn't pollute the real data dir.
    fake_processed = tmp_path / "processed"
    fake_processed.mkdir()
    monkeypatch.setattr(counties, "PROCESSED_DIR", fake_processed)

    out_path = fake_processed / "ms_counties.geojson"
    result = counties.filter_ms_counties(fake_counties_zip, output_path=out_path)
    assert result == out_path
    assert out_path.exists()

    gj = gpd.read_file(out_path)
    assert sorted(gj["fips"].tolist()) == ["28001", "28003"]
    assert sorted(gj["name"].tolist()) == ["Adams", "Alcorn"]
    # Reprojection should produce WGS84.
    assert gj.crs.to_epsg() == 4326

    summary = json.loads((fake_processed / "ms_counties_summary.json").read_text())
    assert {row["fips"] for row in summary} == {"28001", "28003"}
    # Summary file is intentionally geometry-free.
    assert all("geometry" not in row for row in summary)
