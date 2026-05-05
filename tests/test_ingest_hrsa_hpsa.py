"""Tests for the HRSA HPSA designation ingest."""

import pandas as pd

from coverage_gap.ingest import hrsa_hpsa


class _FakeResponse:
    def __init__(self, content=b"", status=200):
        self.content = content
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


def test_download_hpsa_returns_cached(tmp_path):
    (tmp_path / "hpsa.csv").write_bytes(b"cached-csv")
    out = hrsa_hpsa.download_hpsa(target_dir=tmp_path, force=False)
    assert out.read_bytes() == b"cached-csv"


def test_download_hpsa_writes_when_force(tmp_path, monkeypatch):
    monkeypatch.setattr(
        hrsa_hpsa.requests, "get",
        lambda url, timeout=None: _FakeResponse(content=b"col1,col2\n1,2\n"),
    )
    out = hrsa_hpsa.download_hpsa(target_dir=tmp_path, force=True)
    assert out.exists()
    assert out.read_bytes() == b"col1,col2\n1,2\n"


def test_filter_ms_hpsa_filters_by_state(tmp_path):
    """Rows whose state column does not mention MS are dropped."""
    csv = tmp_path / "hpsa.csv"
    pd.DataFrame([
        {"State": "MS", "designation": "x"},
        {"State": "AL", "designation": "y"},
        {"State": "MS / TN", "designation": "z"},
    ]).to_csv(csv, index=False)
    out_path = tmp_path / "out.parquet"
    result = hrsa_hpsa.filter_ms_hpsa(csv, output_path=out_path)
    df = pd.read_parquet(result)
    assert sorted(df["State"].tolist()) == ["MS", "MS / TN"]


def test_filter_ms_hpsa_no_state_column_passes_through(tmp_path):
    """When the input has no state-like column, all rows pass through unfiltered."""
    csv = tmp_path / "hpsa.csv"
    pd.DataFrame([{"foo": "1"}, {"foo": "2"}]).to_csv(csv, index=False)
    out_path = tmp_path / "out.parquet"
    result = hrsa_hpsa.filter_ms_hpsa(csv, output_path=out_path)
    df = pd.read_parquet(result)
    assert len(df) == 2
