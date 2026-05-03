"""Tests for haversine and geocoding utilities."""

import json

import pytest


def test_haversine_zero_distance():
    from coverage_gap.geo import haversine_miles
    assert haversine_miles(40.0, -90.0, 40.0, -90.0) == pytest.approx(0.0, abs=1e-6)


def test_haversine_jackson_to_greenwood():
    # Jackson MS (32.30, -90.18) to Greenwood MS (33.52, -90.17) is roughly 95 miles.
    from coverage_gap.geo import haversine_miles
    d = haversine_miles(32.30, -90.18, 33.52, -90.17)
    assert 80 < d < 105


def test_haversine_one_degree_lat():
    # 1 degree of latitude is roughly 69 miles anywhere on Earth.
    from coverage_gap.geo import haversine_miles
    d = haversine_miles(32.0, -90.0, 33.0, -90.0)
    assert 68 < d < 70


def test_geocode_uses_cache_when_present(tmp_path):
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps({"123 Main St, Greenwood, MS": [33.52, -90.17]}))
    from coverage_gap.geo import geocode_address
    result = geocode_address("123 Main St, Greenwood, MS", cache_path=cache_path, sleep_s=0)
    assert result == (33.52, -90.17)


def test_geocode_cache_records_misses(tmp_path, monkeypatch):
    cache_path = tmp_path / "cache.json"
    from coverage_gap import geo

    def fake_request(query):
        return None

    monkeypatch.setattr(geo, "_nominatim_request", fake_request)
    result = geo.geocode_address("Nonexistent Place 99999", cache_path=cache_path, sleep_s=0)
    assert result is None
    cached = json.loads(cache_path.read_text())
    assert cached["Nonexistent Place 99999"] is None
