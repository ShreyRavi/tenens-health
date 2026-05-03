"""Geocoding and distance utilities.

Hospitals get precise lat/lon from Nominatim, cached to disk. Physicians use ZIP
centroid lookup, accuracy well under 1% inside a 30mi radius. See audit/decisions.md.
"""

import json
import math
import time
from pathlib import Path

import requests
from tenacity import retry, stop_after_attempt, wait_exponential

from coverage_gap.config import PROCESSED_DIR

NOMINATIM_BASE = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "coverage-gap-index/0.1 (contact: founders@tenenshealth.com)"


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles between two points on Earth."""
    r_miles = 3958.8
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r_miles * c


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
def _nominatim_request(query: str) -> dict | None:
    params = {"q": query, "format": "json", "limit": 1}
    headers = {"User-Agent": USER_AGENT}
    resp = requests.get(NOMINATIM_BASE, params=params, headers=headers, timeout=10)
    resp.raise_for_status()
    results = resp.json()
    return results[0] if results else None


def geocode_address(
    address: str,
    cache_path: Path | None = None,
    sleep_s: float = 1.1,
) -> tuple[float, float] | None:
    """Geocode a free-form address via Nominatim, with on-disk cache.

    Returns (lat, lon) or None if geocoding fails. Sleeps after each network call to
    honor Nominatim's 1 req/sec rate limit. Cache misses are recorded too, so we
    don't keep retrying addresses that legitimately can't be geocoded.
    """
    cache_path = cache_path or (PROCESSED_DIR / "geocode_cache.json")
    cache: dict[str, list | None] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text())

    if address in cache:
        cached = cache[address]
        return tuple(cached) if cached else None  # type: ignore[return-value]

    try:
        result = _nominatim_request(address)
    except Exception:
        result = None

    coords: tuple[float, float] | None
    if result:
        coords = (float(result["lat"]), float(result["lon"]))
    else:
        coords = None

    cache[address] = list(coords) if coords else None
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2))
    if sleep_s > 0:
        time.sleep(sleep_s)
    return coords


_zip_centroid_cache: dict[str, tuple[float, float]] | None = None


def zip_centroid(zip_code: str | float | None, table_path: Path | None = None) -> tuple[float, float] | None:
    """Look up the centroid lat/lon for a US ZIP code.

    Loads a static ZIP-to-centroid table on first call. Source on the methodology
    page. Returns None if the ZIP isn't in the table.
    """
    global _zip_centroid_cache
    if zip_code is None or (isinstance(zip_code, float) and math.isnan(zip_code)):
        return None
    if _zip_centroid_cache is None:
        path = table_path or (PROCESSED_DIR / "zip_centroids.parquet")
        if not path.exists():
            _zip_centroid_cache = {}
        else:
            import pandas as pd
            df = pd.read_parquet(path)
            _zip_centroid_cache = {
                str(row.zip).zfill(5): (float(row.lat), float(row.lng))
                for row in df.itertuples()
            }
    return _zip_centroid_cache.get(str(zip_code).zfill(5))
