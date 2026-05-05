"""Tests for the CAH POS file ingest."""

import json

import pandas as pd
import pytest

from coverage_gap.config import CAH_POS_DATASET_UUID
from coverage_gap.ingest import cah_pos


class _FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, *, json_data=None, content=b"", status=200):
        self._json = json_data
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self):
        return self._json

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_content(self, chunk_size=None):
        # Yield content in two pieces to exercise the loop body.
        half = max(1, len(self.content) // 2)
        if self.content:
            yield self.content[:half]
            yield self.content[half:]


def test_find_latest_pos_csv_url_returns_csv(monkeypatch):
    """The catalog scan should pick up the first .csv distribution for our UUID."""
    catalog = {
        "dataset": [
            {"identifier": f"https://example/{CAH_POS_DATASET_UUID}",
             "distribution": [
                 {"downloadURL": "https://example/file.json"},
                 {"downloadURL": "https://example/cah.csv"},
             ]},
            {"identifier": "https://example/some-other-id",
             "distribution": [{"downloadURL": "https://example/other.csv"}]},
        ]
    }
    monkeypatch.setattr(
        cah_pos.requests, "get", lambda url, timeout=None: _FakeResponse(json_data=catalog)
    )
    url = cah_pos.find_latest_pos_csv_url()
    assert url == "https://example/cah.csv"


def test_find_latest_pos_csv_url_uses_access_url_when_download_missing(monkeypatch):
    """Falls back to accessURL when downloadURL is absent."""
    catalog = {
        "dataset": [
            {"identifier": f"x/{CAH_POS_DATASET_UUID}",
             "distribution": [{"accessURL": "https://example/access.csv"}]},
        ]
    }
    monkeypatch.setattr(
        cah_pos.requests, "get", lambda url, timeout=None: _FakeResponse(json_data=catalog)
    )
    assert cah_pos.find_latest_pos_csv_url() == "https://example/access.csv"


def test_find_latest_pos_csv_url_raises_when_uuid_absent(monkeypatch):
    """When the UUID isn't in the catalog at all, raise a clear RuntimeError."""
    monkeypatch.setattr(
        cah_pos.requests, "get",
        lambda url, timeout=None: _FakeResponse(json_data={"dataset": []})
    )
    with pytest.raises(RuntimeError, match="not found in CMS catalog"):
        cah_pos.find_latest_pos_csv_url()


def test_find_latest_pos_csv_url_raises_when_no_csv_distribution(monkeypatch):
    """Dataset present but with no .csv distribution -> error."""
    catalog = {
        "dataset": [
            {"identifier": f"x/{CAH_POS_DATASET_UUID}",
             "distribution": [{"downloadURL": "https://example/data.json"}]},
        ]
    }
    monkeypatch.setattr(
        cah_pos.requests, "get", lambda url, timeout=None: _FakeResponse(json_data=catalog)
    )
    with pytest.raises(RuntimeError):
        cah_pos.find_latest_pos_csv_url()


def test_download_cah_pos_returns_cached_when_present(tmp_path):
    """If the target file already exists, no network call happens."""
    target_dir = tmp_path
    (target_dir / "cah_pos.csv").write_text("cached")
    out = cah_pos.download_cah_pos(target_dir=target_dir, force=False)
    assert out.read_text() == "cached"


def test_download_cah_pos_writes_file_and_versions(tmp_path, monkeypatch):
    """Force download streams content to disk and updates .versions.json."""
    monkeypatch.setattr(
        cah_pos, "find_latest_pos_csv_url", lambda: "https://example/cah.csv"
    )

    captured = {}

    def fake_get(url, stream=None, timeout=None):
        captured["url"] = url
        return _FakeResponse(content=b"PROVIDER_NUM,STATE_CD\nMS001,MS\n")

    monkeypatch.setattr(cah_pos.requests, "get", fake_get)
    out = cah_pos.download_cah_pos(target_dir=tmp_path, force=True)
    assert out.exists()
    assert out.read_bytes() == b"PROVIDER_NUM,STATE_CD\nMS001,MS\n"
    versions = json.loads((tmp_path / ".versions.json").read_text())
    assert versions["cah_pos"]["url"] == "https://example/cah.csv"
    assert "downloaded_utc" in versions["cah_pos"]


def test_download_cah_pos_preserves_existing_versions(tmp_path, monkeypatch):
    """A prior .versions.json entry must be merged, not overwritten."""
    (tmp_path / ".versions.json").write_text(json.dumps({"nppes": {"url": "old"}}))
    monkeypatch.setattr(cah_pos, "find_latest_pos_csv_url", lambda: "https://example/cah.csv")
    monkeypatch.setattr(
        cah_pos.requests, "get",
        lambda url, stream=None, timeout=None: _FakeResponse(content=b"x"),
    )
    cah_pos.download_cah_pos(target_dir=tmp_path, force=True)
    versions = json.loads((tmp_path / ".versions.json").read_text())
    # nppes entry is preserved; cah_pos is added.
    assert versions["nppes"] == {"url": "old"}
    assert versions["cah_pos"]["url"] == "https://example/cah.csv"


def test_filter_ms_cahs_keeps_only_ms_cah_rows(tmp_path):
    """Only rows with STATE_CD=MS, PRVDR_CTGRY_CD=01, PRVDR_CTGRY_SBTYP_CD=11 survive."""
    csv = tmp_path / "in.csv"
    pd.DataFrame([
        {"PRVDR_NUM": "MS001", "FAC_NAME": "MS CAH", "ST_ADR": "1 Main",
         "CITY_NAME": "Greenwood", "STATE_CD": "MS", "ZIP_CD": "389300000",
         "PRVDR_CTGRY_CD": "01", "PRVDR_CTGRY_SBTYP_CD": "11"},
        # Different state.
        {"PRVDR_NUM": "AL001", "FAC_NAME": "AL Hosp", "ST_ADR": "2 Main",
         "CITY_NAME": "Mobile", "STATE_CD": "AL", "ZIP_CD": "36601",
         "PRVDR_CTGRY_CD": "01", "PRVDR_CTGRY_SBTYP_CD": "11"},
        # Wrong subtype (general acute, not CAH).
        {"PRVDR_NUM": "MS999", "FAC_NAME": "MS Acute", "ST_ADR": "3 Main",
         "CITY_NAME": "Jackson", "STATE_CD": "MS", "ZIP_CD": "39200",
         "PRVDR_CTGRY_CD": "01", "PRVDR_CTGRY_SBTYP_CD": "00"},
    ]).to_csv(csv, index=False)
    out_path = tmp_path / "out.parquet"
    result = cah_pos.filter_ms_cahs(csv, output_path=out_path)
    df = pd.read_parquet(result)
    assert list(df["provider_num"]) == ["MS001"]
    assert df.iloc[0]["name"] == "MS CAH"
    assert df.iloc[0]["zip5"] == "38930"
    # Renamed columns are present.
    for col in ("provider_num", "name", "address", "city", "state", "zip", "zip5"):
        assert col in df.columns
