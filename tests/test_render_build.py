"""Tests for the static-site renderer in render/build.py."""

import json

import pandas as pd
import pytest

from coverage_gap.render.build import headline_picker, render_site


def _make_cah_record(
    cah_id: str,
    name: str = "Test Hospital",
    high_specs: list[str] | None = None,
    covered_specs: list[str] | None = None,
    coord_source: str = "nominatim",
) -> dict:
    """Build a minimal cahs_summary record matching the contract aggregates.py emits."""
    high_specs = high_specs or []
    covered_specs = covered_specs or []
    specialties = [
        {"key": k, "label": k.title(), "level": "HIGH", "physician_count": 0,
         "nearest_mi": 50.0}
        for k in high_specs
    ] + [
        {"key": k, "label": k.title(), "level": "COVERED", "physician_count": 5,
         "nearest_mi": 5.0}
        for k in covered_specs
    ]
    return {
        "id": cah_id,
        "name": name,
        "city": "Testville",
        "county_fips": "28001",
        "county_name": "Adams",
        "lat": 33.0,
        "lon": -90.0,
        "coord_source": coord_source,
        "gap_count": len(high_specs),
        "bucket": "low",
        "color": "#27ae60",
        "top_missing": [k.title() for k in high_specs[:5]],
        "specialties": specialties,
    }


def test_headline_picker_empty_returns_default():
    assert headline_picker([]) == {"text": "Coverage Gap Index for Mississippi rural hospitals"}


def test_headline_picker_no_high_critical_specs_returns_default():
    """If no CAH has HIGH or CRITICAL gaps, fall back to the default headline."""
    cahs = [_make_cah_record("MS001", high_specs=[], covered_specs=["cardiology"])]
    assert headline_picker(cahs) == {"text": "Coverage Gap Index for Mississippi rural hospitals"}


def test_headline_picker_picks_most_common_gap_specialty():
    """Picks the specialty that the most CAHs have a HIGH/CRITICAL gap on."""
    cahs = [
        _make_cah_record("MS001", high_specs=["cardiology", "neurology"]),
        _make_cah_record("MS002", high_specs=["cardiology"]),
        _make_cah_record("MS003", high_specs=["neurology"]),
    ]
    headline = headline_picker(cahs)
    # cardiology and neurology both appear twice; max() with ties is implementation-defined
    # but stable: cardiology comes first in iteration order (insertion order in Python 3.7+).
    assert headline["specialty"] in {"cardiology", "neurology"}
    assert headline["n"] == 2
    assert headline["total"] == 3
    # Practitioner singular should match the lookup table.
    if headline["specialty"] == "cardiology":
        assert headline["practitioner"] == "cardiologist"
    else:
        assert headline["practitioner"] == "neurologist"
    assert "rural hospitals" in headline["text"]
    # 30 miles is the configured radius.
    assert "30 miles" in headline["text"]


def test_headline_picker_falls_back_to_specialty_label_when_unknown_key(monkeypatch):
    """A specialty not in the singular practitioner table falls back to its label."""
    from coverage_gap.render import build

    cahs = [{
        "id": "MS001", "name": "X", "city": "Y", "county_fips": "1", "county_name": "Z",
        "lat": 0, "lon": 0, "coord_source": "nominatim", "gap_count": 1,
        "bucket": "low", "color": "#000", "top_missing": [],
        "specialties": [
            {"key": "cardiology", "label": "Cardiology", "level": "HIGH",
             "physician_count": 0, "nearest_mi": 50.0},
        ],
    }]
    # Drop the practitioner override to force fallback.
    monkeypatch.setattr(build, "_PRACTITIONER", {})
    headline = build.headline_picker(cahs)
    assert headline["practitioner"] == "cardiology"


@pytest.fixture
def render_inputs(tmp_path, monkeypatch):
    """Set up a fake PROCESSED_DIR with the data files render_site reads."""
    from coverage_gap.render import build

    processed = tmp_path / "processed"
    processed.mkdir()

    cahs_summary = [
        _make_cah_record("MS001", high_specs=["cardiology", "neurology"]),
        _make_cah_record("MS002", high_specs=["cardiology"], coord_source="zip_centroid"),
    ]
    counties = [
        {"fips": "28001", "name": "Adams", "full_name": "Adams County",
         "cah_count": 2, "max_gaps": 2, "bucket": "low",
         "color": "#27ae60", "top_missing": ["Cardiology"], "cahs": ["MS001", "MS002"]},
        {"fips": "28003", "name": "Alcorn", "full_name": "Alcorn County",
         "cah_count": 0, "max_gaps": None, "bucket": "none",
         "color": "#d0d0d0", "top_missing": [], "cahs": []},
    ]
    (processed / "cahs_summary.json").write_text(json.dumps(cahs_summary))
    (processed / "county_aggregates.json").write_text(json.dumps(counties))
    # Minimal valid GeoJSON. Renderer copies but doesn't parse it.
    (processed / "ms_counties.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": []})
    )

    # Tiny gap_matrix.parquet so render_site exercises the matrix-dump branch.
    matrix = pd.DataFrame([
        {"cah_id": "MS001", "specialty": "cardiology", "physician_count": 0,
         "level": "HIGH", "nearest_distance_mi": 50.0, "is_hpsa": False},
    ])
    matrix.to_parquet(processed / "gap_matrix.parquet")

    monkeypatch.setattr(build, "PROCESSED_DIR", processed)
    return processed


def test_render_site_with_skip_gate_writes_all_files(render_inputs, tmp_path):
    """render_site --skip-gate should produce the four HTML pages plus copied data."""
    out = render_site(output_dir=tmp_path / "site", skip_gate=True, build_id="testbid")
    assert out.exists()
    for fname in ["index.html", "methodology.html", "about.html", "how.html"]:
        assert (out / fname).exists(), f"missing {fname}"
    # Data files were copied across.
    for fname in ["cahs_summary.json", "county_aggregates.json", "ms_counties.geojson",
                  "gap_matrix.json"]:
        assert (out / "data" / fname).exists(), f"missing data/{fname}"
    # Headline substitutions from the cahs_summary should land in index.html.
    index = (out / "index.html").read_text()
    assert "testbid" in index
    # 2 of 2 hospitals lack a cardiologist within 30 miles in our fixture.
    assert "Mississippi rural hospitals" in index
    # Static assets copied (style.css ships in the repo).
    style_dest = out / "static" / "style.css"
    assert style_dest.exists()


def test_render_site_invokes_gate_when_not_skipping(render_inputs, tmp_path, monkeypatch):
    """When skip_gate is False, render_site must call gate_render with the build_id."""
    from coverage_gap.render import build

    calls = []

    def fake_gate(build_id=None, **kwargs):
        calls.append(build_id)

    monkeypatch.setattr(build, "gate_render", fake_gate)
    render_site(output_dir=tmp_path / "site", skip_gate=False, build_id="bid42")
    assert calls == ["bid42"]


def test_render_site_reads_persisted_build_id_when_none(render_inputs, tmp_path, monkeypatch):
    """When build_id is None, render_site falls back to read_build_id()."""
    from coverage_gap.render import build

    monkeypatch.setattr(build, "read_build_id", lambda: "persistedbid")
    monkeypatch.setattr(build, "gate_render", lambda **k: None)
    out = render_site(output_dir=tmp_path / "site", skip_gate=True)
    assert "persistedbid" in (out / "index.html").read_text()


def test_render_site_unknown_build_id_renders(render_inputs, tmp_path, monkeypatch):
    """When no build_id is available anywhere, the template substitutes 'unknown'."""
    from coverage_gap.render import build
    monkeypatch.setattr(build, "read_build_id", lambda: None)
    out = render_site(output_dir=tmp_path / "site", skip_gate=True)
    assert "unknown" in (out / "index.html").read_text()


def test_render_site_without_gap_matrix(render_inputs, tmp_path):
    """If gap_matrix.parquet is absent the renderer must still succeed; just no matrix dump."""
    (render_inputs / "gap_matrix.parquet").unlink()
    out = render_site(output_dir=tmp_path / "site", skip_gate=True, build_id="bid")
    assert (out / "index.html").exists()
    # gap_matrix.json should NOT be emitted.
    assert not (out / "data" / "gap_matrix.json").exists()
