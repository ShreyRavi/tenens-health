"""Tests for the gap scoring algorithm."""

import pandas as pd

from coverage_gap.scoring import (
    GapLevel,
    classify,
    count_physicians_within_radius,
    gap_score,
)


def test_classify_critical():
    assert classify(0, is_hpsa=True) == GapLevel.CRITICAL


def test_classify_high():
    assert classify(0, is_hpsa=False) == GapLevel.HIGH


def test_classify_moderate():
    assert classify(1, is_hpsa=False) == GapLevel.MODERATE
    assert classify(2, is_hpsa=False) == GapLevel.MODERATE


def test_classify_covered():
    assert classify(3, is_hpsa=False) == GapLevel.COVERED
    assert classify(10, is_hpsa=True) == GapLevel.COVERED


def test_count_physicians_empty():
    df = pd.DataFrame(columns=["lat", "lon", "specialty"])
    count, nearest = count_physicians_within_radius(33.0, -90.0, df, "cardiology")
    assert count == 0
    assert nearest is None


def test_count_physicians_within_radius():
    # Jackson MS is roughly 32.30, -90.18.
    df = pd.DataFrame([
        {"lat": 32.78, "lon": -90.18, "specialty": "cardiology"},   # ~33mi north
        {"lat": 35.00, "lon": -90.18, "specialty": "cardiology"},   # ~187mi, outside
        {"lat": 32.78, "lon": -90.18, "specialty": "neurology"},    # wrong specialty
    ])
    count, nearest = count_physicians_within_radius(32.30, -90.18, df, "cardiology", radius_mi=60)
    assert count == 1
    assert 30 < nearest < 35


def test_gap_score_zero_physicians_hpsa():
    df = pd.DataFrame(columns=["lat", "lon", "specialty"])
    cah = {"provider_num": "MS001", "lat": 32.30, "lon": -90.18}
    result = gap_score(cah, "cardiology", df, is_hpsa=True)
    assert result.level == GapLevel.CRITICAL
    assert result.physician_count == 0


def test_gap_score_zero_physicians_no_hpsa():
    df = pd.DataFrame(columns=["lat", "lon", "specialty"])
    cah = {"provider_num": "MS001", "lat": 32.30, "lon": -90.18}
    result = gap_score(cah, "cardiology", df, is_hpsa=False)
    assert result.level == GapLevel.HIGH


def test_gap_score_three_within_radius_is_covered():
    df = pd.DataFrame([
        {"lat": 32.40, "lon": -90.18, "specialty": "cardiology"},
        {"lat": 32.50, "lon": -90.20, "specialty": "cardiology"},
        {"lat": 32.45, "lon": -90.10, "specialty": "cardiology"},
    ])
    cah = {"provider_num": "MS002", "lat": 32.30, "lon": -90.18}
    result = gap_score(cah, "cardiology", df, is_hpsa=True)
    assert result.physician_count == 3
    assert result.level == GapLevel.COVERED
