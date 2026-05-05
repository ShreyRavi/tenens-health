"""Tests for the NPPES taxonomy mapping."""

import pytest

from coverage_gap.taxonomy import (
    TaxonomyError,
    all_codes,
    code_to_specialties,
    load_taxonomy,
    specialty_label,
)


@pytest.fixture(autouse=True)
def _clear_load_taxonomy_cache():
    """load_taxonomy is decorated with @lru_cache. Clear before AND after each
    test so per-path tests do not leak entries into the cache."""
    load_taxonomy.cache_clear()
    yield
    load_taxonomy.cache_clear()


def test_taxonomy_loads():
    t = load_taxonomy()
    assert "cardiology" in t
    assert "general_surgery" in t
    assert len(t) == 15


def test_all_15_specialties_present():
    expected = {
        "general_surgery", "orthopedic_surgery", "cardiology", "pulmonology_critical_care",
        "neurology", "psychiatry", "ob_gyn", "oncology", "gastroenterology", "urology",
        "rheumatology", "endocrinology", "nephrology", "dermatology", "emergency_medicine",
    }
    assert set(load_taxonomy().keys()) == expected


def test_known_cardiology_codes_map():
    # 207RC0000X is the canonical Cardiovascular Disease code.
    assert "cardiology" in code_to_specialties("207RC0000X")
    # 207RI0011X is interventional cardiology, also rolls up to cardiology.
    assert "cardiology" in code_to_specialties("207RI0011X")


def test_unknown_code_returns_empty():
    assert code_to_specialties("9999X9999X") == []


def test_empty_or_none_code_returns_empty():
    assert code_to_specialties("") == []
    assert code_to_specialties(None) == []  # type: ignore[arg-type]


def test_surgical_oncology_in_two_specialties():
    # Surgical Oncology is intentionally cross-listed under both surgery and oncology.
    matches = code_to_specialties("2086S0105X")
    assert "general_surgery" in matches
    assert "oncology" in matches


def test_specialty_label():
    assert specialty_label("ob_gyn") == "Obstetrics and Gynecology"
    assert specialty_label("cardiology") == "Cardiology"


def test_unknown_specialty_label_raises():
    with pytest.raises(TaxonomyError):
        specialty_label("not_a_specialty")


def test_all_codes_returns_set():
    codes = all_codes()
    assert isinstance(codes, set)
    # 15 specialties times at least 1-2 codes minimum yields well over 30.
    assert len(codes) > 30
    assert all(c.endswith("X") for c in codes)


def test_load_taxonomy_missing_file_raises(tmp_path):
    """Pointing load_taxonomy at a nonexistent path must raise TaxonomyError."""
    missing = tmp_path / "no-such-taxonomy.yaml"
    with pytest.raises(TaxonomyError, match="not found"):
        load_taxonomy(path=missing)


def test_load_taxonomy_malformed_raises(tmp_path):
    """A YAML file without a top-level 'specialties' key must raise TaxonomyError."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("other_key: 1\n")
    with pytest.raises(TaxonomyError, match="missing 'specialties' key"):
        load_taxonomy(path=bad)
