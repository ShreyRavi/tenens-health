"""Tests for the NPPES ingest."""

import json
import zipfile

import pandas as pd
import pytest

from coverage_gap.ingest import nppes


class _FakeIndexResponse:
    """Stand-in for the NPPES index page response (text-only)."""

    def __init__(self, text=""):
        self.text = text

    def raise_for_status(self):
        return None


class _FakeStreamResponse:
    """Stand-in for the streaming download response."""

    def __init__(self, content=b"", status=200):
        self.content = content
        self.status_code = status
        self.headers = {"content-length": str(len(content))}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_content(self, chunk_size=None):
        # One chunk is enough; the loop body still gets exercised.
        if self.content:
            yield self.content


def test_find_latest_nppes_url_picks_most_recent(monkeypatch):
    """The scraper sorts (year, month, version) descending and returns the top hit."""
    page = (
        "<a href='NPPES_Data_Dissemination_December_2025.zip'>old</a>"
        "<a href='NPPES_Data_Dissemination_April_2026.zip'>middle</a>"
        "<a href='NPPES_Data_Dissemination_April_2026_V2.zip'>v2</a>"
    )
    monkeypatch.setattr(
        nppes.requests, "get", lambda url, timeout=None: _FakeIndexResponse(text=page)
    )
    url = nppes.find_latest_nppes_url()
    assert url.endswith("NPPES_Data_Dissemination_April_2026_V2.zip")


def test_find_latest_nppes_url_no_match_raises(monkeypatch):
    monkeypatch.setattr(
        nppes.requests, "get", lambda url, timeout=None: _FakeIndexResponse(text="<a>nothing</a>")
    )
    with pytest.raises(RuntimeError, match="No NPPES monthly file"):
        nppes.find_latest_nppes_url()


def _make_nppes_zip(zip_path, csv_filename, csv_text):
    """Write a zip containing a single npidata CSV (the parser expects 'npidata_pfile_*.csv')."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr(csv_filename, csv_text)
        # Also include a fileheader to verify the filter ignores it.
        zf.writestr(csv_filename.replace(".csv", "_fileheader.csv"), "ignore me")


def test_download_nppes_uses_cached_zip(tmp_path, monkeypatch):
    """An existing zip is unpacked, with no network call made."""
    raw = tmp_path
    zip_path = raw / "nppes.zip"
    _make_nppes_zip(zip_path, "npidata_pfile_20240101-20240131.csv", "NPI\n1\n")

    # Sanity: any network call should explode.
    def boom(*a, **k):
        raise AssertionError("download should not happen when zip is cached")

    monkeypatch.setattr(nppes.requests, "get", boom)
    monkeypatch.setattr(nppes, "find_latest_nppes_url", boom)

    csv_path = nppes.download_nppes(target_dir=raw, force=False)
    assert csv_path.exists()
    assert csv_path.name == "npidata_pfile_20240101-20240131.csv"
    versions = json.loads((raw / ".versions.json").read_text())
    assert versions["nppes"]["url"] == "(cached)"


def test_download_nppes_downloads_when_missing(tmp_path, monkeypatch):
    """If the zip isn't cached, we hit the network and unpack the result."""
    raw = tmp_path

    monkeypatch.setattr(
        nppes, "find_latest_nppes_url",
        lambda: "https://example/NPPES_Data_Dissemination_April_2026.zip",
    )

    # Build the bytes we'll "stream" back.
    inner_zip = raw / "_inner.zip"
    _make_nppes_zip(inner_zip, "npidata_pfile_20240101-20240131.csv", "NPI\n1\n")
    inner_bytes = inner_zip.read_bytes()
    inner_zip.unlink()

    monkeypatch.setattr(
        nppes.requests, "get",
        lambda *a, **k: _FakeStreamResponse(content=inner_bytes),
    )

    csv_path = nppes.download_nppes(target_dir=raw, force=False)
    assert csv_path.exists()
    versions = json.loads((raw / ".versions.json").read_text())
    assert versions["nppes"]["url"].endswith("April_2026.zip")


@pytest.fixture
def nppes_csv(tmp_path):
    """Build a tiny NPPES CSV with the columns filter_to_ms_region reads."""
    cols = nppes.KEEP_COLUMNS
    # Pull a known cardiology code from the live taxonomy for realism.
    from coverage_gap.taxonomy import load_taxonomy
    cardio_code = load_taxonomy()["cardiology"]["codes"][0]

    def make_row(**overrides):
        row = {c: "" for c in cols}
        row.update(overrides)
        return row

    rows = [
        # MS cardiologist — should be kept.
        make_row(
            **{
                "NPI": "1000000001",
                "Provider Last Name (Legal Name)": "Doe",
                "Provider First Name": "Jane",
                "Provider Business Practice Location Address State Name": "MS",
                "Provider Business Practice Location Address Postal Code": "389300000",
                "Healthcare Provider Taxonomy Code_1": cardio_code,
            }
        ),
        # Out-of-region (CA) — must be dropped.
        make_row(
            **{
                "NPI": "1000000002",
                "Provider Business Practice Location Address State Name": "CA",
                "Healthcare Provider Taxonomy Code_1": cardio_code,
            }
        ),
        # In-region but with an untracked taxonomy code — dropped after melt.
        make_row(
            **{
                "NPI": "1000000003",
                "Provider Business Practice Location Address State Name": "AL",
                "Healthcare Provider Taxonomy Code_1": "0000X0000X",
            }
        ),
        # Deactivated MS provider — dropped because deactivation date is set.
        make_row(
            **{
                "NPI": "1000000004",
                "Provider Business Practice Location Address State Name": "MS",
                "Healthcare Provider Taxonomy Code_1": cardio_code,
                "NPI Deactivation Date": "2024-01-01",
            }
        ),
    ]
    csv_path = tmp_path / "npidata.csv"
    pd.DataFrame(rows, columns=cols).to_csv(csv_path, index=False)
    return csv_path


def test_filter_to_ms_region_keeps_only_active_in_region_tracked(tmp_path, nppes_csv):
    out_path = tmp_path / "ms_phys.parquet"
    result = nppes.filter_to_ms_region(nppes_csv, output_path=out_path)
    df = pd.read_parquet(result)
    # Only the MS cardiology row survives.
    assert list(df["NPI"]) == ["1000000001"]
    assert df.iloc[0]["specialty"] == "cardiology"
    assert df.iloc[0]["zip5"] == "38930"
    # Renamed columns are present.
    for col in ("first_name", "last_name", "city", "state", "zip"):
        assert col in df.columns


def test_filter_to_ms_region_writes_empty_parquet_when_no_matches(tmp_path):
    """If no rows are in-region, the function writes an empty schema-only parquet."""
    cols = nppes.KEEP_COLUMNS
    df = pd.DataFrame([
        {c: "" for c in cols},  # placeholder all-empty row
    ])
    df.loc[0, "Provider Business Practice Location Address State Name"] = "CA"
    df.loc[0, "Healthcare Provider Taxonomy Code_1"] = "9999X9999X"
    csv_path = tmp_path / "in.csv"
    df.to_csv(csv_path, index=False)

    out_path = tmp_path / "out.parquet"
    result = nppes.filter_to_ms_region(csv_path, output_path=out_path)
    out = pd.read_parquet(result)
    assert out.empty
    assert set(out.columns) >= {"NPI", "specialty", "lat", "lon", "zip5"}


def test_filter_to_ms_region_drops_chunk_with_no_tracked_codes(tmp_path):
    """Region match exists but no row carries a tracked taxonomy code."""
    cols = nppes.KEEP_COLUMNS
    rows = [
        {c: "" for c in cols},
    ]
    rows[0]["NPI"] = "9999999999"
    rows[0]["Provider Business Practice Location Address State Name"] = "MS"
    rows[0]["Provider Business Practice Location Address Postal Code"] = "39200"
    rows[0]["Healthcare Provider Taxonomy Code_1"] = "0000X0000X"
    csv_path = tmp_path / "in.csv"
    pd.DataFrame(rows, columns=cols).to_csv(csv_path, index=False)
    out_path = tmp_path / "out.parquet"
    nppes.filter_to_ms_region(csv_path, output_path=out_path)
    out = pd.read_parquet(out_path)
    # No tracked codes -> empty output.
    assert out.empty
