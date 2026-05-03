"""V2 static site renderer using Jinja2.

Single-page MapLibre dashboard. The CAH detail content from V1 becomes side panel
content rendered client-side from cahs_summary.json. methodology.html and about.html
remain as separate static pages.

Data shipped to the client:
- /data/ms_counties.geojson    Census TIGER MS county polygons
- /data/county_aggregates.json Per-county severity rollup
- /data/cahs.json              Per-CAH summary with all 15 specialty rows
- /data/gap_matrix.json        Raw scoring data, for transparency
"""

import shutil
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from coverage_gap.config import (
    CORE_SPECIALTIES,
    PACKAGE_DIR,
    PROCESSED_DIR,
    RADIUS_MILES,
    SEVERITY_BUCKETS,
    SITE_DIR,
)
from coverage_gap.taxonomy import specialty_label
from coverage_gap.verification import gate_render, read_build_id

TEMPLATES_DIR = PACKAGE_DIR / "render" / "templates"
STATIC_DIR = PACKAGE_DIR / "render" / "static"


# Singular practitioner names so the headline reads naturally:
# "have no rheumatologist" beats "have no rheumatology specialist".
_PRACTITIONER = {
    "general_surgery": "general surgeon",
    "orthopedic_surgery": "orthopedic surgeon",
    "cardiology": "cardiologist",
    "pulmonology_critical_care": "pulmonologist",
    "neurology": "neurologist",
    "psychiatry": "psychiatrist",
    "ob_gyn": "obstetrician-gynecologist",
    "oncology": "oncologist",
    "gastroenterology": "gastroenterologist",
    "urology": "urologist",
    "rheumatology": "rheumatologist",
    "endocrinology": "endocrinologist",
    "nephrology": "nephrologist",
    "dermatology": "dermatologist",
    "emergency_medicine": "emergency physician",
}


def headline_picker(cahs_summary: list[dict]) -> dict:
    """Single-specialty headline. Picks the specialty that the most CAHs lack.

    Format: "X of Y Mississippi rural hospitals have no [practitioner] within Z miles"
    A specific practitioner name lands harder than aggregate framing.
    """
    if not cahs_summary:
        return {"text": "Coverage Gap Index for Mississippi rural hospitals"}
    total = len(cahs_summary)
    radius = int(RADIUS_MILES)

    spec_counts: dict[str, int] = {}
    for cah in cahs_summary:
        for s in cah["specialties"]:
            if s["level"] in ("HIGH", "CRITICAL"):
                spec_counts[s["key"]] = spec_counts.get(s["key"], 0) + 1

    if not spec_counts:
        return {"text": "Coverage Gap Index for Mississippi rural hospitals"}

    top_spec, top_count = max(spec_counts.items(), key=lambda x: x[1])
    practitioner = _PRACTITIONER.get(top_spec, specialty_label(top_spec).lower())
    return {
        "text": (
            f"{top_count} of {total} Mississippi rural hospitals "
            f"have no {practitioner} within {radius} miles"
        ),
        "n": top_count,
        "total": total,
        "specialty": top_spec,
        "practitioner": practitioner,
    }


def render_site(
    output_dir: Path | None = None,
    skip_gate: bool = False,
    build_id: str | None = None,
) -> Path:
    """Render the V2 single-page dashboard to output_dir."""
    build_id = build_id or read_build_id()
    if not skip_gate:
        gate_render(build_id=build_id)

    output_dir = output_dir or SITE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "static").mkdir(exist_ok=True)
    (output_dir / "data").mkdir(exist_ok=True)

    if STATIC_DIR.exists():
        for f in STATIC_DIR.iterdir():
            if f.is_file():
                shutil.copy(f, output_dir / "static" / f.name)

    cahs_summary_path = PROCESSED_DIR / "cahs_summary.json"
    counties_path = PROCESSED_DIR / "county_aggregates.json"
    counties_geojson = PROCESSED_DIR / "ms_counties.geojson"
    gap_matrix_path = PROCESSED_DIR / "gap_matrix.parquet"
    for src in [cahs_summary_path, counties_path, counties_geojson]:
        shutil.copy(src, output_dir / "data" / src.name)
    if gap_matrix_path.exists():
        df = pd.read_parquet(gap_matrix_path)
        (output_dir / "data" / "gap_matrix.json").write_text(df.to_json(orient="records"))

    import json
    cahs_summary = json.loads(cahs_summary_path.read_text())
    counties = json.loads(counties_path.read_text())
    headline = headline_picker(cahs_summary)
    counties_with_data = sum(1 for c in counties if c["bucket"] != "none")
    cah_fallback_count = sum(1 for c in cahs_summary if c["coord_source"] == "zip_centroid")

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
    )
    common = {
        "build_id": build_id or "unknown",
        "build_date": "2026-05-04",
        "radius_mi": int(RADIUS_MILES),
        "specialty_count": len(CORE_SPECIALTIES),
        "severity_buckets": SEVERITY_BUCKETS,
    }

    rendered = {
        "index.html": env.get_template("index.html").render(
            headline=headline,
            cah_count=len(cahs_summary),
            counties_count=len(counties),
            counties_with_data=counties_with_data,
            cah_fallback_count=cah_fallback_count,
            **common,
        ),
        "methodology.html": env.get_template("methodology.html").render(**common),
        "about.html": env.get_template("about.html").render(**common),
    }
    for filename, html in rendered.items():
        (output_dir / filename).write_text(html)

    return output_dir
