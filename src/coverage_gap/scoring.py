"""Gap scoring algorithm.

For each (CAH, specialty) pair, count active physicians of that specialty within
RADIUS_MILES of the CAH, then classify into CRITICAL / HIGH / MODERATE / COVERED.
HRSA HPSA designation escalates from HIGH to CRITICAL.
"""

from dataclasses import dataclass
from enum import Enum

import pandas as pd

from coverage_gap.config import RADIUS_MILES
from coverage_gap.geo import haversine_miles


class GapLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    COVERED = "COVERED"


@dataclass(frozen=True)
class GapResult:
    cah_id: str
    specialty: str
    physician_count: int
    level: GapLevel
    nearest_distance_mi: float | None
    is_hpsa: bool


def count_physicians_within_radius(
    cah_lat: float,
    cah_lon: float,
    physicians: pd.DataFrame,
    specialty: str,
    radius_mi: float = RADIUS_MILES,
) -> tuple[int, float | None]:
    """Count physicians of a given specialty within radius_mi of the CAH.

    physicians must have columns: lat, lon, specialty (the normalized key).
    Returns (count, nearest_distance_mi). nearest is None only when the specialty
    has zero physicians anywhere in the dataset.
    """
    if physicians.empty:
        return 0, None
    subset = physicians[physicians["specialty"] == specialty]
    if subset.empty:
        return 0, None

    distances = subset.apply(
        lambda row: haversine_miles(cah_lat, cah_lon, row["lat"], row["lon"]),
        axis=1,
    )
    within = distances[distances <= radius_mi]
    if within.empty:
        return 0, float(distances.min())
    return int(len(within)), float(within.min())


def classify(physician_count: int, is_hpsa: bool) -> GapLevel:
    if physician_count == 0 and is_hpsa:
        return GapLevel.CRITICAL
    if physician_count == 0:
        return GapLevel.HIGH
    if physician_count <= 2:
        return GapLevel.MODERATE
    return GapLevel.COVERED


def gap_score(
    cah: dict,
    specialty: str,
    physicians: pd.DataFrame,
    is_hpsa: bool = False,
    radius_mi: float = RADIUS_MILES,
) -> GapResult:
    count, nearest = count_physicians_within_radius(
        cah["lat"], cah["lon"], physicians, specialty, radius_mi
    )
    return GapResult(
        cah_id=cah["provider_num"],
        specialty=specialty,
        physician_count=count,
        level=classify(count, is_hpsa),
        nearest_distance_mi=nearest,
        is_hpsa=is_hpsa,
    )
