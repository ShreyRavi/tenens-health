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


def test_nominatim_request_returns_first_result(monkeypatch):
    """The internal _nominatim_request returns the first hit from the API."""
    from coverage_gap import geo

    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return [{"lat": "32.30", "lon": "-90.18", "display_name": "X"}]

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(geo.requests, "get", fake_get)
    result = geo._nominatim_request("Jackson MS")
    assert result == {"lat": "32.30", "lon": "-90.18", "display_name": "X"}
    assert captured["params"]["q"] == "Jackson MS"
    assert captured["headers"]["User-Agent"] == geo.USER_AGENT


def test_nominatim_request_returns_none_for_empty_results(monkeypatch):
    from coverage_gap import geo

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return []

    monkeypatch.setattr(geo.requests, "get", lambda *a, **k: FakeResponse())
    assert geo._nominatim_request("Nowhere") is None


def test_geocode_address_writes_coords_on_hit(tmp_path, monkeypatch):
    """A successful Nominatim hit records (lat, lon) into the cache file."""
    from coverage_gap import geo

    monkeypatch.setattr(
        geo,
        "_nominatim_request",
        lambda q: {"lat": "33.5", "lon": "-90.17"},
    )
    cache_path = tmp_path / "cache.json"
    result = geo.geocode_address("Greenwood, MS", cache_path=cache_path, sleep_s=0)
    assert result == (33.5, -90.17)
    cached = json.loads(cache_path.read_text())
    assert cached["Greenwood, MS"] == [33.5, -90.17]


def test_geocode_address_handles_request_exceptions(tmp_path, monkeypatch):
    """A raising _nominatim_request must be caught and recorded as a miss."""
    from coverage_gap import geo

    def explode(query):
        raise RuntimeError("network down")

    monkeypatch.setattr(geo, "_nominatim_request", explode)
    cache_path = tmp_path / "cache.json"
    result = geo.geocode_address("Anywhere", cache_path=cache_path, sleep_s=0)
    assert result is None
    assert json.loads(cache_path.read_text())["Anywhere"] is None


def test_geocode_address_sleeps_when_sleep_s_positive(tmp_path, monkeypatch):
    """sleep_s > 0 should call time.sleep with the requested duration."""
    from coverage_gap import geo

    monkeypatch.setattr(geo, "_nominatim_request", lambda q: {"lat": "1", "lon": "2"})
    sleep_calls: list[float] = []
    monkeypatch.setattr(geo.time, "sleep", lambda s: sleep_calls.append(s))
    cache_path = tmp_path / "cache.json"
    geo.geocode_address("X", cache_path=cache_path, sleep_s=0.05)
    assert sleep_calls == [0.05]


@pytest.fixture(autouse=True)
def _reset_zip_centroid_cache():
    """Reset the module-level zip centroid cache before AND after each test
    so cached state never leaks across the suite."""
    from coverage_gap import geo
    geo._zip_centroid_cache = None
    yield
    geo._zip_centroid_cache = None


def test_zip_centroid_returns_none_for_none_or_nan():
    from coverage_gap.geo import zip_centroid
    assert zip_centroid(None) is None
    assert zip_centroid(float("nan")) is None


def test_zip_centroid_lookup_from_parquet(tmp_path):
    """zip_centroid loads a parquet table and returns the matching centroid."""
    import pandas as pd

    from coverage_gap.geo import zip_centroid

    table = tmp_path / "zip_centroids.parquet"
    pd.DataFrame(
        {"zip": ["38930", "39530"], "lat": [33.5, 30.4], "lng": [-90.17, -88.9]}
    ).to_parquet(table, index=False)

    assert zip_centroid("38930", table_path=table) == (33.5, -90.17)
    # Subsequent calls reuse the in-memory cache (no table_path needed).
    assert zip_centroid("39530") == (30.4, -88.9)
    # Padding short ZIPs to 5 digits is part of the contract.
    # Reset between sub-cases so the new parquet is re-read instead of stale-cached.
    from coverage_gap import geo as _geo
    _geo._zip_centroid_cache = None
    pd.DataFrame({"zip": ["01234"], "lat": [40.0], "lng": [-71.0]}).to_parquet(table, index=False)
    assert zip_centroid("1234", table_path=table) == (40.0, -71.0)
    # Unknown ZIPs return None even when cache is populated.
    assert zip_centroid("99999") is None


def test_zip_centroid_missing_table_returns_none(tmp_path):
    """When the parquet table is missing, lookups return None and don't crash."""
    from coverage_gap.geo import zip_centroid
    nowhere = tmp_path / "does_not_exist.parquet"
    assert zip_centroid("38930", table_path=nowhere) is None
