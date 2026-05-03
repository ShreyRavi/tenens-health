"""Typer CLI for the coverage-gap pipeline."""

import http.server
import os
import socketserver
from pathlib import Path

import pandas as pd
import typer
from rich import print as rprint

from coverage_gap.config import (
    CORE_SPECIALTIES,
    EXPECTED_CAH_COUNT,
    PROCESSED_DIR,
    RAW_DIR,
    SITE_DIR,
    TARGET_STATE,
)
from coverage_gap.aggregates import write_aggregates
from coverage_gap.geo import geocode_address, zip_centroid
from coverage_gap.ingest.cah_pos import download_cah_pos, filter_ms_cahs
from coverage_gap.ingest.counties import download_counties, filter_ms_counties
from coverage_gap.ingest.nppes import download_nppes, filter_to_ms_region
from coverage_gap.ingest.zip_centroids import download_zip_centroids
from coverage_gap.render.build import render_site
from coverage_gap.scoring import gap_score
from coverage_gap.verification import (
    VerificationGateError,
    compute_build_id,
    format_for_review,
    pick_random_sample,
    write_build_id,
)

app = typer.Typer(help="Coverage Gap Index for Mississippi Critical Access Hospitals.")


@app.command()
def download() -> None:
    """Download source CMS files, Census ZIP centroids, and Census county boundaries."""
    rprint("[cyan]Downloading NPPES monthly (around 1GB compressed)...[/cyan]")
    nppes_csv = download_nppes()
    rprint(f"  -> {nppes_csv}")
    rprint("[cyan]Downloading CAH Provider of Services...[/cyan]")
    cah_csv = download_cah_pos()
    rprint(f"  -> {cah_csv}")
    rprint("[cyan]Downloading Census ZIP centroid table...[/cyan]")
    zip_pq = download_zip_centroids()
    rprint(f"  -> {zip_pq}")
    rprint("[cyan]Downloading Census county boundaries...[/cyan]")
    counties_zip = download_counties()
    counties_geojson = filter_ms_counties(counties_zip)
    rprint(f"  -> {counties_geojson}")
    rprint("[green]Done. Run `coverage-gap build` next.[/green]")


@app.command()
def build() -> None:
    """Filter, geocode, score. Writes the gap matrix to data/processed/."""
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    rprint("[cyan]Filtering NPPES to Mississippi region...[/cyan]")
    raw_nppes = next(iter(RAW_DIR.glob("npidata_pfile_*.csv")), None)
    if raw_nppes is None:
        rprint("[red]No NPPES file found. Run `coverage-gap download` first.[/red]")
        raise typer.Exit(1)
    physicians_path = filter_to_ms_region(raw_nppes)
    rprint(f"  -> {physicians_path}")

    rprint("[cyan]Filtering CAH POS to Mississippi CAHs...[/cyan]")
    cahs_path = filter_ms_cahs(RAW_DIR / "cah_pos.csv")
    cahs = pd.read_parquet(cahs_path)
    rprint(f"  -> {cahs_path}  ({len(cahs)} hospitals, expected ~{EXPECTED_CAH_COUNT})")

    rprint("[cyan]Geocoding hospitals...[/cyan]")
    if "lat" not in cahs.columns or cahs["lat"].isna().any() or "coord_source" not in cahs.columns:
        coords: list[tuple[float | None, float | None]] = []
        sources: list[str] = []
        zip_fallbacks = 0
        for _, row in cahs.iterrows():
            address = ", ".join(filter(None, [
                str(row.get("address", "") or ""),
                str(row.get("city", "") or ""),
                TARGET_STATE,
            ]))
            result = geocode_address(address) if address.strip(", ") else None
            source = "nominatim" if result else "none"
            if not result:
                # Rural highway-style addresses ("25117 HIGHWAY 51") are unresolvable
                # by Nominatim. Fall back to the hospital's ZIP centroid; a few miles
                # of error is fine inside a 30mi radius.
                zip5 = str(row.get("zip5") or row.get("zip") or "")[:5]
                if zip5:
                    result = zip_centroid(zip5)
                    if result:
                        zip_fallbacks += 1
                        source = "zip_centroid"
            coords.append(result if result else (None, None))
            sources.append(source)
        cahs[["lat", "lon"]] = coords
        cahs["coord_source"] = sources
        cahs.to_parquet(cahs_path, index=False)
        if zip_fallbacks:
            rprint(f"  [yellow]{zip_fallbacks} hospitals fell back to ZIP centroid (rural addresses)[/yellow]")

    rprint("[cyan]Resolving physician ZIP centroids...[/cyan]")
    physicians = pd.read_parquet(physicians_path)
    if "lat" not in physicians.columns:
        coord_pairs = physicians["zip5"].apply(zip_centroid)
        physicians["lat"] = coord_pairs.apply(lambda c: c[0] if c else None)
        physicians["lon"] = coord_pairs.apply(lambda c: c[1] if c else None)
        physicians = physicians.dropna(subset=["lat", "lon"])
        physicians.to_parquet(physicians_path, index=False)

    rprint("[cyan]Scoring gaps...[/cyan]")
    rows = []
    for _, cah in cahs.dropna(subset=["lat", "lon"]).iterrows():
        for spec in CORE_SPECIALTIES:
            result = gap_score(
                cah={
                    "provider_num": cah["provider_num"],
                    "lat": cah["lat"],
                    "lon": cah["lon"],
                },
                specialty=spec,
                physicians=physicians,
                is_hpsa=False,
            )
            rows.append({
                "cah_id": result.cah_id,
                "cah_name": cah.get("name", ""),
                "specialty": result.specialty,
                "physician_count": result.physician_count,
                "level": result.level.value,
                "nearest_distance_mi": result.nearest_distance_mi,
                "is_hpsa": result.is_hpsa,
            })
    matrix = pd.DataFrame(rows)
    matrix_path = PROCESSED_DIR / "gap_matrix.parquet"
    matrix.to_parquet(matrix_path, index=False)

    build_id = compute_build_id(matrix)
    write_build_id(build_id)
    rprint(f"[green]Gap matrix written ({len(matrix)} rows). build_id={build_id}[/green]")

    rprint("[cyan]Computing per-CAH and per-county aggregates for the dashboard map...[/cyan]")
    cahs_with_county = pd.read_parquet(cahs_path)
    cahs_summary_path, county_aggregates_path = write_aggregates(
        cahs_with_county.dropna(subset=["lat", "lon"]),
        matrix,
    )
    rprint(f"  -> {cahs_summary_path}")
    rprint(f"  -> {county_aggregates_path}")
    rprint("[green]Run `coverage-gap verify` next.[/green]")


@app.command()
def verify(
    n: int = typer.Option(5, help="Number of random CAH-specialty pairs to spot check"),
    seed: int = typer.Option(42, help="Random seed for reproducibility"),
) -> None:
    """Print n random CAH x specialty rows for human verification.

    Sign off each in audit/verification-log.md using the template at the top of that
    file. Render is blocked until 5 CONFIRMED entries exist.
    """
    matrix_path = PROCESSED_DIR / "gap_matrix.parquet"
    if not matrix_path.exists():
        rprint("[red]No gap matrix found. Run `coverage-gap build` first.[/red]")
        raise typer.Exit(1)
    matrix = pd.read_parquet(matrix_path)
    sample = pick_random_sample(matrix, n=n, seed=seed)
    rprint(format_for_review(sample))


@app.command()
def render(
    skip_gate: bool = typer.Option(
        False, "--skip-gate", help="Skip verification gate. Local dev only, never for deploy."
    ),
) -> None:
    """Render the static site from the gap matrix into site/."""
    try:
        out = render_site(skip_gate=skip_gate)
    except VerificationGateError as e:
        rprint(f"[red]{e}[/red]")
        raise typer.Exit(1)
    rprint(f"[green]Site rendered to {out}[/green]")


@app.command()
def serve(
    port: int = typer.Option(8000, help="Port to bind"),
) -> None:
    """Serve site/ at localhost for local preview."""
    if not SITE_DIR.exists():
        rprint("[red]No site/ directory. Run `coverage-gap render` first.[/red]")
        raise typer.Exit(1)
    os.chdir(SITE_DIR)
    handler = http.server.SimpleHTTPRequestHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        rprint(f"[green]Serving at http://localhost:{port}[/green]  (Ctrl+C to stop)")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            rprint("[yellow]Stopped.[/yellow]")


if __name__ == "__main__":
    app()
