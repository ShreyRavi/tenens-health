"""Tests for the Census ZIP centroid table ingest."""

import json
import zipfile

import pandas as pd
import pytest

from coverage_gap.ingest import zip_centroids


class _FakeResponse:
    def __init__(self, content=b"", status=200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


@pytest.fixture
def gazetteer_zip(tmp_path):
    """Build a tiny tab-separated gazetteer file inside a zip."""
    tsv_text = (
        "GEOID\tINTPTLAT\tINTPTLONG\n"
        "38930\t33.5\t-90.17\n"
        "39530\t30.4\t-88.9\n"
        # Row with bad numeric: should be dropped by pd.to_numeric/dropna.
        "00000\tNA\tNA\n"
    )
    z = tmp_path / "gaz.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("2020_Gaz_zcta_national.txt", tsv_text)
    return z


def test_download_zip_centroids_returns_cached(tmp_path, monkeypatch):
    """If the parquet output already exists, no work is done."""
    fake_processed = tmp_path / "processed"
    fake_processed.mkdir()
    (fake_processed / "zip_centroids.parquet").write_bytes(b"cached")
    monkeypatch.setattr(zip_centroids, "PROCESSED_DIR", fake_processed)

    out = zip_centroids.download_zip_centroids(target_dir=tmp_path)
    assert out == fake_processed / "zip_centroids.parquet"
    # File untouched (would otherwise be a real parquet, not "cached").
    assert out.read_bytes() == b"cached"


def test_download_zip_centroids_reuses_cached_zip_when_parquet_missing(
    tmp_path, monkeypatch, gazetteer_zip
):
    """Parquet absent + zip present + force=False: parses the cached zip without network."""
    fake_processed = tmp_path / "processed"
    fake_processed.mkdir()
    monkeypatch.setattr(zip_centroids, "PROCESSED_DIR", fake_processed)

    target_dir = tmp_path / "raw"
    target_dir.mkdir()
    # Place the test gazetteer where download_zip_centroids expects to find a cached zip.
    cached_zip = target_dir / "zip_centroids.zip"
    cached_zip.write_bytes(gazetteer_zip.read_bytes())

    def boom(*a, **k):
        raise AssertionError("network fetch should not happen when cached zip is present")

    monkeypatch.setattr(zip_centroids.requests, "get", boom)
    out = zip_centroids.download_zip_centroids(target_dir=target_dir, force=False)
    assert out.exists()

    df = pd.read_parquet(out)
    # 2 valid rows, the NA row is dropped.
    assert sorted(df["zip"].tolist()) == ["38930", "39530"]
    assert all(len(z) == 5 for z in df["zip"])

    versions = json.loads((target_dir / ".versions.json").read_text())
    assert versions["zip_centroids"]["rows"] == 2


def test_download_zip_centroids_downloads_when_zip_missing(
    tmp_path, monkeypatch, gazetteer_zip
):
    """When neither parquet nor zip exists, fetch via requests.get and parse."""
    fake_processed = tmp_path / "processed"
    fake_processed.mkdir()
    monkeypatch.setattr(zip_centroids, "PROCESSED_DIR", fake_processed)
    target_dir = tmp_path / "raw"
    # Leave target_dir empty so the fetcher runs.

    monkeypatch.setattr(
        zip_centroids.requests, "get",
        lambda url, timeout=None: _FakeResponse(content=gazetteer_zip.read_bytes()),
    )
    out = zip_centroids.download_zip_centroids(target_dir=target_dir)
    df = pd.read_parquet(out)
    assert len(df) == 2
