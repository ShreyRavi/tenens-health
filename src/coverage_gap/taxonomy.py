"""NPPES taxonomy code to specialty mapping, loaded from taxonomy.yaml."""

from functools import lru_cache
from pathlib import Path

import yaml

from coverage_gap.config import PACKAGE_DIR


class TaxonomyError(Exception):
    """Raised when the taxonomy YAML is missing or malformed."""


@lru_cache(maxsize=4)
def load_taxonomy(path: Path | None = None) -> dict:
    """Load the specialty-to-codes map from taxonomy.yaml."""
    yaml_path = path or (PACKAGE_DIR / "taxonomy.yaml")
    if not yaml_path.exists():
        raise TaxonomyError(f"Taxonomy YAML not found at {yaml_path}")
    with yaml_path.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict) or "specialties" not in data:
        raise TaxonomyError(f"Taxonomy YAML missing 'specialties' key: {yaml_path}")
    return data["specialties"]


def code_to_specialties(code: str) -> list[str]:
    """Return all specialty keys that include this NPPES taxonomy code.

    A code can map to multiple specialties (Surgical Oncology, for example,
    counts for both general_surgery and oncology). Unknown codes return [].
    """
    if not code:
        return []
    specialties = load_taxonomy()
    return [key for key, entry in specialties.items() if code in entry["codes"]]


def specialty_label(key: str) -> str:
    """Return the human-readable label for a specialty key."""
    specialties = load_taxonomy()
    if key not in specialties:
        raise TaxonomyError(f"Unknown specialty key: {key}")
    return specialties[key]["label"]


def all_codes() -> set[str]:
    """Return the set of all NPPES codes we track across the 15 specialties."""
    specialties = load_taxonomy()
    codes: set[str] = set()
    for entry in specialties.values():
        codes.update(entry["codes"])
    return codes
