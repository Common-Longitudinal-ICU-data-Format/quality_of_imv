"""Time-zero and IMV-interval logic for analysis_plan/01_cohort_identification.md.

The one non-obvious piece of this project is time zero, so it lives here as plain
functions rather than inline in a notebook cell -- it needs to be unit-testable against
the edge cases the plan enumerates.

Time zero (plan 01 section 3) is the first moment at which the patient is simultaneously
(a) in an ICU and (b) past 4 cumulative hours of IMV during the hospitalization:

    t0 = min { t : in_icu(t) and cumulative_imv(t) >= threshold }

IMV time accrued anywhere (ED, OR, ward) counts toward the threshold; only the location
*at* time zero must be an ICU.
"""

from __future__ import annotations

import pandas as pd

Interval = tuple[pd.Timestamp, pd.Timestamp]


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    """Merge overlapping or touching intervals. Input need not be sorted."""
    if not intervals:
        return []
    out: list[Interval] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if out and start <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


def build_imv_intervals(
    resp: pd.DataFrame,
    imv_device: str = "imv",
    max_gap_hours: float = 6.0,
    trailing_clip_hours: float = 1.0,
    time_col: str = "recorded_dttm",
    device_col: str = "device_category",
) -> list[Interval]:
    """Convert point respiratory_support observations into IMV intervals.

    Each IMV row covers the span from its own timestamp to the next observation of any
    kind, capped at ``max_gap_hours``. Capping matters: without it, a single IMV row
    followed by a week-long documentation gap would imply a week of ventilation.

    The **final** row of the record is capped more tightly, at ``trailing_clip_hours``,
    following the dashboard's ``TRAIL_CLIP``. This is not a cosmetic detail at a 4-hour
    cohort threshold: with a 6-hour trailing carry-forward, a patient with two hourly IMV
    observations would accrue 7 hours of apparent ventilation and enter the cohort on the
    strength of a single unresolved observation. Clipping the trailing row to 1 hour means
    accrued IMV time is bounded by what was actually documented. See the carry-forward
    open decision in plan 01 section 3.
    """
    if resp.empty:
        return []

    df = resp[[time_col, device_col]].copy()
    df[device_col] = df[device_col].astype("string").str.strip().str.lower()
    df = df.dropna(subset=[time_col]).sort_values(time_col)

    gap_cap = pd.Timedelta(hours=max_gap_hours)
    trail_cap = pd.Timedelta(hours=trailing_clip_hours)
    next_time = df[time_col].shift(-1)

    intervals: list[Interval] = []
    for t, nxt, dev in zip(df[time_col], next_time, df[device_col]):
        if dev != imv_device:
            continue
        if pd.isna(nxt):
            end = t + trail_cap
        else:
            end = min(nxt, t + gap_cap)
        intervals.append((t, end))
    return merge_intervals(intervals)


def build_icu_intervals(
    adt: pd.DataFrame,
    in_col: str = "in_dttm",
    out_col: str = "out_dttm",
    category_col: str = "location_category",
    name_col: str = "location_name",
) -> list[tuple[pd.Timestamp, pd.Timestamp, str]]:
    """ICU stays as (in, out, location_name), sorted by entry time.

    Not merged: adjacent ICU stays in *different* units must stay separate so that
    time zero can be attributed to the right ``location_name``.
    """
    if adt.empty:
        return []
    df = adt.copy()
    df[category_col] = df[category_col].astype("string").str.strip().str.lower()
    icu = df[df[category_col] == "icu"].dropna(subset=[in_col, out_col])
    icu = icu.sort_values(in_col)
    return [
        (r[in_col], r[out_col], r[name_col])
        for _, r in icu.iterrows()
        if r[out_col] > r[in_col]
    ]


def compute_time_zero(
    imv_intervals: list[Interval],
    icu_intervals: list[tuple[pd.Timestamp, pd.Timestamp, str]],
    threshold_hours: float = 4.0,
) -> dict | None:
    """Find time zero, or None if the patient never qualifies.

    Walks ICU stays in order. Within each stay, accumulates IMV time until the threshold
    is met; if the stay ends first, the accumulated total carries into the next stay.

    Returns a dict with ``time_zero``, ``location_name``, ``imv_hours_at_t0`` (cumulative
    IMV at time zero, which exceeds the threshold when the patient arrived in the ICU
    already past it), ``intubated_before_icu``, and ``total_imv_hours``.
    """
    threshold = pd.Timedelta(hours=threshold_hours)
    total_imv = sum((e - s for s, e in imv_intervals), pd.Timedelta(seconds=0))

    if not imv_intervals or not icu_intervals or total_imv <= threshold:
        return None

    first_imv_start = imv_intervals[0][0]

    for icu_in, icu_out, unit in icu_intervals:
        # Cumulative IMV strictly before this ICU stay begins.
        accrued = sum(
            (min(e, icu_in) - s for s, e in imv_intervals if s < icu_in),
            pd.Timedelta(seconds=0),
        )

        if accrued >= threshold:
            # Already past the threshold on arrival: both conditions first hold at
            # ICU admission (plan 01 section 3, the ED-then-ICU scenario).
            return {
                "time_zero": icu_in,
                "location_name": unit,
                "imv_hours_at_t0": accrued.total_seconds() / 3600.0,
                "intubated_before_icu": first_imv_start < icu_in,
                "total_imv_hours": total_imv.total_seconds() / 3600.0,
            }

        # Otherwise accumulate IMV time inside this ICU stay until the deficit closes.
        deficit = threshold - accrued
        for s, e in imv_intervals:
            lo, hi = max(s, icu_in), min(e, icu_out)
            if hi <= lo:
                continue
            span = hi - lo
            if span >= deficit:
                return {
                    "time_zero": lo + deficit,
                    "location_name": unit,
                    "imv_hours_at_t0": threshold_hours,
                    "intubated_before_icu": first_imv_start < icu_in,
                    "total_imv_hours": total_imv.total_seconds() / 3600.0,
                }
            deficit -= span

    return None
