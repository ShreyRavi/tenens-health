"""Tests for the Typer CLI in coverage_gap.cli."""

import http.server
from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from coverage_gap import cli
from coverage_gap.scoring import GapLevel, GapResult


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def fake_dirs(tmp_path, monkeypatch):
    """Redirect RAW_DIR / PROCESSED_DIR / SITE_DIR (in cli + verification) to a tmp tree."""
    from coverage_gap import verification

    raw = tmp_path / "raw"
    processed = tmp_path / "processed"
    site = tmp_path / "site"
    raw.mkdir()
    processed.mkdir()
    monkeypatch.setattr(cli, "RAW_DIR", raw)
    monkeypatch.setattr(cli, "PROCESSED_DIR", processed)
    monkeypatch.setattr(cli, "SITE_DIR", site)
    # write_build_id reads PROCESSED_DIR from the verification module.
    monkeypatch.setattr(verification, "PROCESSED_DIR", processed)
    return {"raw": raw, "processed": processed, "site": site}


def test_download_command_invokes_each_step(runner, fake_dirs, monkeypatch):
    """The download command should call each of the four ingest helpers in turn."""
    calls = []

    def record(name, ret):
        def f(*a, **k):
            calls.append(name)
            return ret
        return f

    monkeypatch.setattr(cli, "download_nppes", record("nppes", Path("/tmp/nppes.csv")))
    monkeypatch.setattr(cli, "download_cah_pos", record("cah_pos", Path("/tmp/cah_pos.csv")))
    monkeypatch.setattr(cli, "download_zip_centroids", record("zip", Path("/tmp/zip.parquet")))
    monkeypatch.setattr(cli, "download_counties", record("counties_zip", Path("/tmp/counties.zip")))
    monkeypatch.setattr(cli, "filter_ms_counties", record("counties_geo", Path("/tmp/counties.geojson")))

    result = runner.invoke(cli.app, ["download"])
    assert result.exit_code == 0, result.output
    assert calls == ["nppes", "cah_pos", "zip", "counties_zip", "counties_geo"]
    assert "Done" in result.output


def test_build_aborts_when_no_nppes_file(runner, fake_dirs):
    """build should exit non-zero when no NPPES csv has been downloaded."""
    # Empty raw dir -> no npidata_pfile_*.csv.
    result = runner.invoke(cli.app, ["build"])
    assert result.exit_code == 1
    assert "No NPPES file found" in result.output


def test_build_full_flow_with_mocks(runner, fake_dirs, monkeypatch, tmp_path):
    """Exercise the build pipeline end-to-end with light fakes for the heavy steps."""
    raw = fake_dirs["raw"]
    processed = fake_dirs["processed"]

    # Place a stub NPPES csv so the existence check passes.
    (raw / "npidata_pfile_20240101-20240131.csv").write_text("NPI\n1\n")
    # And the cah_pos csv. filter_ms_cahs is patched so contents don't matter.
    (raw / "cah_pos.csv").write_text("PRVDR_NUM\nMS001\n")

    # filter_to_ms_region: write a tiny physicians parquet WITHOUT lat/lon so the
    # geocoding branch runs. zip_centroid is patched to a fixed result.
    physicians_path = processed / "ms_physicians.parquet"

    def fake_filter_ms_region(_csv):
        pd.DataFrame([
            {"NPI": "1000000001", "specialty": "cardiology", "zip5": "38930"},
        ]).to_parquet(physicians_path)
        return physicians_path

    monkeypatch.setattr(cli, "filter_to_ms_region", fake_filter_ms_region)

    cahs_path = processed / "ms_cahs.parquet"

    def fake_filter_ms_cahs(_csv):
        # No lat/lon yet — forces the geocoding branch to run.
        pd.DataFrame([
            # Address geocodes successfully -> source 'nominatim'.
            {"provider_num": "MS001", "name": "Greenwood", "address": "1 Main",
             "city": "Greenwood", "state": "MS", "zip": "38930", "zip5": "38930"},
            # Address fails to geocode but ZIP centroid succeeds -> 'zip_centroid'.
            {"provider_num": "MS002", "name": "Highway 51", "address": "25117 HIGHWAY 51",
             "city": "Rural", "state": "MS", "zip": "39530", "zip5": "39530"},
        ]).to_parquet(cahs_path)
        return cahs_path

    monkeypatch.setattr(cli, "filter_ms_cahs", fake_filter_ms_cahs)

    # geocode_address: returns coords for "1 Main" rows, None for highway rows.
    def fake_geocode(addr):
        return None if "HIGHWAY" in addr else (33.5, -90.17)

    monkeypatch.setattr(cli, "geocode_address", fake_geocode)
    monkeypatch.setattr(cli, "zip_centroid", lambda z: (30.4, -88.9))

    # Replace gap_score with a deterministic stub so we don't depend on geo math.
    def fake_gap_score(cah, specialty, physicians, is_hpsa):
        return GapResult(
            cah_id=str(cah["provider_num"]),
            specialty=specialty,
            physician_count=0 if specialty == "cardiology" else 5,
            level=GapLevel.HIGH if specialty == "cardiology" else GapLevel.COVERED,
            nearest_distance_mi=42.0,
            is_hpsa=is_hpsa,
        )

    monkeypatch.setattr(cli, "gap_score", fake_gap_score)
    # write_aggregates writes JSON files; just assert it was invoked.
    aggregates_calls: list = []

    def fake_write_aggregates(cahs, matrix):
        aggregates_calls.append((len(cahs), len(matrix)))
        return processed / "cahs_summary.json", processed / "county_aggregates.json"

    monkeypatch.setattr(cli, "write_aggregates", fake_write_aggregates)

    result = runner.invoke(cli.app, ["build"])
    assert result.exit_code == 0, result.output
    # gap_matrix.parquet should land in PROCESSED_DIR.
    matrix_path = processed / "gap_matrix.parquet"
    assert matrix_path.exists()
    matrix = pd.read_parquet(matrix_path)
    # 2 CAHs * 15 core specialties.
    assert len(matrix) == 2 * 15
    # build_id was persisted.
    assert (processed / ".build_id").read_text()
    # Aggregates were called with the matrix and the CAH frame.
    assert aggregates_calls and aggregates_calls[0][1] == len(matrix)
    # zip_fallback path printed when at least one CAH used zip_centroid.
    assert "ZIP centroid" in result.output


def test_build_skips_geocoding_when_lat_present(runner, fake_dirs, monkeypatch):
    """If lat/lon and coord_source are already set, the geocoding loop is skipped."""
    raw = fake_dirs["raw"]
    processed = fake_dirs["processed"]
    (raw / "npidata_pfile_20240101.csv").write_text("NPI\n1\n")
    (raw / "cah_pos.csv").write_text("x")

    physicians_path = processed / "ms_physicians.parquet"

    def fake_filter_ms_region(_csv):
        # Already has lat/lon so the second geocoding branch skips too.
        pd.DataFrame([
            {"NPI": "X", "specialty": "cardiology", "zip5": "38930",
             "lat": 33.5, "lon": -90.17},
        ]).to_parquet(physicians_path)
        return physicians_path

    monkeypatch.setattr(cli, "filter_to_ms_region", fake_filter_ms_region)

    cahs_path = processed / "ms_cahs.parquet"

    def fake_filter_ms_cahs(_csv):
        # Already geocoded.
        pd.DataFrame([
            {"provider_num": "MS001", "name": "X", "address": "1 Main",
             "city": "Greenwood", "state": "MS", "zip": "38930", "zip5": "38930",
             "lat": 33.5, "lon": -90.17, "coord_source": "nominatim"},
        ]).to_parquet(cahs_path)
        return cahs_path

    monkeypatch.setattr(cli, "filter_ms_cahs", fake_filter_ms_cahs)

    # If geocode_address is called we want to know.
    sentinel = []
    monkeypatch.setattr(cli, "geocode_address", lambda *a, **k: sentinel.append("called") or (0, 0))
    monkeypatch.setattr(cli, "zip_centroid", lambda z: (0, 0))

    monkeypatch.setattr(
        cli, "gap_score",
        lambda cah, specialty, physicians, is_hpsa: GapResult(
            cah_id="MS001", specialty=specialty, physician_count=1,
            level=GapLevel.MODERATE, nearest_distance_mi=10.0, is_hpsa=False,
        ),
    )
    monkeypatch.setattr(
        cli, "write_aggregates",
        lambda cahs, matrix: (processed / "cahs.json", processed / "counties.json"),
    )

    result = runner.invoke(cli.app, ["build"])
    assert result.exit_code == 0, result.output
    # Geocoding loop didn't run.
    assert sentinel == []


def test_verify_aborts_when_matrix_missing(runner, fake_dirs):
    """verify exits non-zero with a helpful message when no matrix exists."""
    result = runner.invoke(cli.app, ["verify"])
    assert result.exit_code == 1
    assert "No gap matrix found" in result.output


def test_verify_prints_sample(runner, fake_dirs):
    """verify reads the matrix, prints a sample, and exits cleanly."""
    matrix_path = fake_dirs["processed"] / "gap_matrix.parquet"
    pd.DataFrame([
        {"cah_id": "MS001", "cah_name": "Greenwood", "specialty": "cardiology",
         "physician_count": 0, "level": "HIGH", "nearest_distance_mi": 50.0,
         "is_hpsa": False},
        {"cah_id": "MS002", "cah_name": "Magee", "specialty": "neurology",
         "physician_count": 0, "level": "CRITICAL", "nearest_distance_mi": 70.0,
         "is_hpsa": True},
    ]).to_parquet(matrix_path)
    result = runner.invoke(cli.app, ["verify", "--n", "2", "--seed", "1"])
    assert result.exit_code == 0, result.output
    # Either of the two test CAH names appears in the output.
    assert "Greenwood" in result.output or "Magee" in result.output


def test_render_command_prints_output_path(runner, fake_dirs, monkeypatch):
    """render delegates to render_site and surfaces the resulting path."""
    monkeypatch.setattr(cli, "render_site", lambda skip_gate: fake_dirs["site"])
    result = runner.invoke(cli.app, ["render", "--skip-gate"])
    assert result.exit_code == 0, result.output
    assert "Site rendered" in result.output


def test_render_command_surfaces_gate_error(runner, fake_dirs, monkeypatch):
    """A VerificationGateError from render_site results in exit code 1."""
    from coverage_gap.verification import VerificationGateError

    def boom(skip_gate):
        raise VerificationGateError("blocked by gate")

    monkeypatch.setattr(cli, "render_site", boom)
    result = runner.invoke(cli.app, ["render"])
    assert result.exit_code == 1
    assert "blocked by gate" in result.output


def test_serve_aborts_when_site_missing(runner, fake_dirs):
    """serve refuses to start if the site directory does not yet exist."""
    result = runner.invoke(cli.app, ["serve"])
    assert result.exit_code == 1
    assert "No site/" in result.output


def test_serve_starts_and_handles_keyboard_interrupt(
    runner, fake_dirs, monkeypatch, tmp_path
):
    """serve binds an HTTP server and tolerates a Ctrl+C cleanly."""
    fake_dirs["site"].mkdir()
    chdir_calls: list[str] = []
    monkeypatch.setattr(cli.os, "chdir", lambda p: chdir_calls.append(str(p)))

    captured: dict = {}

    class FakeServer:
        def __init__(self, addr, handler):
            self.addr = addr
            self.handler = handler
            captured["instance"] = self

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def serve_forever(self):
            raise KeyboardInterrupt()

    monkeypatch.setattr(cli.socketserver, "TCPServer", FakeServer)
    result = runner.invoke(cli.app, ["serve", "--port", "0"])
    assert result.exit_code == 0, result.output
    assert "Stopped" in result.output
    assert chdir_calls == [str(fake_dirs["site"])]
    # Verify cli.serve actually passed SimpleHTTPRequestHandler to TCPServer.
    assert captured["instance"].handler is http.server.SimpleHTTPRequestHandler
    assert captured["instance"].addr[1] == 0


def test_module_runs_as_main(monkeypatch):
    """The `if __name__ == '__main__': app()` block should be reachable.

    We patch typer.Typer.__call__ before runpy executes the module so the entry
    point runs without dispatching the real CLI parser.
    """
    import runpy

    import typer

    sentinel: list[str] = []
    monkeypatch.setattr(
        typer.Typer, "__call__", lambda self, *a, **k: sentinel.append("called")
    )
    runpy.run_module("coverage_gap.cli", run_name="__main__")
    assert sentinel == ["called"]
