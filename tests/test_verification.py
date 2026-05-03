"""Tests for the verification gate."""

import pandas as pd
import pytest

from coverage_gap.verification import (
    VerificationGateError,
    count_recent_signoffs,
    format_for_review,
    gate_render,
    pick_random_sample,
)


@pytest.fixture
def sample_matrix():
    return pd.DataFrame([
        {"cah_id": "MS001", "cah_name": "Greenwood Leflore", "specialty": "cardiology",
         "physician_count": 0, "level": "HIGH", "nearest_distance_mi": 95.0, "is_hpsa": False},
        {"cah_id": "MS002", "cah_name": "Magee General", "specialty": "neurology",
         "physician_count": 0, "level": "CRITICAL", "nearest_distance_mi": 70.0, "is_hpsa": True},
        {"cah_id": "MS003", "cah_name": "Tippah County", "specialty": "psychiatry",
         "physician_count": 1, "level": "MODERATE", "nearest_distance_mi": 12.0, "is_hpsa": False},
        {"cah_id": "MS004", "cah_name": "Pearl River", "specialty": "ob_gyn",
         "physician_count": 0, "level": "HIGH", "nearest_distance_mi": 65.0, "is_hpsa": False},
        {"cah_id": "MS005", "cah_name": "Sharkey-Issaquena", "specialty": "general_surgery",
         "physician_count": 0, "level": "CRITICAL", "nearest_distance_mi": 80.0, "is_hpsa": True},
        {"cah_id": "MS006", "cah_name": "Wayne General", "specialty": "orthopedic_surgery",
         "physician_count": 0, "level": "HIGH", "nearest_distance_mi": 55.0, "is_hpsa": False},
    ])


def test_pick_random_sample_returns_n(sample_matrix):
    sample = pick_random_sample(sample_matrix, n=3)
    assert len(sample) == 3


def test_pick_random_sample_deterministic(sample_matrix):
    a = pick_random_sample(sample_matrix, n=3, seed=42)
    b = pick_random_sample(sample_matrix, n=3, seed=42)
    pd.testing.assert_frame_equal(a, b)


def test_pick_random_sample_prefers_critical_high(sample_matrix):
    sample = pick_random_sample(sample_matrix, n=5, seed=42)
    assert all(level in {"CRITICAL", "HIGH"} for level in sample["level"])


def test_pick_random_sample_falls_back_when_pool_too_small():
    matrix = pd.DataFrame([
        {"cah_id": "MS001", "specialty": "cardiology", "level": "MODERATE",
         "physician_count": 1, "cah_name": "Greenwood"},
    ])
    sample = pick_random_sample(matrix, n=5)
    # Pool is too small, falls back to whole matrix and returns what's available.
    assert len(sample) == 1


def test_format_for_review_includes_each_row(sample_matrix):
    sample = pick_random_sample(sample_matrix, n=3)
    text = format_for_review(sample)
    for _, row in sample.iterrows():
        assert row["cah_name"] in text


def test_count_signoffs_no_log(tmp_path):
    log = tmp_path / "no-such-log.md"
    assert count_recent_signoffs(log_path=log) == 0


def test_count_signoffs_one_confirmed(tmp_path):
    log = tmp_path / "verification-log.md"
    log.write_text(
        "# Verification Log\n\n"
        "## 2026-05-04 14:00 signed off by founder\n\n"
        "Build: abc123\n"
        "Result: CONFIRMED\n"
    )
    assert count_recent_signoffs(log_path=log) == 1


def test_count_signoffs_disputed_excluded(tmp_path):
    log = tmp_path / "verification-log.md"
    log.write_text(
        "# Verification Log\n\n"
        "## 2026-05-04 14:00 signed off by founder\n\n"
        "Result: CONFIRMED\n\n"
        "## 2026-05-04 14:30 signed off by founder\n\n"
        "Result: DISPUTED\n"
    )
    assert count_recent_signoffs(log_path=log) == 1


def test_count_signoffs_filters_by_build_id(tmp_path):
    log = tmp_path / "verification-log.md"
    log.write_text(
        "# Verification Log\n\n"
        "## 2026-05-04 14:00 signed off by founder\n\n"
        "Build: abc123\n"
        "Result: CONFIRMED\n\n"
        "## 2026-05-04 15:00 signed off by founder\n\n"
        "Build: xyz789\n"
        "Result: CONFIRMED\n"
    )
    assert count_recent_signoffs(log_path=log, build_id="abc123") == 1
    assert count_recent_signoffs(log_path=log, build_id="def456") == 0


def test_gate_render_blocks_when_insufficient(tmp_path):
    log = tmp_path / "verification-log.md"
    log.write_text("# Verification Log\n")
    with pytest.raises(VerificationGateError):
        gate_render(min_signoffs=5, build_id="abc123", log_path=log)


def test_gate_render_passes_when_sufficient(tmp_path):
    log = tmp_path / "verification-log.md"
    entries = "\n\n".join(
        f"## 2026-05-04 14:0{i} signed off by founder\n\nBuild: abc123\nResult: CONFIRMED\n"
        for i in range(5)
    )
    log.write_text("# Verification Log\n\n" + entries)
    # Should not raise.
    gate_render(min_signoffs=5, build_id="abc123", log_path=log)


def test_gate_render_rejects_stale_signoffs_from_different_build(tmp_path):
    """Regression test: signoffs from a different build_id must NOT count."""
    log = tmp_path / "verification-log.md"
    entries = "\n\n".join(
        f"## 2026-05-04 14:0{i} signed off by founder\n\nBuild: old123\nResult: CONFIRMED\n"
        for i in range(5)
    )
    log.write_text("# Verification Log\n\n" + entries)
    with pytest.raises(VerificationGateError, match="found 0 CONFIRMED signoffs for build new456"):
        gate_render(min_signoffs=5, build_id="new456", log_path=log)


def test_compute_build_id_stable_across_schema_changes():
    """build_id should not change when non-claim columns are added."""
    from coverage_gap.verification import compute_build_id
    base = pd.DataFrame([
        {"cah_id": "MS001", "specialty": "cardiology", "physician_count": 5, "level": "COVERED"},
        {"cah_id": "MS002", "specialty": "cardiology", "physician_count": 0, "level": "HIGH"},
    ])
    extended = base.assign(extra_col="anything", coord_source="nominatim")
    assert compute_build_id(base) == compute_build_id(extended)


def test_compute_build_id_changes_with_claims():
    from coverage_gap.verification import compute_build_id
    a = pd.DataFrame([
        {"cah_id": "MS001", "specialty": "cardiology", "physician_count": 5, "level": "COVERED"},
    ])
    b = pd.DataFrame([
        {"cah_id": "MS001", "specialty": "cardiology", "physician_count": 4, "level": "COVERED"},
    ])
    assert compute_build_id(a) != compute_build_id(b)
