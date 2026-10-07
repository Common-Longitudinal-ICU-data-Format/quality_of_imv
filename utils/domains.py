"""The four IMV quality domains, per analysis_plan/02_quality_score.md.

Definitions are transcribed from the CLIF ventilator QI dashboard (commit ``7ea68ec``).
Constants live in ``config/project_params.json`` so the research team can review them
against the plan without reading code.

These are **basic first-pass implementations**. Each domain notes the specific
simplifications it makes relative to the dashboard; the significant ones are the SBT
12-hour controlled accrual and stability window (approximated from native rows rather
than waterfall scaffold hours) and the norepinephrine-equivalent criterion (not yet
implemented). Search for ``SIMPLIFICATION`` to find them all.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def split_at_midnight(start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[str, pd.Timestamp, pd.Timestamp]]:
    """Split an interval into per-calendar-day pieces.

    Returns ``(day_string, piece_start, piece_end)``. The day is a ``"YYYY-MM-DD"``
    string rather than a date dtype, matching the dashboard's deliberate choice for
    parquet and DuckDB merge-key robustness.
    """
    out = []
    cur = start
    while cur < end:
        next_midnight = cur.normalize() + pd.Timedelta(days=1)
        piece_end = min(end, next_midnight)
        out.append((cur.strftime("%Y-%m-%d"), cur, piece_end))
        cur = piece_end
    return out


def _lower(s: pd.Series) -> pd.Series:
    return s.astype("string").str.strip().str.lower()


def _num(x) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return float("nan")
    return v


def scoring_windows(cohort: pd.DataFrame) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    """Per-patient scoring window: time zero to the end of IMV (plan 02 section 3)."""
    out = {}
    for _, r in cohort.iterrows():
        t0 = r["time_zero"]
        end = r["imv_end"] if pd.notna(r["imv_end"]) else r["discharge_dttm"]
        if pd.notna(t0) and pd.notna(end) and end > t0:
            out[r["hospitalization_id"]] = (t0, end)
    return out


def active_segments(
    meds: pd.DataFrame,
    categories: list[str],
    trailing_cap_hours: float = 24.0,
    interior_cap_hours: float | None = None,
) -> dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]]:
    """Union of active-infusion intervals per hospitalization.

    Following the dashboard: a segment is active when ``med_dose > 0`` and
    ``mar_action_category != "stop"``, and runs from its own ``admin_dttm`` to the next
    row for the same (hospitalization, drug), with the final segment capped at
    ``trailing_cap_hours``.

    ``interior_cap_hours`` caps *non-final* segments too. The dashboard does not do this
    (``None`` reproduces its behaviour), but leaving interior segments uncapped is
    hazardous for the SAT domain: if a drug is charted sporadically, or a ``stop`` row is
    missing, a single row whose next same-drug row is three days later is treated as
    **72 hours of continuous infusion**. That spurious segment swallows the real off-gaps
    inside it, so no SAT hold is detected and the unit's SAT rate is silently deflated.
    Failures here are invisible -- the rate just looks bad. See plan 02 section 11.
    """
    if meds.empty:
        return {}

    df = meds.copy()
    df["med_category"] = _lower(df["med_category"])
    df = df[df["med_category"].isin([c.lower() for c in categories])]
    if df.empty:
        return {}

    df["mar_action_category"] = _lower(df.get("mar_action_category", pd.Series(dtype="string")))
    df["dose"] = pd.to_numeric(df["med_dose"], errors="coerce")
    df = df.sort_values(["hospitalization_id", "med_category", "admin_dttm"])

    cap = pd.Timedelta(hours=trailing_cap_hours)
    df["seg_end"] = df.groupby(["hospitalization_id", "med_category"])["admin_dttm"].shift(-1)
    if interior_cap_hours is not None:
        interior = pd.Timedelta(hours=interior_cap_hours)
        df["seg_end"] = df[["seg_end"]].assign(
            capped=df["admin_dttm"] + interior
        ).min(axis=1)
    df["seg_end"] = df["seg_end"].fillna(df["admin_dttm"] + cap)
    df["active"] = (df["dose"] > 0) & (df["mar_action_category"] != "stop")

    from utils.cohort import merge_intervals

    out: dict[str, list[tuple[pd.Timestamp, pd.Timestamp]]] = {}
    for hid, g in df[df["active"]].groupby("hospitalization_id"):
        out[hid] = merge_intervals(list(zip(g["admin_dttm"], g["seg_end"])))
    return out


def _overlaps_day(
    segs: list[tuple[pd.Timestamp, pd.Timestamp]],
    day_in: pd.Timestamp,
    day_out: pd.Timestamp,
) -> bool:
    """Dashboard day-overlap test: ``seg.start < day_out AND seg.end > day_in``."""
    return any(s < day_out and e > day_in for s, e in segs)


# ---------------------------------------------------------------------------
# Domain 1 -- Lung-protective tidal volume
# ---------------------------------------------------------------------------


def compute_pbw(patient: pd.DataFrame, vitals: pd.DataFrame, cohort: pd.DataFrame,
                p: dict) -> pd.Series:
    """Predicted body weight per hospitalization (plan 02 section 4.1).

    Height is the median ``height_cm`` per hospitalization within plausible bounds.
    Sex is matched on ``patient.sex_category`` in **exact case** ``"Male"``/``"Female"``,
    reproducing the dashboard. That is a portability trap, not an oversight: a site whose
    ``sex_category`` is ``"male"`` or ``"M"`` yields an all-NaN PBW and a silently empty
    LTVV denominator, which is why the notebook asserts on the PBW coverage rate.
    """
    lo, hi = p["height_min_cm"], p["height_max_cm"]

    h = vitals[_lower(vitals["vital_category"]) == "height_cm"].copy()
    h["v"] = pd.to_numeric(h["vital_value"], errors="coerce")
    h = h[h["v"].between(lo, hi)]
    height = h.groupby("hospitalization_id")["v"].median()

    sex = (
        cohort[["hospitalization_id", "patient_id"]]
        .merge(patient[["patient_id", "sex_category"]], on="patient_id", how="left")
        .set_index("hospitalization_id")["sex_category"]
    )

    height_in = height / 2.54
    base = sex.map({"Male": 50.0, "Female": 45.5})
    pbw = base.reindex(height_in.index).astype(float) + 2.3 * (height_in - 60.0)
    pbw[pbw < p["pbw_min_kg"]] = np.nan
    return pbw.dropna()


def ltvv_patient_days(resp, windows, pbw, vocab, p, threshold=None) -> pd.DataFrame:
    """Per-patient-day LTVV status, minute-weighted (plan 02 sections 4.2-4.7)."""
    tau = p["ml_per_kg_threshold"] if threshold is None else threshold
    modes = {m.lower() for m in p["eligible_modes_2_1"] + p["eligible_modes_3_0"]}
    fast = pd.Timedelta(hours=p["carry_forward_fast_hours"])
    trail = pd.Timedelta(hours=p["trailing_clip_hours"])

    pieces = []
    for hid, g in resp.groupby("hospitalization_id"):
        if hid not in windows:
            continue
        w0, w1 = windows[hid]
        this_pbw = pbw.get(hid, np.nan)
        if not np.isfinite(this_pbw):
            continue

        g = g.sort_values("recorded_dttm")
        times = g["recorded_dttm"].tolist()
        recs = g.to_dict("records")

        for i, r in enumerate(recs):
            t = r["recorded_dttm"]
            nxt = times[i + 1] if i + 1 < len(times) else None
            end = t + trail if nxt is None else min(nxt, t + fast)
            s, e = max(t, w0), min(end, w1)
            if e <= s:
                continue

            dev = str(r.get("device_category") or "").strip().lower()
            mode = str(r.get("mode_category") or "").strip().lower()
            if dev != vocab["imv_device"] or mode not in modes:
                continue

            vt = _num(r.get("tidal_volume_obs")) if p["prefer_observed_tidal_volume"] else np.nan
            if not np.isfinite(vt):
                vt = _num(r.get("tidal_volume_set"))
            if not np.isfinite(vt):
                continue

            in_target = (vt / this_pbw) <= tau
            for day, ss, ee in split_at_midnight(s, e):
                mins = (ee - ss).total_seconds() / 60.0
                pieces.append(
                    {
                        "hospitalization_id": hid,
                        "day": day,
                        "assess_min": mins,
                        "in_target_min": mins if in_target else 0.0,
                    }
                )

    if not pieces:
        return pd.DataFrame(columns=["hospitalization_id", "day", "assess_min",
                                     "in_target_min", "frac", "status"])

    days = (
        pd.DataFrame(pieces)
        .groupby(["hospitalization_id", "day"], as_index=False)[["assess_min", "in_target_min"]]
        .sum()
    )
    days["frac"] = days["in_target_min"] / days["assess_min"].replace(0, np.nan)
    days["status"] = np.where(
        days["assess_min"] < p["min_assessable_minutes"],
        "not_assessable",
        np.where(days["frac"] >= p["adherence_fraction"], "adherent", "non_adherent"),
    )
    return days


# ---------------------------------------------------------------------------
# Domain 2 -- Spontaneous awakening trials
# ---------------------------------------------------------------------------


def sat_patient_days(meds, windows, p, prone_segs=None) -> pd.DataFrame:
    """Per-patient-day SAT eligibility and performance (plan 02 section 5)."""
    interior = p.get("interior_cap_hours")
    sed = active_segments(
        meds, p["sedative_analgesic_categories"], p["trailing_cap_hours"], interior
    )
    par = active_segments(
        meds, p["paralytic_categories"], p["trailing_cap_hours"], interior
    )
    hold = pd.Timedelta(minutes=p["hold_min_minutes"])
    prone_segs = prone_segs or {}

    rows = []
    for hid, (w0, w1) in windows.items():
        sed_h = sed.get(hid, [])
        if not sed_h:
            continue
        for day, day_in, day_out in split_at_midnight(w0, w1):
            on_sed = _overlaps_day(sed_h, day_in, day_out)
            on_par = _overlaps_day(par.get(hid, []), day_in, day_out)
            on_prone = (
                _overlaps_day(prone_segs.get(hid, []), day_in, day_out)
                if p["exclude_prone_days"] else False
            )
            eligible = on_sed and not on_par and not on_prone

            # Clip active sedation to the day, then scan for an off-gap. The scan starts
            # at the end of the first active block, so pre-sedation lead-in can never be
            # mistaken for a hold.
            clipped = [
                (max(s, day_in), min(e, day_out))
                for s, e in sed_h
                if s < day_out and e > day_in
            ]
            clipped = [(s, e) for s, e in clipped if e > s]

            performed = False
            if clipped:
                clipped.sort()
                cursor = clipped[0][1]
                for s, e in clipped[1:]:
                    if s > cursor and (s - cursor) >= hold:
                        performed = True
                        break
                    cursor = max(cursor, e)
                if not performed and day_out > cursor and (day_out - cursor) >= hold:
                    performed = True

            rows.append(
                {
                    "hospitalization_id": hid,
                    "day": day,
                    "on_sat_sedation": on_sed,
                    "on_paralytic": on_par,
                    "on_prone": on_prone,
                    "eligible": eligible,
                    "sat_performed": performed,
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Domain 3 -- Spontaneous breathing trials
# ---------------------------------------------------------------------------


def sbt_patient_days(resp, windows, vocab, p, paralytic_segs=None) -> pd.DataFrame:
    """Per-patient-day SBT eligibility and delivery (plan 02 section 6).

    SIMPLIFICATION vs the dashboard, all flagged in plan 02 section 6.1:

    * The 12-hour controlled accrual is measured from native-row intervals rather than
      waterfall scaffold hours.
    * The 2-hour stability window requires 2 hours of rows meeting FiO2/PEEP criteria,
      not 2 *contiguous* scaffold hours with a 90-minute gap rule.
    * The norepinephrine-equivalent criterion is NOT implemented. Adding it needs
      ``standardize_dose_to_base_units`` plus ASOF-merged weights; until then eligibility
      is slightly too permissive and the denominator slightly too large.
    """
    controlled = set(p["controlled_modes_2_1"] + p["controlled_modes_3_0"])
    controlled = {m.lower() for m in controlled}
    support = {m.lower() for m in p["support_modes_2_1"] + p["support_modes_3_0"]}
    trail = pd.Timedelta(hours=p["trailing_native_cap_hours"])
    paralytic_segs = paralytic_segs or {}

    rows = []
    for hid, g in resp.groupby("hospitalization_id"):
        if hid not in windows:
            continue
        w0, w1 = windows[hid]
        g = g.sort_values("recorded_dttm")
        times = g["recorded_dttm"].tolist()
        recs = g.to_dict("records")

        # Classify each native row and build its interval.
        episodes = []
        for i, r in enumerate(recs):
            t = r["recorded_dttm"]
            nxt = times[i + 1] if i + 1 < len(times) else None
            end = t + trail if nxt is None else min(nxt, t + trail)
            dev = str(r.get("device_category") or "").strip().lower()
            mode = str(r.get("mode_category") or "").strip().lower()
            peep = _num(r.get("peep_set"))
            ps = _num(r.get("pressure_support_set"))
            fio2 = _num(r.get("fio2_set"))
            trach = _num(r.get("tracheostomy"))

            if dev == vocab["imv_device"] and mode in controlled:
                cls = "controlled"
            elif mode in support:
                # CPAP arm: device is cpap, or pressure support is null/zero. CPAP
                # pressure is read from peep_set because CLIF has no dedicated column.
                is_cpap_arm = dev == vocab["cpap_device"] or not np.isfinite(ps) or ps == 0
                cap_peep = p["cpap_peep_max"] if is_cpap_arm else p["ps_peep_max"]
                cls = "sbt_support" if np.isfinite(peep) and peep <= cap_peep else "support_other"
            else:
                cls = "other"

            episodes.append(
                {"t": t, "end": end, "cls": cls, "fio2": fio2, "peep": peep,
                 "trach": trach}
            )

        if not episodes:
            continue

        ep = pd.DataFrame(episodes)
        ep["prev_cls"] = ep["cls"].shift()

        # Cumulative controlled hours before each timestamp.
        ep["ctrl_h"] = np.where(
            ep["cls"] == "controlled",
            (ep["end"] - ep["t"]).dt.total_seconds() / 3600.0,
            0.0,
        )
        ep["cum_ctrl_h"] = ep["ctrl_h"].cumsum().shift(fill_value=0.0)

        # Stability per row (SIMPLIFICATION: no contiguity requirement, no NEE).
        ep["stable"] = (
            (ep["fio2"] <= p["fio2_max"]) & (ep["peep"] <= p["peep_max"])
        ).fillna(False)
        ep["stable_h"] = np.where(
            ep["stable"], (ep["end"] - ep["t"]).dt.total_seconds() / 3600.0, 0.0
        )

        # A transition is a qualifying support episode preceded by a controlled one.
        ep["is_transition"] = (ep["cls"] == "sbt_support") & (ep["prev_cls"] == "controlled")
        ep["dur_min"] = (ep["end"] - ep["t"]).dt.total_seconds() / 60.0

        for day, day_in, day_out in split_at_midnight(w0, w1):
            in_day = ep[(ep["t"] >= day_in) & (ep["t"] < day_out)]
            if in_day.empty:
                continue

            prior = ep[ep["t"] < day_in]
            prior_ctrl_h = float(prior["ctrl_h"].sum())
            stable_h = float(in_day["stable_h"].sum())

            on_trach = bool((in_day["trach"] >= 1).any()) if p["exclude_trach_days"] else False
            on_par = (
                _overlaps_day(paralytic_segs.get(hid, []), day_in, day_out)
                if p["exclude_paralytic_days"] else False
            )

            if on_trach:
                status = "excluded_trach"
            elif on_par:
                status = "excluded_paralytic"
            elif prior_ctrl_h >= p["controlled_min_hours"] and stable_h >= p["stability_min_hours"]:
                status = "eligible"
            else:
                status = "not_eligible"

            trans = in_day[in_day["is_transition"]]
            delivered = bool((trans["dur_min"] >= p["support_min_minutes"]).any())
            delivered_strict = bool(
                (trans["dur_min"] >= p["support_min_minutes_secondary"]).any()
            )
            # Parked on a spontaneous mode all day with no transition: cannot demonstrate
            # a controlled-to-support transition, so excluded from the headline denominator.
            on_spontaneous = bool((in_day["cls"] == "sbt_support").any()) and trans.empty

            rows.append(
                {
                    "hospitalization_id": hid,
                    "day": day,
                    "eligibility_status": status,
                    "eligible": status == "eligible",
                    "on_spontaneous": on_spontaneous,
                    "sbt_delivered": delivered,
                    "sbt_delivered_strict": delivered_strict,
                    "transition_candidate": status == "eligible" and not on_spontaneous,
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Domain 4 -- Prone positioning
# ---------------------------------------------------------------------------


def prone_encounters(resp, labs, position, windows, vocab, p) -> pd.DataFrame:
    """Per-encounter proning eligibility and delivery (plan 02 section 7).

    Two nested gates: an ARDS cohort at T0 (P/F <= 300 on FiO2 >= 0.4, PEEP >= 5), then
    PROSEVA-strict eligibility (P/F <= 150 on FiO2 >= 0.6, PEEP >= 5, sustained such that
    another qualifying gas exists at or after T_first + 12 h).
    """
    ards, elig = p["ards_cohort"], p["eligibility"]
    tol = pd.Timedelta(hours=ards["abg_match_tolerance_hours"])
    lo, hi = ards["pf_in_band"]

    # Arterial oxygen values, matched backward to the prevailing ventilator settings.
    abg = labs[_lower(labs["lab_category"]) == "po2_arterial"].copy()
    if abg.empty or resp.empty:
        return pd.DataFrame(
            columns=["hospitalization_id", "in_ards_cohort", "proseva_eligible",
                     "ever_proned", "ineligibility_reason"]
        )
    abg["pao2"] = pd.to_numeric(abg["lab_value_numeric"], errors="coerce")
    abg["abg_time"] = abg.get("lab_collect_dttm", abg["lab_result_dttm"])
    abg = abg.dropna(subset=["pao2", "abg_time"]).sort_values("abg_time")

    vent = resp[[
        "hospitalization_id", "recorded_dttm", "device_category", "fio2_set", "peep_set"
    ]].copy()
    vent["device_category"] = _lower(vent["device_category"])
    vent = vent.dropna(subset=["recorded_dttm"]).sort_values("recorded_dttm")

    pf = pd.merge_asof(
        abg[["hospitalization_id", "abg_time", "pao2"]],
        vent,
        left_on="abg_time",
        right_on="recorded_dttm",
        by="hospitalization_id",
        direction="backward",
        tolerance=tol,
    ).dropna(subset=["fio2_set"])

    # FiO2 as a fraction. Percent detection runs BEFORE any range clipping, or clipping
    # would destroy the signal the detector needs (plan 02 section 11, trap 10).
    if pf["fio2_set"].quantile(0.95) > 1.5:
        pf["fio2_set"] = pf["fio2_set"] / 100.0

    pf["pf_ratio"] = pf["pao2"] / pf["fio2_set"]
    pf = pf[pf["pf_ratio"].between(lo, hi)]

    prone_by_hosp = {}
    if not position.empty:
        pos = position.copy()
        pos["position_category"] = _lower(pos["position_category"])
        for hid, g in pos.groupby("hospitalization_id"):
            prone_by_hosp[hid] = set(g["position_category"].dropna())

    rows = []
    for hid, (w0, w1) in windows.items():
        g = pf[(pf["hospitalization_id"] == hid) & pf["abg_time"].between(w0, w1)]
        g = g.sort_values("abg_time")

        in_ards = False
        proseva = False
        reason = "no post-T0 ABGs" if g.empty else ""

        if not g.empty:
            is_imv = g["device_category"] == vocab["imv_device"]
            ards_ok = (
                is_imv
                & (g["peep_set"] >= ards["peep_min"])
                & (g["fio2_set"] >= ards["fio2_min"])
                & (g["pf_ratio"] <= ards["pf_max"])
            )
            in_ards = bool(ards_ok.any())

            strict = (
                is_imv
                & (g["peep_set"] >= elig["peep_min"])
                & (g["fio2_set"] >= elig["fio2_min"])
                & (g["pf_ratio"] <= elig["pf_max"])
            )
            if not strict.any():
                reason = "no ABG meets PROSEVA-strict thresholds"
            else:
                t_first = g.loc[strict, "abg_time"].iloc[0]
                t_eligible = t_first + pd.Timedelta(hours=elig["sustained_hours"])
                # T_eligible is exactly T_first + 12 h, not the confirming gas's time.
                confirmed = bool((strict & (g["abg_time"] >= t_eligible)).any())
                if confirmed:
                    proseva = True
                    reason = ""
                else:
                    reason = (
                        "qualifying ABG at T_first but no qualifying ABG >=12h later"
                    )

        cats = prone_by_hosp.get(hid, set())
        rows.append(
            {
                "hospitalization_id": hid,
                "in_ards_cohort": in_ards,
                "proseva_eligible": proseva and in_ards,
                "ever_proned": "prone" in cats,
                "position_data_present": bool(cats),
                "ineligibility_reason": reason,
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Unit-level aggregation and the composite score
# ---------------------------------------------------------------------------


def composite_q(unit_df: pd.DataFrame, weights: dict, min_domains: int) -> pd.DataFrame:
    """Weighted average of the four domain proportions (plan 02 section 8).

    Missing domains are NOT scored as zero. Weights are renormalized over the domains a
    unit actually has, and units with too few estimable domains get no score at all.
    """
    cols = {
        "p_ltvv": weights.get("w_ltvv"),
        "p_sat": weights.get("w_sat"),
        "p_sbt": weights.get("w_sbt"),
        "p_prone": weights.get("w_prone"),
    }
    out = unit_df.copy()

    if any(w is None for w in cols.values()):
        out["n_estimable_domains"] = out[list(cols)].notna().sum(axis=1)
        out["Q"] = np.nan
        out["Q_std"] = np.nan
        return out

    num = sum(
        out[c].fillna(0.0) * w * out[c].notna().astype(float) for c, w in cols.items()
    )
    den = sum(w * out[c].notna().astype(float) for c, w in cols.items())

    out["n_estimable_domains"] = out[list(cols)].notna().sum(axis=1)
    out["Q"] = np.where(
        out["n_estimable_domains"] >= min_domains, num / den.replace(0, np.nan), np.nan
    )
    sd = out["Q"].std(ddof=1)
    out["Q_std"] = (out["Q"] - out["Q"].mean()) / sd if sd and np.isfinite(sd) else np.nan
    return out


def day_unit_attribution(adt: pd.DataFrame, windows: dict) -> pd.DataFrame:
    """Map each patient-day to a unit by the earliest ICU interval that day.

    This is the dashboard's "start-of-day" rule (plan 02 section 2.1), which its
    ``docs/determinism.md`` notes is unique by construction and never ties. A patient who
    transfers mid-day counts entirely toward the unit that held them at the start of the
    day.
    """
    from utils.cohort import build_icu_intervals

    by_hosp = dict(tuple(adt.groupby("hospitalization_id")))
    rows = []
    for hid, (w0, w1) in windows.items():
        g = by_hosp.get(hid)
        if g is None:
            continue
        ivs = build_icu_intervals(g)
        for day, day_in, day_out in split_at_midnight(w0, w1):
            overlapping = [(s, e, u) for s, e, u in ivs if s < day_out and e > day_in]
            if not overlapping:
                continue
            _, _, unit = min(overlapping, key=lambda x: max(x[0], day_in))
            rows.append({"hospitalization_id": hid, "day": day, "location_name": unit})
    return pd.DataFrame(rows)


def aggregate_day_domain(
    days: pd.DataFrame,
    attribution: pd.DataFrame,
    numerator_col: str,
    denominator_mask: pd.Series | None = None,
    label: str = "domain",
) -> pd.DataFrame:
    """Aggregate a patient-day domain to the unit level."""
    if days.empty:
        return pd.DataFrame(columns=["location_name", f"num_{label}", f"den_{label}",
                                     f"p_{label}"])
    df = days.merge(attribution, on=["hospitalization_id", "day"], how="inner")
    if denominator_mask is not None:
        df = df[denominator_mask.reindex(df.index, fill_value=False)]
    out = (
        df.groupby("location_name")
        .agg(**{
            f"num_{label}": (numerator_col, "sum"),
            f"den_{label}": (numerator_col, "size"),
        })
        .reset_index()
    )
    out[f"p_{label}"] = out[f"num_{label}"] / out[f"den_{label}"].replace(0, np.nan)
    return out
