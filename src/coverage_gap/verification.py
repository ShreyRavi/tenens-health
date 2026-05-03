"""Verification gate before render.

Picks 5 random CAHs from the gap matrix, prints their claims for human review, and
refuses render until corresponding signoff entries appear in audit/verification-log.md.

The build_id is a SHA256 of the gap matrix's claim columns (cah_id, specialty,
physician_count, level). Stable across schema additions, changes when claims change.
Persisted to data/processed/.build_id at build time.
"""

import hashlib
import json
import random
import re
from pathlib import Path

import pandas as pd

from coverage_gap.config import AUDIT_DIR, PROCESSED_DIR, RADIUS_MILES


class VerificationGateError(Exception):
    """Raised when render is attempted without enough confirmed signoffs."""


def compute_build_id(gap_matrix: pd.DataFrame) -> str:
    """Hash the gap matrix's claim-bearing columns into a stable build identifier.

    Two builds produce the same id iff every (cah_id, specialty, physician_count, level)
    tuple matches. Schema additions (new columns) don't change the id; data changes do.
    """
    cols = ["cah_id", "specialty", "physician_count", "level"]
    if not all(c in gap_matrix.columns for c in cols):
        raise ValueError(f"gap_matrix missing claim columns: {cols}")
    claims = (
        gap_matrix[cols]
        .sort_values(["cah_id", "specialty"])
        .to_dict(orient="records")
    )
    payload = json.dumps(claims, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def write_build_id(build_id: str, output_dir: Path | None = None) -> Path:
    output_dir = output_dir or PROCESSED_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / ".build_id"
    out.write_text(build_id)
    return out


def read_build_id(output_dir: Path | None = None) -> str | None:
    output_dir = output_dir or PROCESSED_DIR
    path = output_dir / ".build_id"
    if not path.exists():
        return None
    return path.read_text().strip() or None


def pick_random_sample(
    gap_matrix: pd.DataFrame,
    n: int = 5,
    seed: int = 42,
) -> pd.DataFrame:
    """Pick n random CAH x specialty rows weighted toward CRITICAL and HIGH levels.

    Deterministic given seed, so the same sample is reproducible across runs.
    """
    if gap_matrix.empty:
        raise ValueError("Empty gap matrix, cannot sample")
    rng = random.Random(seed)
    pool = gap_matrix[gap_matrix["level"].isin(["CRITICAL", "HIGH"])]
    if len(pool) < n:
        pool = gap_matrix
    indices = rng.sample(list(pool.index), min(n, len(pool)))
    return pool.loc[indices]


def format_for_review(
    sample: pd.DataFrame,
    radius_mi: float | None = None,
    build_id: str | None = None,
) -> str:
    radius = int(radius_mi if radius_mi is not None else RADIUS_MILES)
    bid = build_id or read_build_id() or "unknown"
    lines = [
        f"Verification sample for build {bid}. Google each, confirm or refute:\n",
    ]
    for i, (_, row) in enumerate(sample.iterrows(), start=1):
        name = row.get("cah_name") or row["cah_id"]
        lines.append(
            f"  {i}. {name}: {row['physician_count']} {row['specialty']} within {radius} miles "
            f"({row['level']})"
        )
    lines.append(
        f"\nWrite signoffs into {AUDIT_DIR / 'verification-log.md'} with `Build: {bid}`. "
        "Render is blocked until 5 entries are CONFIRMED for this build."
    )
    return "\n".join(lines)


_SIGNOFF_HEADER_RE = re.compile(r"^## \d{4}-\d{2}-\d{2}", re.MULTILINE)
_RESULT_RE = re.compile(r"Result:\s*(CONFIRMED|DISPUTED|INCONCLUSIVE)", re.IGNORECASE)
_BUILD_RE = re.compile(r"^Build:\s*(\S+)\s*$", re.MULTILINE)


def count_recent_signoffs(
    log_path: Path | None = None,
    build_id: str | None = None,
) -> int:
    """Count CONFIRMED signoffs in the verification log.

    If build_id is given, only count entries whose `Build:` field matches exactly.
    Without a build_id, counts all CONFIRMED entries (legacy behavior; not safe for
    cross-build verification).
    """
    log_path = log_path or (AUDIT_DIR / "verification-log.md")
    if not log_path.exists():
        return 0
    text = log_path.read_text()
    entries = _SIGNOFF_HEADER_RE.split(text)[1:]
    confirmed = 0
    for entry in entries:
        if build_id is not None:
            build_match = _BUILD_RE.search(entry)
            if not build_match or build_match.group(1) != build_id:
                continue
        result_match = _RESULT_RE.search(entry)
        if result_match and result_match.group(1).upper() == "CONFIRMED":
            confirmed += 1
    return confirmed


def gate_render(
    min_signoffs: int = 5,
    build_id: str | None = None,
    log_path: Path | None = None,
) -> None:
    """Refuse render if fewer than min_signoffs CONFIRMED entries exist for the build.

    If build_id is None, falls back to reading data/processed/.build_id. If still
    missing, raises VerificationGateError to enforce that a build must produce one.
    """
    if build_id is None:
        build_id = read_build_id()
    if build_id is None:
        raise VerificationGateError(
            "No build_id available. Run `coverage-gap build` to produce one before render."
        )
    count = count_recent_signoffs(log_path=log_path, build_id=build_id)
    if count < min_signoffs:
        raise VerificationGateError(
            f"Render blocked: found {count} CONFIRMED signoffs for build {build_id}, "
            f"need at least {min_signoffs}. Run `coverage-gap verify` for a fresh sample, "
            f"then write entries into audit/verification-log.md with `Build: {build_id}`."
        )
