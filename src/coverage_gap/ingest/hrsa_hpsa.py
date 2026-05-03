"""HRSA HPSA designations for Mississippi counties.

Stretch for V1. When pulled, escalates HIGH to CRITICAL where a CAH's county
is HPSA-designated for primary care or specialty.
"""

from pathlib import Path

import pandas as pd
import requests

from coverage_gap.config import HRSA_HPSA_URL, PROCESSED_DIR, RAW_DIR, TARGET_STATE


def download_hpsa(target_dir: Path | None = None, force: bool = False) -> Path:
    target_dir = target_dir or RAW_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    out = target_dir / "hpsa.csv"
    if out.exists() and not force:
        return out
    resp = requests.get(HRSA_HPSA_URL, timeout=120)
    resp.raise_for_status()
    out.write_bytes(resp.content)
    return out


def filter_ms_hpsa(csv_path: Path, output_path: Path | None = None) -> Path:
    output_path = output_path or (PROCESSED_DIR / "ms_hpsa.parquet")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(csv_path, dtype=str, low_memory=False, encoding_errors="replace")
    state_col = next((c for c in df.columns if "state" in c.lower()), None)
    if state_col:
        df = df[df[state_col].str.contains(TARGET_STATE, na=False)]
    df.to_parquet(output_path, index=False)
    return output_path
