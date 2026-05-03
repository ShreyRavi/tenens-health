"""CAH Provider of Services file ingest. Filters to Mississippi Critical Access Hospitals.

The Hospital POS file rotates quarterly. The dataset UUID is stable so we resolve
the current CSV URL via the data.cms.gov catalog (data.json) at runtime.

CAH identification: PRVDR_CTGRY_CD == "01" (Hospital) AND PRVDR_CTGRY_SBTYP_CD == "11" (CAH).
"""

import json
from pathlib import Path

import pandas as pd
import requests

from coverage_gap.config import (
    CAH_CATEGORY_CD,
    CAH_POS_DATASET_UUID,
    CAH_SUBTYPE_CD,
    CMS_DATA_JSON_URL,
    PROCESSED_DIR,
    RAW_DIR,
    TARGET_STATE,
)


def find_latest_pos_csv_url() -> str:
    """Resolve the current Hospital POS CSV URL from the data.cms.gov catalog."""
    resp = requests.get(CMS_DATA_JSON_URL, timeout=60)
    resp.raise_for_status()
    catalog = resp.json()
    for item in catalog.get("dataset", []):
        ident = item.get("identifier", "")
        if CAH_POS_DATASET_UUID in ident:
            for dist in item.get("distribution", []):
                url = dist.get("downloadURL") or dist.get("accessURL", "")
                if url.lower().endswith(".csv"):
                    return url
            break
    raise RuntimeError(
        f"Hospital POS dataset UUID {CAH_POS_DATASET_UUID} not found in CMS catalog. "
        "CMS may have rotated the dataset. Check data.cms.gov/data.json manually."
    )


def download_cah_pos(target_dir: Path | None = None, force: bool = False) -> Path:
    """Download the most recent Hospital POS CSV via the CMS data.json catalog."""
    target_dir = target_dir or RAW_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / "cah_pos.csv"
    if out_path.exists() and not force:
        return out_path

    url = find_latest_pos_csv_url()
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with out_path.open("wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)

    versions = target_dir / ".versions.json"
    existing = json.loads(versions.read_text()) if versions.exists() else {}
    existing["cah_pos"] = {
        "url": url,
        "downloaded_utc": str(pd.Timestamp.utcnow()),
    }
    versions.write_text(json.dumps(existing, indent=2))
    return out_path


def filter_ms_cahs(csv_path: Path, output_path: Path | None = None) -> Path:
    """Filter to MS Critical Access Hospitals and write parquet.

    Uses CMS POS column names: PRVDR_CTGRY_CD == "01", PRVDR_CTGRY_SBTYP_CD == "11",
    STATE_CD == "MS". Output columns are normalized to lowercase: provider_num,
    name, address, city, state, zip.
    """
    output_path = output_path or (PROCESSED_DIR / "ms_cahs.parquet")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(csv_path, dtype=str, low_memory=False)

    df = df[
        (df["STATE_CD"] == TARGET_STATE)
        & (df["PRVDR_CTGRY_CD"] == CAH_CATEGORY_CD)
        & (df["PRVDR_CTGRY_SBTYP_CD"] == CAH_SUBTYPE_CD)
    ]

    rename = {
        "PRVDR_NUM": "provider_num",
        "FAC_NAME": "name",
        "ST_ADR": "address",
        "CITY_NAME": "city",
        "STATE_CD": "state",
        "ZIP_CD": "zip",
    }
    df = df.rename(columns=rename)
    keep = [c for c in ["provider_num", "name", "address", "city", "state", "zip"] if c in df.columns]
    df = df[keep] if keep else df
    df["zip5"] = df["zip"].astype(str).str.slice(0, 5) if "zip" in df.columns else ""
    df.to_parquet(output_path, index=False)
    return output_path
