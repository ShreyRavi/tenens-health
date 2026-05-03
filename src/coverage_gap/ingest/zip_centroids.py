"""US ZIP code centroid table.

Source is the Census Bureau 2020 ZCTA Gazetteer file. One row per ZCTA with
INTPTLAT and INTPTLONG. Inside a 60-mile radius centroid error is under 1%, which
we use for physician practice address lookup. Documented in methodology.html.
"""

import json
import zipfile
from pathlib import Path

import pandas as pd
import requests

from coverage_gap.config import PROCESSED_DIR, RAW_DIR, ZIP_CENTROIDS_URL


def download_zip_centroids(target_dir: Path | None = None, force: bool = False) -> Path:
    """Download Census 2020 ZCTA gazetteer and write parquet ready for geo.zip_centroid()."""
    target_dir = target_dir or RAW_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / "zip_centroids.zip"
    out_path = PROCESSED_DIR / "zip_centroids.parquet"

    if not out_path.exists() or force:
        if not zip_path.exists() or force:
            resp = requests.get(ZIP_CENTROIDS_URL, timeout=120)
            resp.raise_for_status()
            zip_path.write_bytes(resp.content)

        with zipfile.ZipFile(zip_path) as zf:
            tsv_name = next(n for n in zf.namelist() if n.endswith(".txt"))
            with zf.open(tsv_name) as fh:
                df = pd.read_csv(fh, sep="\t", dtype={"GEOID": str})

        df.columns = [c.strip() for c in df.columns]
        # Census headers can have trailing whitespace; normalize.
        col_zip = next(c for c in df.columns if c.upper().startswith("GEOID"))
        col_lat = next(c for c in df.columns if c.upper().startswith("INTPTLAT"))
        col_lng = next(c for c in df.columns if c.upper().startswith("INTPTLONG"))

        out = pd.DataFrame({
            "zip": df[col_zip].astype(str).str.zfill(5),
            "lat": pd.to_numeric(df[col_lat], errors="coerce"),
            "lng": pd.to_numeric(df[col_lng], errors="coerce"),
        }).dropna()
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        out.to_parquet(out_path, index=False)

        versions = target_dir / ".versions.json"
        existing = json.loads(versions.read_text()) if versions.exists() else {}
        existing["zip_centroids"] = {
            "url": ZIP_CENTROIDS_URL,
            "downloaded_utc": str(pd.Timestamp.utcnow()),
            "rows": len(out),
        }
        versions.write_text(json.dumps(existing, indent=2))

    return out_path
