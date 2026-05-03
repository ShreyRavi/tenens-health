"""NPPES ingest. Downloads the federal physician registry and filters to MS region."""

import json
import re
import zipfile
from pathlib import Path

import pandas as pd
import requests
from rich.progress import Progress

from coverage_gap.config import (
    ADJACENT_STATES,
    NPPES_BASE_URL,
    NPPES_INDEX_URL,
    PROCESSED_DIR,
    RAW_DIR,
    TARGET_STATE,
)
from coverage_gap.taxonomy import all_codes, code_to_specialties

_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def find_latest_nppes_url(index_url: str = NPPES_INDEX_URL) -> str:
    """Scrape the NPPES download index for the most recent monthly full file.

    CMS publishes a new full file each month; URL contains the month name and year.
    Filename pattern: NPPES_Data_Dissemination_<Month>_<YYYY>[_V<N>].zip.
    """
    resp = requests.get(index_url, timeout=30)
    resp.raise_for_status()
    pattern = re.compile(
        r"NPPES_Data_Dissemination_(" + "|".join(_MONTHS) + r")_(\d{4})(?:_V(\d+))?\.zip",
        re.IGNORECASE,
    )
    matches = list(pattern.finditer(resp.text))
    if not matches:
        raise RuntimeError(f"No NPPES monthly file found at {index_url}")
    # Sort by (year, month_index, version) descending; take the most recent.
    def key(m):
        year = int(m.group(2))
        month = _MONTHS.index(m.group(1).capitalize()) + 1
        version = int(m.group(3) or "1")
        return (year, month, version)
    latest = max(matches, key=key)
    return NPPES_BASE_URL + latest.group(0)

# NPPES has around 330 columns. We keep the ones that matter for gap scoring.
# Note: the practice address is stored as "First Line Business Practice Location Address"
# (no "Line 1" suffix). We use ZIP centroid for physician location so we don't need
# the street address column anyway.
TAXONOMY_SLOTS = 15
KEEP_COLUMNS = [
    "NPI",
    "Provider Last Name (Legal Name)",
    "Provider First Name",
    "Provider Business Practice Location Address City Name",
    "Provider Business Practice Location Address State Name",
    "Provider Business Practice Location Address Postal Code",
    *[f"Healthcare Provider Taxonomy Code_{n}" for n in range(1, TAXONOMY_SLOTS + 1)],
    "Provider License Number_1",
    "Provider License Number State Code_1",
    "NPI Deactivation Date",
    "Provider Enumeration Date",
]


def download_nppes(target_dir: Path | None = None, force: bool = False) -> Path:
    """Download the latest NPPES monthly file and unzip the data CSV. Returns CSV path."""
    target_dir = target_dir or RAW_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    zip_path = target_dir / "nppes.zip"

    if not zip_path.exists() or force:
        url = find_latest_nppes_url()
        with requests.get(url, stream=True, timeout=600) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            with zip_path.open("wb") as f, Progress() as progress:
                task = progress.add_task(f"[cyan]NPPES {Path(url).name}", total=total or None)
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
                    progress.update(task, advance=len(chunk))
    else:
        url = "(cached)"

    with zipfile.ZipFile(zip_path) as zf:
        npidata_name = next(
            n for n in zf.namelist()
            if n.startswith("npidata_pfile_")
            and n.endswith(".csv")
            and "fileheader" not in n.lower()
        )
        zf.extract(npidata_name, target_dir)
        csv_path = target_dir / npidata_name

    versions = target_dir / ".versions.json"
    existing = json.loads(versions.read_text()) if versions.exists() else {}
    existing["nppes"] = {
        "url": url,
        "filename": npidata_name,
        "downloaded_utc": str(pd.Timestamp.utcnow()),
    }
    versions.write_text(json.dumps(existing, indent=2))
    return csv_path


def filter_to_ms_region(csv_path: Path, output_path: Path | None = None) -> Path:
    """Filter NPPES to active providers in MS plus adjacent states.

    Reads the file in chunks because the full file is around 8GB. Output parquet has
    one row per (NPI, specialty) pair, so a multi-specialty physician shows up
    multiple times in the gap matrix.
    """
    output_path = output_path or (PROCESSED_DIR / "ms_physicians.parquet")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    states = {TARGET_STATE, *ADJACENT_STATES}
    tracked_codes = all_codes()

    chunks_out: list[pd.DataFrame] = []
    chunk_iter = pd.read_csv(
        csv_path,
        usecols=KEEP_COLUMNS,
        chunksize=200_000,
        dtype=str,
        low_memory=False,
    )
    for chunk in chunk_iter:
        # Active providers only. Empty deactivation date means active.
        active_mask = (
            chunk["NPI Deactivation Date"].isna()
            | (chunk["NPI Deactivation Date"] == "")
        )
        active = chunk[active_mask]
        in_region = active[
            active["Provider Business Practice Location Address State Name"].isin(states)
        ]
        if in_region.empty:
            continue

        long = in_region.melt(
            id_vars=[
                "NPI",
                "Provider Last Name (Legal Name)",
                "Provider First Name",
                "Provider Business Practice Location Address City Name",
                "Provider Business Practice Location Address State Name",
                "Provider Business Practice Location Address Postal Code",
                "Provider License Number_1",
                "Provider License Number State Code_1",
            ],
            value_vars=[f"Healthcare Provider Taxonomy Code_{n}" for n in range(1, TAXONOMY_SLOTS + 1)],
            var_name="taxonomy_slot",
            value_name="taxonomy_code",
        )
        long = long[long["taxonomy_code"].isin(tracked_codes)]
        if long.empty:
            continue
        long = long.assign(
            specialties=long["taxonomy_code"].apply(code_to_specialties),
        ).explode("specialties").rename(columns={"specialties": "specialty"})
        long = long.dropna(subset=["specialty"])
        chunks_out.append(long)

    if not chunks_out:
        empty = pd.DataFrame(columns=["NPI", "specialty", "lat", "lon", "zip5"])
        empty.to_parquet(output_path)
        return output_path

    combined = pd.concat(chunks_out, ignore_index=True)
    combined = combined.rename(columns={
        "Provider Last Name (Legal Name)": "last_name",
        "Provider First Name": "first_name",
        "Provider Business Practice Location Address City Name": "city",
        "Provider Business Practice Location Address State Name": "state",
        "Provider Business Practice Location Address Postal Code": "zip",
        "Provider License Number_1": "license_number",
        "Provider License Number State Code_1": "license_state",
    })
    combined["zip5"] = combined["zip"].astype(str).str.slice(0, 5)
    combined.to_parquet(output_path, index=False)
    return output_path
