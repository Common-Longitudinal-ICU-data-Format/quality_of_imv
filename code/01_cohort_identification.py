# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "marimo",
#     "pandas",
#     "numpy",
#     "matplotlib",
#     "pyarrow",
# ]
# ///

import marimo

__generated_with = "0.20.4"
app = marimo.App(width="medium")


@app.cell
def _(mo):
    mo.md(
        r"""
        # 1 — Cohort Identification

        **Plan:** [`analysis_plan/01_cohort_identification.md`](../analysis_plan/01_cohort_identification.md)

        All adults with IMV > 4 hours admitted to an ICU. Produces a Table 1, a STROBE
        diagram, and the eligible `hospitalization_id` list consumed by notebooks 02 and 03.

        **Time zero** is the first moment the patient is simultaneously in an ICU *and* past
        4 cumulative hours of IMV. Logic lives in `utils/cohort.py` with edge-case tests in
        `utils/test_cohort.py`.
        """
    )
    return


@app.cell
def _():
    import json
    import sys
    from pathlib import Path

    import marimo as mo
    import numpy as np
    import pandas as pd

    # Notebooks live in code/ but are run from the project root.
    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from utils.cohort import build_icu_intervals, build_imv_intervals, compute_time_zero
    from utils.project_config import (
        FINAL_DIR,
        INTERMEDIATE_DIR,
        get_vocab,
        load_clif_config,
        load_params,
    )

    return (
        FINAL_DIR,
        INTERMEDIATE_DIR,
        ROOT,
        build_icu_intervals,
        build_imv_intervals,
        compute_time_zero,
        get_vocab,
        json,
        load_clif_config,
        load_params,
        mo,
        np,
        pd,
    )


@app.cell
def _(get_vocab, load_clif_config, load_params, mo):
    params = load_params()
    clif_config = load_clif_config()

    CLIF_VERSION = params["clif_version"]
    VOCAB = get_vocab(CLIF_VERSION)
    COHORT_P = params["cohort"]

    USING_REAL_DATA = clif_config is not None

    source_banner = mo.md(
        f"""
        /// attention | Data source: **{"site CLIF database" if USING_REAL_DATA else "SYNTHETIC DEMO DATA"}**

        {
            f"Loading from `{clif_config['data_directory']}` "
            f"(`{clif_config['filetype']}`, timezone `{clif_config['timezone']}`) "
            f"for site **{clif_config.get('site_name', 'unnamed')}**."
            if USING_REAL_DATA
            else "No `config/config.json` found, so this run uses synthetic data from "
                 "`utils/synthetic_clif.py`. Numbers below are **not real**. Copy "
                 "`config/config_template.json` to `config/config.json` and fill it in to "
                 "run against your site."
        }

        CLIF version **{CLIF_VERSION}** — IMV device category is `{VOCAB["imv_device"]}`.
        ///
        """
    )
    source_banner
    return CLIF_VERSION, COHORT_P, USING_REAL_DATA, VOCAB, clif_config, params


@app.cell
def _(USING_REAL_DATA, clif_config, mo):
    # ------------------------------------------------------------------
    # Load CLIF tables.
    #
    # PLACEHOLDER FOR REAL-DATABASE DEVELOPMENT: the clifpy branch below is written
    # against the clifpy 2.1 API but has not been run against a real CLIF database.
    # Expect to adjust column names and filters at first contact with site data.
    # ------------------------------------------------------------------
    TABLES = [
        "patient",
        "hospitalization",
        "adt",
        "respiratory_support",
        "vitals",
        "labs",
        "medication_admin_continuous",
        "patient_assessments",
        "position",
    ]

    if USING_REAL_DATA:
        from clifpy import ClifOrchestrator

        co = ClifOrchestrator(config_path="config/config.json")
        co.initialize(tables=TABLES)
        tbl = {name: getattr(co, name).df for name in TABLES}
        site_name = clif_config.get("site_name", "unnamed")
    else:
        from utils.synthetic_clif import make_demo_tables

        co = None
        tbl = make_demo_tables()
        site_name = "DEMO"

    shapes = mo.ui.table(
        [{"table": k, "rows": len(v), "columns": len(v.columns)} for k, v in tbl.items()],
        selection=None,
    )
    shapes
    return TABLES, co, shapes, site_name, tbl


@app.cell
def _(mo):
    mo.md(r"""## Step 1 — Adults""")
    return


@app.cell
def _(COHORT_P, tbl):
    hosp = tbl["hospitalization"].copy()

    n_all_hosp = hosp["hospitalization_id"].nunique()
    n_all_pat = hosp["patient_id"].nunique()

    adults = hosp[hosp["age_at_admission"] >= COHORT_P["min_age_years"]].copy()
    n_excl_peds = n_all_hosp - adults["hospitalization_id"].nunique()
    return adults, hosp, n_all_hosp, n_all_pat, n_excl_peds


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Step 2 — Time zero

        For each adult hospitalization, build IMV intervals and ICU intervals, then solve

        $$t^0 = \min\{\, t : \mathrm{ICU}(t) = 1 \ \text{and} \ A(t) \ge 4\text{h} \,\}$$

        where $A(t)$ is cumulative IMV time. A `None` result means the patient never
        qualified, and the reason is recorded for the STROBE diagram.
        """
    )
    return


@app.cell
def _(
    COHORT_P,
    VOCAB,
    adults,
    build_icu_intervals,
    build_imv_intervals,
    compute_time_zero,
    pd,
    tbl,
):
    adt_by_hosp = dict(tuple(tbl["adt"].groupby("hospitalization_id")))
    resp_by_hosp = dict(tuple(tbl["respiratory_support"].groupby("hospitalization_id")))

    THRESHOLD_H = COHORT_P["imv_hours_threshold"]
    MAX_GAP_H = COHORT_P["device_carry_forward_max_hours"]
    TRAIL_CLIP_H = COHORT_P["device_trailing_clip_hours"]

    rows = []
    for _, hrow in adults.iterrows():
        hid = hrow["hospitalization_id"]

        resp_h = resp_by_hosp.get(hid, pd.DataFrame(columns=["recorded_dttm", "device_category"]))
        adt_h = adt_by_hosp.get(hid)

        imv_iv = build_imv_intervals(
            resp_h,
            imv_device=VOCAB["imv_device"],
            max_gap_hours=MAX_GAP_H,
            trailing_clip_hours=TRAIL_CLIP_H,
        )
        icu_iv = [] if adt_h is None else build_icu_intervals(adt_h)

        total_imv_h = (
            sum((e - s).total_seconds() for s, e in imv_iv) / 3600.0 if imv_iv else 0.0
        )

        # Classify the exclusion reason, in the STROBE order of plan 01 section 7.
        if not icu_iv:
            reason = "no_icu_stay"
        elif not imv_iv:
            reason = "no_imv"
        elif total_imv_h <= THRESHOLD_H:
            reason = "imv_le_threshold"
        else:
            reason = None

        t0 = None if reason else compute_time_zero(imv_iv, icu_iv, THRESHOLD_H)
        if reason is None and t0 is None:
            reason = "threshold_never_in_icu"

        rows.append(
            {
                "hospitalization_id": hid,
                "patient_id": hrow["patient_id"],
                "admission_dttm": hrow["admission_dttm"],
                "discharge_dttm": hrow["discharge_dttm"],
                "age_at_admission": hrow["age_at_admission"],
                "discharge_category": hrow["discharge_category"],
                "total_imv_hours": total_imv_h,
                "imv_start": imv_iv[0][0] if imv_iv else pd.NaT,
                "imv_end": imv_iv[-1][1] if imv_iv else pd.NaT,
                "exclusion_reason": reason,
                "time_zero": t0["time_zero"] if t0 else pd.NaT,
                "location_name": t0["location_name"] if t0 else None,
                "imv_hours_at_t0": t0["imv_hours_at_t0"] if t0 else float("nan"),
                "intubated_before_icu": t0["intubated_before_icu"] if t0 else None,
            }
        )

    screened = pd.DataFrame(rows)
    return MAX_GAP_H, TRAIL_CLIP_H, THRESHOLD_H, adt_by_hosp, resp_by_hosp, screened


@app.cell
def _(mo, screened):
    reason_counts = (
        screened["exclusion_reason"]
        .fillna("INCLUDED")
        .value_counts()
        .rename_axis("outcome")
        .reset_index(name="hospitalizations")
    )
    mo.ui.table(reason_counts, selection=None)
    return (reason_counts,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Step 3 — Remaining exclusions and unit attribution

        Tracheostomy and ECMO at time zero are **placeholders**: both are open decisions in
        plan 01 section 5, and identifying them needs site-specific fields. The hooks are
        wired so the STROBE counts stay correct once the definitions are settled.
        """
    )
    return


@app.cell
def _(COHORT_P, np, pd, screened, site_name, tbl):
    eligible = screened[screened["exclusion_reason"].isna()].copy()

    # --- PLACEHOLDER: tracheostomy at time zero -----------------------------
    # Plan 01 section 5, open decision. Needs respiratory_support.tracheostomy carried
    # forward to time zero, and only distinguishes trach from ETT where sites populate it.
    resp_all = tbl["respiratory_support"]
    if COHORT_P["exclude_tracheostomy_at_t0"] and "tracheostomy" in resp_all.columns:
        trach_at_t0 = (
            resp_all.merge(
                eligible[["hospitalization_id", "time_zero"]], on="hospitalization_id"
            )
            .query("recorded_dttm <= time_zero and tracheostomy >= 1")["hospitalization_id"]
            .unique()
        )
    else:
        trach_at_t0 = np.array([], dtype=object)

    # --- PLACEHOLDER: ECMO at time zero -------------------------------------
    # Plan 01 section 5, open decision. CLIF 3.0 has an ecmo_mcs table; under 2.1 this
    # needs a site-specific source. Left empty deliberately rather than guessed.
    ecmo_at_t0 = np.array([], dtype=object)

    eligible["excluded_trach"] = eligible["hospitalization_id"].isin(trach_at_t0)
    eligible["excluded_ecmo"] = eligible["hospitalization_id"].isin(ecmo_at_t0)

    n_excl_trach = int(eligible["excluded_trach"].sum())
    n_excl_ecmo = int((~eligible["excluded_trach"] & eligible["excluded_ecmo"]).sum())

    cohort = eligible[~eligible["excluded_trach"] & ~eligible["excluded_ecmo"]].copy()

    # One episode per hospitalization (plan 01 section 2), and the site/unit keys.
    if COHORT_P["first_episode_per_hospitalization_only"]:
        cohort = cohort.sort_values("time_zero").drop_duplicates("hospitalization_id")

    cohort["site"] = site_name
    cohort["unit_key"] = cohort["site"] + " | " + cohort["location_name"].astype(str)

    # Unit metadata supplies hospital_id and location_type. CLIF has no hospital
    # identifier above location_name, so this mapping has to come from the site --
    # see config/README.md and plan 03 section 6.
    meta_path = ROOT / "config" / "unit_metadata.csv"
    if meta_path.exists():
        unit_meta = pd.read_csv(meta_path)
    elif "unit_metadata" in tbl:
        unit_meta = tbl["unit_metadata"]
    else:
        unit_meta = pd.DataFrame(
            columns=["location_name", "hospital_id", "location_type"]
        )

    meta_cols = [
        c for c in ("location_name", "hospital_id", "location_type", "hospital_beds",
                    "academic")
        if c in unit_meta.columns
    ]
    cohort = cohort.merge(unit_meta[meta_cols], on="location_name", how="left")

    # A missing hospital_id would collapse the nested random effect in plan 03 into a
    # single hospital without warning, so fall back to the site and flag it.
    n_missing_hosp = int(cohort["hospital_id"].isna().sum()) if "hospital_id" in cohort else len(cohort)
    if "hospital_id" not in cohort.columns:
        cohort["hospital_id"] = cohort["site"]
    cohort["hospital_id"] = cohort["hospital_id"].fillna(cohort["site"])

    # Outcomes, for Table 1 description and for notebook 03.
    cohort["died_in_hospital"] = (
        cohort["discharge_category"].astype("string").str.lower().eq("expired")
    )
    cohort["survived_to_discharge"] = ~cohort["died_in_hospital"]
    cohort["icu_los_hours"] = (
        cohort["discharge_dttm"] - cohort["time_zero"]
    ).dt.total_seconds() / 3600.0
    cohort["imv_hours_after_t0"] = (
        cohort["imv_end"] - cohort["time_zero"]
    ).dt.total_seconds() / 3600.0

    # Ventilator-free days at 28 days, with death forced to 0 (plan 03 section 2).
    VFD_HORIZON = 28
    vent_days = (cohort["imv_hours_after_t0"].clip(lower=0) / 24.0).clip(upper=VFD_HORIZON)
    cohort["vfd_28"] = np.where(
        cohort["died_in_hospital"], 0.0, (VFD_HORIZON - vent_days).clip(lower=0)
    )

    cohort = cohort.reset_index(drop=True)
    return (
        VFD_HORIZON,
        cohort,
        n_missing_hosp,
        unit_meta,
        meta_cols,
        meta_path,
        ecmo_at_t0,
        eligible,
        n_excl_ecmo,
        n_excl_trach,
        resp_all,
        trach_at_t0,
        vent_days,
    )


@app.cell
def _(mo):
    mo.md(r"""## STROBE diagram""")
    return


@app.cell
def _(cohort, n_all_hosp, n_all_pat, n_excl_ecmo, n_excl_peds, n_excl_trach,
      n_missing_hosp, screened):
    def _n(reason):
        return int((screened["exclusion_reason"] == reason).sum())

    n_adults = int(len(screened))
    n_no_icu = _n("no_icu_stay")
    n_no_imv = _n("no_imv")
    n_short = _n("imv_le_threshold")
    n_not_icu_at_threshold = _n("threshold_never_in_icu")

    strobe = {
        "all_hospitalizations": n_all_hosp,
        "all_patients": n_all_pat,
        "excluded_age_lt_18": int(n_excl_peds),
        "adult_hospitalizations": n_adults,
        "excluded_no_icu_stay": n_no_icu,
        "adult_with_icu": n_adults - n_no_icu,
        "excluded_no_imv": n_no_imv,
        "adult_icu_with_imv": n_adults - n_no_icu - n_no_imv,
        "excluded_imv_le_4h": n_short,
        "adult_icu_imv_gt_4h": n_adults - n_no_icu - n_no_imv - n_short,
        "excluded_threshold_never_in_icu": n_not_icu_at_threshold,
        "excluded_tracheostomy_at_t0": int(n_excl_trach),
        "excluded_ecmo_at_t0": int(n_excl_ecmo),
        "analytic_cohort": int(len(cohort)),
        "analytic_cohort_patients": int(cohort["patient_id"].nunique()),
        "n_units": int(cohort["unit_key"].nunique()),
        "n_hospitals": int(cohort["hospital_id"].nunique()),
        "patients_missing_hospital_id": int(n_missing_hosp),
    }
    return (
        n_adults,
        n_no_icu,
        n_no_imv,
        n_not_icu_at_threshold,
        n_short,
        strobe,
    )


@app.cell
def _(strobe):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    STROBE_STEPS = [
        ("All hospitalizations", "all_hospitalizations", None),
        ("Adults (age ≥ 18)", "adult_hospitalizations", "excluded_age_lt_18"),
        ("With an ICU stay", "adult_with_icu", "excluded_no_icu_stay"),
        ("With any IMV", "adult_icu_with_imv", "excluded_no_imv"),
        ("IMV > 4 hours", "adult_icu_imv_gt_4h", "excluded_imv_le_4h"),
        ("ANALYTIC COHORT", "analytic_cohort", "excluded_threshold_never_in_icu"),
    ]

    EXCL_LABELS = {
        "excluded_age_lt_18": "age < 18",
        "excluded_no_icu_stay": "no ICU stay",
        "excluded_no_imv": "no IMV",
        "excluded_imv_le_4h": "IMV ≤ 4 h",
        "excluded_threshold_never_in_icu": "4 h threshold never reached in an ICU",
    }

    fig_strobe, ax_strobe = plt.subplots(figsize=(8.5, 8.0))
    ax_strobe.set_xlim(0, 10)
    ax_strobe.set_ylim(0, len(STROBE_STEPS) * 2)
    ax_strobe.axis("off")

    for i, (label, key, excl_key) in enumerate(STROBE_STEPS):
        y = (len(STROBE_STEPS) - i) * 2 - 1
        bold = key == "analytic_cohort"
        ax_strobe.annotate(
            f"{label}\nN = {strobe[key]:,}",
            xy=(2.6, y),
            ha="center",
            va="center",
            fontsize=10,
            fontweight="bold" if bold else "normal",
            bbox=dict(
                boxstyle="round,pad=0.5",
                facecolor="#dbeafe" if bold else "#f1f5f9",
                edgecolor="#1e3a8a" if bold else "#64748b",
                linewidth=1.6 if bold else 1.0,
            ),
        )
        if i < len(STROBE_STEPS) - 1:
            ax_strobe.annotate(
                "", xy=(2.6, y - 1.35), xytext=(2.6, y - 0.62),
                arrowprops=dict(arrowstyle="-|>", color="#334155", linewidth=1.2),
            )
        nxt = STROBE_STEPS[i + 1][2] if i < len(STROBE_STEPS) - 1 else None
        if nxt:
            extra = ""
            if nxt == "excluded_threshold_never_in_icu":
                more = [
                    f"tracheostomy at t₀: n = {strobe['excluded_tracheostomy_at_t0']:,}",
                    f"ECMO at t₀: n = {strobe['excluded_ecmo_at_t0']:,}",
                ]
                extra = "\n" + "\n".join(more)
            ax_strobe.annotate(
                f"excluded: {EXCL_LABELS[nxt]}\nn = {strobe[nxt]:,}{extra}",
                xy=(6.3, y - 1.0),
                ha="left",
                va="center",
                fontsize=8.5,
                color="#7f1d1d",
                bbox=dict(boxstyle="round,pad=0.35", facecolor="#fef2f2",
                          edgecolor="#fca5a5", linewidth=0.9),
            )
            ax_strobe.annotate(
                "", xy=(6.2, y - 1.0), xytext=(2.65, y - 1.0),
                arrowprops=dict(arrowstyle="-|>", color="#9ca3af", linewidth=1.0),
            )

    ax_strobe.set_title(
        "STROBE — CLIF IMV quality cohort", fontsize=12, fontweight="bold", pad=4
    )
    fig_strobe.tight_layout()
    fig_strobe
    return EXCL_LABELS, STROBE_STEPS, ax_strobe, fig_strobe, matplotlib, plt


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Table 1

        Stratified by unit here. The manuscript version stratifies by unit quality-score
        quartile, which needs notebook 02's output — plan 01 section 8.

        **PLACEHOLDER:** the severity block (six SOFA components from the 4-hour
        presentation window) is computed in notebook 03, where the window is defined, and
        should be merged in here once that step is settled. Plan 01 section 8 requires a
        missingness column for every variable, which also waits on real data.
        """
    )
    return


@app.cell
def _(cohort, np, pd, tbl):
    def _median_iqr(s):
        s = pd.to_numeric(s, errors="coerce").dropna()
        if s.empty:
            return "—"
        return f"{s.median():.1f} ({s.quantile(0.25):.1f}–{s.quantile(0.75):.1f})"

    def _pct(s):
        s = s.dropna()
        if s.empty:
            return "—"
        return f"{int(s.sum()):,} ({100 * s.mean():.1f}%)"

    t1_base = cohort.merge(
        tbl["patient"][["patient_id", "sex_category", "race_category", "ethnicity_category"]],
        on="patient_id",
        how="left",
    )

    def _table1_for(df):
        out = {
            "N": f"{len(df):,}",
            "Age, median (IQR)": _median_iqr(df["age_at_admission"]),
            "Female": _pct(df["sex_category"].eq("Female")),
            "Intubated before ICU arrival": _pct(df["intubated_before_icu"].astype("boolean")),
            "IMV hours accrued at time zero, median (IQR)": _median_iqr(df["imv_hours_at_t0"]),
            "Total IMV hours, median (IQR)": _median_iqr(df["total_imv_hours"]),
            "IMV hours after time zero, median (IQR)": _median_iqr(df["imv_hours_after_t0"]),
            "Hours from time zero to discharge, median (IQR)": _median_iqr(df["icu_los_hours"]),
            "In-hospital mortality": _pct(df["died_in_hospital"]),
            "VFD at day 28, median (IQR)": _median_iqr(df["vfd_28"]),
        }
        return out

    table1 = pd.DataFrame(
        {"Overall": _table1_for(t1_base)}
        | {
            str(unit): _table1_for(grp)
            for unit, grp in t1_base.groupby("location_name")
        }
    )
    table1.index.name = "Variable"
    table1 = table1.reset_index()
    return t1_base, table1


@app.cell
def _(mo, table1):
    mo.ui.table(table1, selection=None, page_size=15)
    return


@app.cell
def _(mo):
    mo.md(r"""## Data-quality checks (plan 01 section 11)""")
    return


@app.cell
def _(THRESHOLD_H, cohort, mo, pd, tbl):
    checks = []

    def _check(name, ok, detail):
        checks.append({"check": name, "status": "PASS" if ok else "FAIL", "detail": detail})

    # 1. Time zero falls inside the hospitalization.
    inside = (
        cohort["time_zero"].between(cohort["admission_dttm"], cohort["discharge_dttm"])
    )
    _check(
        "time_zero within hospitalization",
        bool(inside.all()),
        f"{int((~inside).sum())} violation(s)",
    )

    # 2. Time zero falls inside an ICU stay in adt.
    icu_adt = tbl["adt"].copy()
    icu_adt["location_category"] = (
        icu_adt["location_category"].astype("string").str.lower()
    )
    icu_adt = icu_adt[icu_adt["location_category"] == "icu"]
    t0_in_icu = (
        cohort[["hospitalization_id", "time_zero", "location_name"]]
        .merge(icu_adt, on="hospitalization_id", how="left", suffixes=("", "_adt"))
        .assign(
            ok=lambda d: d["time_zero"].between(d["in_dttm"], d["out_dttm"])
            & d["location_name"].eq(d["location_name_adt"])
        )
        .groupby("hospitalization_id")["ok"]
        .any()
    )
    _check(
        "time_zero inside the attributed ICU stay",
        bool(t0_in_icu.all()),
        f"{int((~t0_in_icu).sum())} violation(s)",
    )

    # 3. Timezone consistency: mixed naive/aware silently breaks durations.
    tzs = {
        name: str(getattr(df[col].dtype, "tz", None))
        for name, df in tbl.items()
        for col in df.columns
        if col.endswith("_dttm")
    }
    _check(
        "consistent datetime timezone across tables",
        len(set(tzs.values())) <= 1,
        f"tz values seen: {sorted(set(tzs.values()))}",
    )

    # 4. IMV durations are plausible.
    bad_dur = (
        (cohort["total_imv_hours"] <= THRESHOLD_H)
        | (cohort["total_imv_hours"] > cohort["icu_los_hours"] + cohort["imv_hours_at_t0"] + 24)
    )
    _check(
        "IMV duration plausible",
        bool(~bad_dur.any()),
        f"{int(bad_dur.sum())} implausible duration(s)",
    )

    # 5. location_name cardinality: free text would fragment units.
    n_units = cohort["location_name"].nunique()
    _check(
        "ICU location_name cardinality is small enough to be real units",
        n_units <= 60,
        f"{n_units} distinct ICU location_name value(s)",
    )

    # 6. Unit denominators.
    per_unit = cohort.groupby("unit_key").size().sort_values()
    _check(
        "every unit has ≥ 20 patients",
        bool((per_unit >= 20).all()),
        f"smallest unit n = {int(per_unit.min())} ({per_unit.idxmin()})",
    )

    # 7. device_category coverage.
    dev = tbl["respiratory_support"]["device_category"]
    cov = 1.0 - dev.isna().mean()
    _check(
        "respiratory_support.device_category coverage ≥ 95%",
        cov >= 0.95,
        f"{100 * cov:.1f}% non-null",
    )

    checks_df = pd.DataFrame(checks)
    mo.ui.table(checks_df, selection=None)
    return checks, checks_df, cov, dev, icu_adt, inside, n_units, per_unit, t0_in_icu, tzs


@app.cell
def _(mo):
    mo.md(r"""## Write outputs""")
    return


@app.cell
def _(
    FINAL_DIR,
    INTERMEDIATE_DIR,
    checks_df,
    cohort,
    fig_strobe,
    json,
    mo,
    strobe,
    table1,
):
    INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    # PHI — gitignored.
    cohort.to_parquet(INTERMEDIATE_DIR / "cohort.parquet", index=False)
    cohort[["hospitalization_id"]].to_csv(
        INTERMEDIATE_DIR / "hospitalization_ids.csv", index=False
    )

    # Aggregate — shareable.
    (FINAL_DIR / "strobe_counts.json").write_text(json.dumps(strobe, indent=2))
    table1.to_csv(FINAL_DIR / "table1.csv", index=False)
    table1.to_html(FINAL_DIR / "table1.html", index=False)
    checks_df.to_csv(FINAL_DIR / "data_quality_checks.csv", index=False)
    fig_strobe.savefig(FINAL_DIR / "strobe_diagram.png", dpi=150, bbox_inches="tight")

    mo.md(
        f"""
        Wrote:

        - `output/intermediate_phi/cohort.parquet` — {len(cohort):,} rows **(PHI)**
        - `output/intermediate_phi/hospitalization_ids.csv` **(PHI)**
        - `output/final_no_phi/table1.csv`, `table1.html`
        - `output/final_no_phi/strobe_counts.json`, `strobe_diagram.png`
        - `output/final_no_phi/data_quality_checks.csv`

        **Cohort: {len(cohort):,} hospitalizations across {cohort["unit_key"].nunique()} units in {cohort["hospital_id"].nunique()} hospital(s).**
        """
    )
    return


if __name__ == "__main__":
    app.run()
