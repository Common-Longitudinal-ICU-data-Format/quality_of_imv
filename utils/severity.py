"""Presentation-window severity, per analysis_plan/03_outcome_analysis.md section 3.

The risk-adjustment window is the 4 hours **ending at time zero**:

    W = [t0 - 4h, t0]

so every covariate is measured at or before the moment exposure to ICU quality begins and
cannot be a post-treatment variable. This replaces the concept paper's worst-in-first-24 h,
which was contaminated: respiratory and cardiovascular SOFA depend on the very unit
practices (PEEP, FiO2, vasopressor thresholds) that the quality score is meant to capture.

For real CLIF data, prefer clifpy's ``calculate_sofa2``, which accepts an arbitrary
``cohort_df`` of ``[hospitalization_id, start_dttm, end_dttm]`` windows and therefore fits
this design directly. The function here is a simplified fallback used for the synthetic
demo, and it implements only the six standard components with conventional cutoffs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def presentation_windows(cohort: pd.DataFrame, hours_before: float = 4.0) -> pd.DataFrame:
    """The ``[t0 - hours_before, t0]`` window per hospitalization.

    Column names match what clifpy's ``calculate_sofa2`` expects, so the same frame can be
    handed straight to it on real data.
    """
    out = cohort[["hospitalization_id", "time_zero"]].copy()
    out["start_dttm"] = out["time_zero"] - pd.Timedelta(hours=hours_before)
    out["end_dttm"] = out["time_zero"]
    return out.drop(columns="time_zero")


def _worst_in_window(
    df: pd.DataFrame,
    windows: pd.DataFrame,
    time_col: str,
    value_col: str,
    how: str,
    carry_forward_hours: float = 24.0,
) -> pd.Series:
    """Worst value in the window, extending backwards if the window itself is empty.

    Carrying forward from before the window keeps the value pre-exposure while recovering
    labs that were simply not redrawn inside a 4-hour span -- option (b) of the missing
    data open decision in plan 03 section 10. Narrowing the window from 24 h to 4 h buys
    freedom from post-treatment adjustment at the cost of missingness, and this is where
    that cost is paid.
    """
    d = df.merge(windows, on="hospitalization_id", how="inner")
    d[value_col] = pd.to_numeric(d[value_col], errors="coerce")
    d = d.dropna(subset=[value_col, time_col])

    in_win = d[(d[time_col] >= d["start_dttm"]) & (d[time_col] <= d["end_dttm"])]
    agg = in_win.groupby("hospitalization_id")[value_col]
    primary = agg.max() if how == "max" else agg.min()

    back = d[
        (d[time_col] < d["start_dttm"])
        & (d[time_col] >= d["start_dttm"] - pd.Timedelta(hours=carry_forward_hours))
    ]
    if not back.empty:
        latest = back.sort_values(time_col).groupby("hospitalization_id").tail(1)
        fallback = latest.set_index("hospitalization_id")[value_col]
        primary = primary.reindex(primary.index.union(fallback.index))
        primary = primary.fillna(fallback)
    return primary


def sofa_components(
    cohort: pd.DataFrame,
    labs: pd.DataFrame,
    vitals: pd.DataFrame,
    resp: pd.DataFrame,
    assessments: pd.DataFrame,
    meds: pd.DataFrame,
    hours_before: float = 4.0,
    carry_forward_hours: float = 24.0,
) -> pd.DataFrame:
    """Six SOFA components from the presentation window. Simplified; demo use only."""
    win = presentation_windows(cohort, hours_before)
    idx = cohort["hospitalization_id"]

    def worst(df, time_col, value_col, how, category_col=None, category=None):
        if df.empty:
            return pd.Series(dtype=float)
        d = df
        if category_col is not None:
            d = d[d[category_col].astype("string").str.strip().str.lower() == category]
        if d.empty:
            return pd.Series(dtype=float)
        return _worst_in_window(d, win, time_col, value_col, how, carry_forward_hours)

    pao2 = worst(labs, "lab_result_dttm", "lab_value_numeric", "min",
                 "lab_category", "po2_arterial")
    plt_ct = worst(labs, "lab_result_dttm", "lab_value_numeric", "min",
                   "lab_category", "platelet_count")
    bili = worst(labs, "lab_result_dttm", "lab_value_numeric", "max",
                 "lab_category", "bilirubin_total")
    creat = worst(labs, "lab_result_dttm", "lab_value_numeric", "max",
                  "lab_category", "creatinine")
    mapv = worst(vitals, "recorded_dttm", "vital_value", "min", "vital_category", "map")
    gcs = worst(assessments, "recorded_dttm", "numerical_value", "min",
                "assessment_category", "gcs_total")
    fio2 = worst(resp, "recorded_dttm", "fio2_set", "max")

    vaso = pd.Series(dtype=float)
    if not meds.empty:
        v = meds[
            meds["med_category"].astype("string").str.strip().str.lower().isin(
                ["norepinephrine", "epinephrine", "dopamine", "phenylephrine",
                 "vasopressin"]
            )
        ]
        vaso = worst(v, "admin_dttm", "med_dose", "max")

    out = pd.DataFrame({"hospitalization_id": idx}).set_index("hospitalization_id")
    out["pao2"] = pao2.reindex(out.index)
    out["fio2"] = fio2.reindex(out.index)
    out["platelets"] = plt_ct.reindex(out.index)
    out["bilirubin"] = bili.reindex(out.index)
    out["creatinine"] = creat.reindex(out.index)
    out["map"] = mapv.reindex(out.index)
    out["gcs"] = gcs.reindex(out.index)
    out["vasopressor_dose"] = vaso.reindex(out.index)

    pf = out["pao2"] / out["fio2"].where(out["fio2"] > 0)
    out["pf_ratio"] = pf

    # All patients in this cohort are on IMV at time zero, so the respiratory component
    # uses the ventilated thresholds throughout.
    out["sofa_resp"] = pd.cut(
        pf, [-np.inf, 100, 200, 300, 400, np.inf], labels=[4, 3, 2, 1, 0]
    ).astype("float")
    out["sofa_coag"] = pd.cut(
        out["platelets"], [-np.inf, 20, 50, 100, 150, np.inf], labels=[4, 3, 2, 1, 0]
    ).astype("float")
    out["sofa_liver"] = pd.cut(
        out["bilirubin"], [-np.inf, 1.2, 2.0, 6.0, 12.0, np.inf], labels=[0, 1, 2, 3, 4]
    ).astype("float")
    out["sofa_renal"] = pd.cut(
        out["creatinine"], [-np.inf, 1.2, 2.0, 3.5, 5.0, np.inf], labels=[0, 1, 2, 3, 4]
    ).astype("float")
    out["sofa_cns"] = pd.cut(
        out["gcs"], [-np.inf, 6, 9, 12, 14, np.inf], labels=[4, 3, 2, 1, 0]
    ).astype("float")

    # Simplified cardiovascular: any vasopressor scores 3, hypotension alone scores 1.
    # The real component needs dose bands in mcg/kg/min, which is what clifpy's
    # convert_dose_units_for_continuous_meds exists for.
    out["sofa_cv"] = np.where(
        out["vasopressor_dose"].fillna(0) > 0, 3.0,
        np.where(out["map"] < 70, 1.0, 0.0),
    )

    comp = ["sofa_resp", "sofa_coag", "sofa_liver", "sofa_renal", "sofa_cns", "sofa_cv"]
    out["sofa_total"] = out[comp].sum(axis=1, min_count=1)
    out["n_sofa_components_observed"] = out[comp].notna().sum(axis=1)
    return out.reset_index()
