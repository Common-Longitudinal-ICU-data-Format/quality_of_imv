"""Edge-case tests for the time-zero logic in analysis_plan/01_cohort_identification.md.

Run with:  uv run pytest utils/test_cohort.py -q
"""

from __future__ import annotations

import pandas as pd

from utils.cohort import (
    build_icu_intervals,
    build_imv_intervals,
    compute_time_zero,
    merge_intervals,
)

T = pd.Timestamp("2024-01-01 00:00:00")


def h(n: float) -> pd.Timedelta:
    return pd.Timedelta(hours=n)


def _icu(start_h: float, end_h: float, unit: str = "MICU_A"):
    return [(T + h(start_h), T + h(end_h), unit)]


def test_merge_intervals_joins_touching_and_overlapping():
    got = merge_intervals([(T + h(2), T + h(4)), (T, T + h(2)), (T + h(3), T + h(6))])
    assert got == [(T, T + h(6))]


def test_ed_then_icu_time_zero_is_icu_admission():
    """8 h of IMV in the ED, then ICU -> time zero is ICU admission."""
    imv = [(T, T + h(40))]
    got = compute_time_zero(imv, _icu(8, 200))
    assert got["time_zero"] == T + h(8)
    assert got["imv_hours_at_t0"] == 8.0
    assert got["intubated_before_icu"] is True


def test_imv_starting_in_icu_time_zero_is_onset_plus_four():
    """Intubated 3 h after ICU arrival -> time zero is IMV onset + 4 h."""
    imv = [(T + h(13), T + h(60))]
    got = compute_time_zero(imv, _icu(10, 200))
    assert got["time_zero"] == T + h(17)
    assert got["imv_hours_at_t0"] == 4.0
    assert got["intubated_before_icu"] is False


def test_partial_ed_time_carries_forward():
    """2 h of IMV in the ED then continuing -> time zero is ICU admit + 2 h."""
    imv = [(T + h(8), T + h(60))]
    got = compute_time_zero(imv, _icu(10, 200))
    assert got["time_zero"] == T + h(12)
    assert got["imv_hours_at_t0"] == 4.0
    assert got["intubated_before_icu"] is True


def test_short_imv_is_excluded():
    assert compute_time_zero([(T, T + h(2))], _icu(0, 100)) is None


def test_exactly_four_hours_is_excluded_because_criterion_is_strictly_greater():
    """Plan 01 section 4: IMV > 4 hours, so exactly 4 h does not qualify."""
    assert compute_time_zero([(T, T + h(4))], _icu(0, 100)) is None


def test_no_icu_is_excluded():
    assert compute_time_zero([(T, T + h(40))], []) is None


def test_threshold_reached_only_outside_icu_is_excluded():
    """Ventilated 10 h in the ED, extubated, then a later ICU stay with no IMV."""
    imv = [(T, T + h(10))]
    icu = _icu(20, 40)
    got = compute_time_zero(imv, icu)
    # Accrued before ICU (10 h) already exceeds the threshold, so arrival qualifies.
    assert got["time_zero"] == T + h(20)


def test_accrual_spanning_two_icu_stays():
    """1 h of IMV in a first ICU stay, the rest in a second -> t0 in the second unit."""
    imv = [(T + h(1), T + h(2)), (T + h(10), T + h(30))]
    icu = [
        (T, T + h(2), "MICU_A"),
        (T + h(10), T + h(50), "SICU_C"),
    ]
    got = compute_time_zero(imv, icu)
    assert got["location_name"] == "SICU_C"
    assert got["time_zero"] == T + h(13)  # needs 3 more hours after the 1 h already accrued


def test_build_imv_intervals_caps_documentation_gaps():
    resp = pd.DataFrame(
        {
            "recorded_dttm": [T, T + h(1), T + h(100)],
            "device_category": ["IMV", "IMV", "IMV"],
        }
    )
    got = build_imv_intervals(resp, max_gap_hours=6, trailing_clip_hours=1)
    # Row 0 runs to row 1 (1 h). Row 1 precedes a 99-hour gap and is capped at the
    # 6-hour interior cap, giving [0h, 7h) after merging. Row 2 is the final row of the
    # record, so it gets the tighter 1-hour trailing clip rather than 6 hours.
    assert got == [(T, T + h(7)), (T + h(100), T + h(101))]


def test_trailing_clip_prevents_a_short_episode_entering_the_cohort():
    """Two hourly IMV rows is a 2-hour episode, not a 7-hour one.

    With a 6-hour trailing carry-forward this patient would accrue 7 h and wrongly meet
    the IMV > 4 h criterion on the strength of one unresolved observation.
    """
    resp = pd.DataFrame(
        {"recorded_dttm": [T, T + h(1)], "device_category": ["IMV", "IMV"]}
    )
    imv = build_imv_intervals(resp, max_gap_hours=6, trailing_clip_hours=1)
    assert imv == [(T, T + h(2))]
    assert compute_time_zero(imv, _icu(0, 100)) is None


def test_build_imv_intervals_ignores_non_imv_devices():
    resp = pd.DataFrame(
        {
            "recorded_dttm": [T, T + h(1)],
            "device_category": ["Nasal Cannula", "NIPPV"],
        }
    )
    assert build_imv_intervals(resp) == []


def test_build_icu_intervals_filters_and_keeps_units_separate():
    adt = pd.DataFrame(
        {
            "hospitalization_id": ["H1"] * 3,
            "in_dttm": [T, T + h(10), T + h(20)],
            "out_dttm": [T + h(10), T + h(20), T + h(30)],
            "location_category": ["ED", "icu", "ICU"],
            "location_name": ["ED_MAIN", "MICU_A", "SICU_C"],
        }
    )
    got = build_icu_intervals(adt)
    assert [g[2] for g in got] == ["MICU_A", "SICU_C"]
