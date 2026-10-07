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
        # 2 — Unit-Level IMV Quality Score

        **Plan:** [`analysis_plan/02_quality_score.md`](../analysis_plan/02_quality_score.md)

        Performance in each of four domains per ICU `location_name`, combined into

        $$Q_i = w_1\, p^{\mathrm{LTVV}}_i + w_2\, p^{\mathrm{SAT}}_i + w_3\, p^{\mathrm{SBT}}_i + w_4\, p^{\mathrm{prone}}_i$$

        **Weights are intentionally unspecified** (`null` in
        `config/project_params.json`). The four domain proportions are computed and
        reported regardless; $Q_i$ appears only once the research team sets weights.

        Domain definitions are transcribed from the
        [CLIF ventilator QI dashboard](https://github.com/shanguleria/clif-ventilator-qi-dashboard)
        at commit `7ea68ec`. Implementations live in `utils/domains.py`.
        """
    )
    return


@app.cell
def _():
    import sys
    from pathlib import Path

    import marimo as mo
    import numpy as np
    import pandas as pd

    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from utils.domains import (
        active_segments,
        aggregate_day_domain,
        composite_q,
        compute_pbw,
        day_unit_attribution,
        ltvv_patient_days,
        prone_encounters,
        sat_patient_days,
        sbt_patient_days,
        scoring_windows,
    )
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
        active_segments,
        aggregate_day_domain,
        composite_q,
        compute_pbw,
        day_unit_attribution,
        get_vocab,
        load_clif_config,
        load_params,
        ltvv_patient_days,
        mo,
        np,
        pd,
        prone_encounters,
        sat_patient_days,
        sbt_patient_days,
        scoring_windows,
    )


@app.cell
def _(INTERMEDIATE_DIR, get_vocab, load_clif_config, load_params, mo, pd):
    params = load_params()
    clif_config = load_clif_config()
    QS = params["quality_score"]
    VOCAB = get_vocab(params["clif_version"])
    USING_REAL_DATA = clif_config is not None

    cohort_path = INTERMEDIATE_DIR / "cohort.parquet"
    if not cohort_path.exists():
        raise FileNotFoundError(
            f"{cohort_path} not found. Run code/01_cohort_identification.py first."
        )
    cohort = pd.read_parquet(cohort_path)

    mo.md(
        f"""
        Cohort: **{len(cohort):,} hospitalizations** across
        **{cohort["location_name"].nunique()} ICU units**
        ({"site data" if USING_REAL_DATA else "**synthetic demo data**"}).
        """
    )
    return QS, USING_REAL_DATA, VOCAB, clif_config, cohort, cohort_path, params


@app.cell
def _(USING_REAL_DATA, cohort, clif_config):
    # Load only the tables the quality domains need, filtered to the cohort.
    # Filtering at load time is the CLIF convention and matters at real-data scale.
    QS_TABLES = [
        "patient",
        "adt",
        "respiratory_support",
        "vitals",
        "labs",
        "medication_admin_continuous",
        "position",
    ]
    ids = cohort["hospitalization_id"].tolist()

    if USING_REAL_DATA:
        from clifpy import ClifOrchestrator

        co = ClifOrchestrator(config_path="config/config.json")
        co.initialize(
            tables=QS_TABLES,
            filters={t: {"hospitalization_id": ids} for t in QS_TABLES if t != "patient"},
        )
        tbl = {name: getattr(co, name).df for name in QS_TABLES}
    else:
        from utils.synthetic_clif import make_demo_tables

        co = None
        full = make_demo_tables(n_hosp=120, seed=7)
        tbl = {
            name: (
                df
                if name == "patient"
                else df[df["hospitalization_id"].isin(ids)].copy()
            )
            for name, df in full.items()
            if name in QS_TABLES
        }
    return QS_TABLES, co, ids, tbl


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Scoring window and unit attribution

        The window opens at **time zero** and closes at the end of IMV, so the score
        measures the receiving unit's practice and stays disjoint from the risk-adjustment
        window in notebook 03. Patient-days are attributed to the unit holding the patient
        at the **start of the day**.
        """
    )
    return


@app.cell
def _(cohort, day_unit_attribution, mo, scoring_windows, tbl):
    windows = scoring_windows(cohort)
    attribution = day_unit_attribution(tbl["adt"], windows)

    mo.md(
        f"""
        **{len(windows):,}** scoring windows; **{len(attribution):,}** attributed
        patient-days across **{attribution["location_name"].nunique()}** units.
        """
    )
    return attribution, windows


@app.cell
def _(mo):
    mo.md(r"""## Domain 1 — Lung-protective tidal volume""")
    return


@app.cell
def _(QS, cohort, compute_pbw, mo, tbl):
    pbw = compute_pbw(tbl["patient"], tbl["vitals"], cohort, QS["ltvv"])
    pbw_coverage = len(pbw) / max(len(cohort), 1)

    # Guard the exact-case sex_category trap (plan 02 section 4.1): a site whose
    # sex_category is "male"/"M" silently yields an all-NaN PBW and an empty LTVV
    # denominator. Fail loudly instead.
    pbw_warning = (
        None
        if pbw_coverage >= 0.80
        else mo.md(
            f"""
            /// danger | PBW coverage is only {100 * pbw_coverage:.1f}%

            Check that `patient.sex_category` uses exact-case `"Male"`/`"Female"` and that
            `vitals` contains `height_cm` within
            {QS["ltvv"]["height_min_cm"]}–{QS["ltvv"]["height_max_cm"]} cm. A low coverage
            rate here silently empties the LTVV denominator rather than raising an error.
            ///
            """
        )
    )
    pbw_warning if pbw_warning is not None else mo.md(
        f"PBW computed for **{len(pbw):,}** hospitalizations "
        f"({100 * pbw_coverage:.1f}% of the cohort)."
    )
    return pbw, pbw_coverage, pbw_warning


@app.cell
def _(QS, VOCAB, ltvv_patient_days, pbw, tbl, windows):
    ltvv_days = ltvv_patient_days(
        tbl["respiratory_support"], windows, pbw, VOCAB, QS["ltvv"]
    )
    ltvv_days_secondary = ltvv_patient_days(
        tbl["respiratory_support"], windows, pbw, VOCAB, QS["ltvv"],
        threshold=QS["ltvv"]["ml_per_kg_secondary"],
    )
    return ltvv_days, ltvv_days_secondary


@app.cell
def _(attribution, ltvv_days, ltvv_days_secondary, np, pd):
    def _ltvv_unit(days, label):
        if days.empty:
            return pd.DataFrame(columns=["location_name", f"num_{label}", f"den_{label}",
                                         f"p_{label}", f"not_assessable_{label}"])
        df = days.merge(attribution, on=["hospitalization_id", "day"], how="inner")
        g = df.groupby("location_name")
        out = pd.DataFrame(
            {
                f"num_{label}": g["status"].apply(lambda s: (s == "adherent").sum()),
                f"den_{label}": g["status"].apply(
                    lambda s: s.isin(["adherent", "non_adherent"]).sum()
                ),
                "n_total_days": g["status"].size(),
            }
        ).reset_index()
        # Headline is the assessable rate (plan 02 section 4.7).
        out[f"p_{label}"] = out[f"num_{label}"] / out[f"den_{label}"].replace(0, np.nan)
        # Crude rate keeps not-assessable days in the denominator; the gap between the
        # two is a charting-completeness measure, not a care measure.
        out[f"crude_{label}"] = out[f"num_{label}"] / out["n_total_days"].replace(0, np.nan)
        out[f"not_assessable_{label}"] = 1.0 - (
            out[f"den_{label}"] / out["n_total_days"].replace(0, np.nan)
        )
        return out

    unit_ltvv = _ltvv_unit(ltvv_days, "ltvv")
    unit_ltvv6 = _ltvv_unit(ltvv_days_secondary, "ltvv6")[
        ["location_name", "p_ltvv6", "num_ltvv6", "den_ltvv6"]
    ]
    return unit_ltvv, unit_ltvv6


@app.cell
def _(mo, unit_ltvv):
    mo.ui.table(unit_ltvv.round(3), selection=None)
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Domain 2 — Spontaneous awakening trials

        A SAT is a gap of ≥ 30 minutes in the union of active sedative infusions, on a day
        the patient was on sedation and not paralyzed. RASS is deliberately **not** used
        for eligibility, matching the dashboard.
        """
    )
    return


@app.cell
def _(QS, active_segments, aggregate_day_domain, attribution, sat_patient_days, tbl, windows):
    # Prone segments feed the SAT day exclusion (our deviation, plan 02 section 5.1).
    prone_segs = {}
    pos = tbl["position"]
    if not pos.empty and QS["sat"]["exclude_prone_days"]:
        import pandas as _pd

        p_low = pos.copy()
        p_low["position_category"] = (
            p_low["position_category"].astype("string").str.strip().str.lower()
        )
        for hid, g in p_low.groupby("hospitalization_id"):
            g = g.sort_values("recorded_dttm")
            segs, start = [], None
            for _, r in g.iterrows():
                if r["position_category"] == "prone" and start is None:
                    start = r["recorded_dttm"]
                elif r["position_category"] == "not_prone" and start is not None:
                    segs.append((start, r["recorded_dttm"]))
                    start = None
            if start is not None:
                segs.append((start, start + _pd.Timedelta(hours=16)))
            if segs:
                prone_segs[hid] = segs

    sat_days = sat_patient_days(
        tbl["medication_admin_continuous"], windows, QS["sat"], prone_segs=prone_segs
    )
    unit_sat = aggregate_day_domain(
        sat_days[sat_days["eligible"]] if not sat_days.empty else sat_days,
        attribution,
        numerator_col="sat_performed",
        label="sat",
    )
    return p_low, pos, prone_segs, sat_days, unit_sat


@app.cell
def _(mo, unit_sat):
    mo.ui.table(unit_sat.round(3), selection=None)
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Domain 3 — Spontaneous breathing trials

        A controlled → qualifying-support transition on an eligible day. The headline
        denominator is eligible **transition-candidate** days: eligible days minus days
        parked on a spontaneous mode with no transition.

        /// warning | Simplifications in this first pass

        The 12-hour controlled accrual and 2-hour stability window are approximated from
        native rows rather than waterfall scaffold hours, and the
        **norepinephrine-equivalent criterion is not yet implemented**. Eligibility is
        therefore slightly too permissive. See `utils/domains.py` and plan 02 section 6.1.
        ///
        """
    )
    return


@app.cell
def _(QS, VOCAB, active_segments, aggregate_day_domain, attribution, sbt_patient_days, tbl, windows):
    paralytic_segs = active_segments(
        tbl["medication_admin_continuous"],
        QS["sat"]["paralytic_categories"],
        QS["sat"]["trailing_cap_hours"],
    )
    sbt_days = sbt_patient_days(
        tbl["respiratory_support"], windows, VOCAB, QS["sbt"],
        paralytic_segs=paralytic_segs,
    )
    unit_sbt = aggregate_day_domain(
        sbt_days[sbt_days["transition_candidate"]] if not sbt_days.empty else sbt_days,
        attribution,
        numerator_col="sbt_delivered",
        label="sbt",
    )
    return paralytic_segs, sbt_days, unit_sbt


@app.cell
def _(mo, sbt_days, unit_sbt):
    status_mix = (
        sbt_days["eligibility_status"].value_counts().rename_axis("status")
        .reset_index(name="patient_days")
        if not sbt_days.empty
        else None
    )
    mo.vstack([mo.ui.table(unit_sbt.round(3), selection=None),
               mo.md("**SBT eligibility status mix**"),
               mo.ui.table(status_mix, selection=None)])
    return (status_mix,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Domain 4 — Prone positioning

        The only patient-level domain: proportion of PROSEVA-eligible **encounters** ever
        proned. Note the denominator is severe hypoxemia on adequate support, not
        adjudicated ARDS — CLIF has no structured imaging, so Berlin criteria cannot be
        applied.
        """
    )
    return


@app.cell
def _(QS, VOCAB, cohort, np, pd, prone_encounters, tbl, windows):
    prone_df = prone_encounters(
        tbl["respiratory_support"], tbl["labs"], tbl["position"],
        windows, VOCAB, QS["prone"],
    )

    prone_attr = prone_df.merge(
        cohort[["hospitalization_id", "location_name"]], on="hospitalization_id", how="left"
    )
    elig_prone = prone_attr[prone_attr["proseva_eligible"]]
    if QS["prone"]["require_position_data_present"]:
        elig_prone = elig_prone[elig_prone["position_data_present"]]

    unit_prone = (
        elig_prone.groupby("location_name")
        .agg(num_prone=("ever_proned", "sum"), den_prone=("ever_proned", "size"))
        .reset_index()
    )
    unit_prone["p_prone"] = (
        unit_prone["num_prone"] / unit_prone["den_prone"].replace(0, np.nan)
    )
    return elig_prone, prone_attr, prone_df, unit_prone


@app.cell
def _(mo, prone_df, unit_prone):
    mo.vstack([
        mo.md(
            f"""
            ARDS cohort (P/F ≤ 300): **{int(prone_df["in_ards_cohort"].sum()):,}** ·
            PROSEVA-eligible: **{int(prone_df["proseva_eligible"].sum()):,}** ·
            ever proned: **{int(prone_df["ever_proned"].sum()):,}**
            """
        ),
        mo.ui.table(unit_prone.round(3), selection=None),
    ])
    return


@app.cell
def _(mo):
    mo.md(r"""## Combine into the unit table""")
    return


@app.cell
def _(QS, cohort, np, pd, unit_ltvv, unit_ltvv6, unit_prone, unit_sat, unit_sbt):
    units = (
        cohort.groupby("location_name")
        .agg(n_patients=("hospitalization_id", "nunique"), site=("site", "first"))
        .reset_index()
    )
    for part in (unit_ltvv, unit_ltvv6, unit_sat, unit_sbt, unit_prone):
        units = units.merge(part, on="location_name", how="left")

    # Suppress domain proportions whose denominator is too small to be stable
    # (plan 02 section 8.2). Suppressed means missing, never zero.
    MIN_DEN = QS["min_denominator_per_domain"]
    for label in ("ltvv", "sat", "sbt", "prone"):
        den, p = f"den_{label}", f"p_{label}"
        if den in units.columns:
            units.loc[units[den].fillna(0) < MIN_DEN, p] = np.nan

    units["unit_key"] = units["site"] + " | " + units["location_name"]
    return MIN_DEN, part, units


@app.cell
def _(QS, composite_q, mo, units):
    weights = QS["weights"]
    unit_scores = composite_q(units, weights, QS["min_estimable_domains"])

    weights_set = all(
        weights.get(k) is not None for k in ("w_ltvv", "w_sat", "w_sbt", "w_prone")
    )
    weights_banner = mo.md(
        r"""
        /// attention | Weights are unspecified, so $Q$ is not computed

        `quality_score.weights` in `config/project_params.json` is all `null`, by design —
        see [plan 02 section 8.1](../analysis_plan/02_quality_score.md). The four domain
        proportions below are complete and usable; the composite column is empty until the
        research team sets weights.

        Equal weights (0.25 each) is the recommended primary. **Whatever is chosen must be
        fixed before looking at outcomes in notebook 03.**
        ///
        """
        if not weights_set
        else f"""
        Composite $Q$ computed with weights
        LTVV **{weights["w_ltvv"]}**, SAT **{weights["w_sat"]}**,
        SBT **{weights["w_sbt"]}**, prone **{weights["w_prone"]}**.
        """
    )
    weights_banner
    return unit_scores, weights, weights_banner, weights_set


@app.cell
def _(mo, unit_scores):
    DISPLAY_COLS = [
        # location_name and site are the join keys downstream -- notebook 03 reads this
        # CSV and merges on location_name, so they must be written out, not just displayed.
        "unit_key", "site", "location_name", "n_patients",
        "p_ltvv", "den_ltvv", "p_ltvv6",
        "p_sat", "den_sat",
        "p_sbt", "den_sbt",
        "p_prone", "den_prone",
        "num_ltvv", "num_sat", "num_sbt", "num_prone",
        "crude_ltvv", "not_assessable_ltvv",
        "n_estimable_domains", "Q", "Q_std",
    ]
    mo.ui.table(
        unit_scores[[c for c in DISPLAY_COLS if c in unit_scores.columns]].round(3),
        selection=None,
    )
    return (DISPLAY_COLS,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Do the domains agree with each other?

        Worth looking at before anything else. Strongly correlated domains mean the
        composite is nearly one-dimensional and the weights barely matter; uncorrelated or
        negatively correlated domains mean a single composite may hide more than it
        reveals, which is itself a finding.
        """
    )
    return


@app.cell
def _(mo, unit_scores):
    DOMAIN_COLS = ["p_ltvv", "p_sat", "p_sbt", "p_prone"]
    present = [c for c in DOMAIN_COLS if c in unit_scores.columns]
    domain_corr = unit_scores[present].corr()
    mo.vstack([
        mo.md(
            f"_Correlations across only {len(unit_scores)} units — indicative, not "
            "inferential. With few units these are very noisy._"
        ),
        mo.ui.table(domain_corr.round(3).reset_index(), selection=None),
    ])
    return DOMAIN_COLS, domain_corr, present


@app.cell
def _(MIN_DEN, present, unit_scores):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    LABELS = {
        "p_ltvv": "LTVV\n(Vt ≤ 8 mL/kg PBW)",
        "p_sat": "SAT\n(sedation interruption)",
        "p_sbt": "SBT\n(controlled → support)",
        "p_prone": "Proning\n(ever proned)",
    }

    # sharey must stay False: each panel is sorted by its own domain, so row i is a
    # DIFFERENT unit in each panel. Sharing the y axis would attach one panel's unit
    # labels to every panel's points and silently mislabel the figure.
    fig_dom, axes = plt.subplots(
        1, len(present), figsize=(3.6 * len(present), 4.4), sharey=False
    )
    axes = [axes] if len(present) == 1 else list(axes)

    for ax, col in zip(axes, present):
        d = unit_scores[["location_name", col, f"den_{col.split('_', 1)[1]}"]].dropna(
            subset=[col]
        ).sort_values(col)
        if d.empty:
            # An empty panel must say why. A domain with every unit below the minimum
            # denominator is MISSING, not zero, and a blank panel reads as zero.
            ax.text(
                0.5, 0.5,
                f"no unit reaches the\nminimum denominator\n(n ≥ {MIN_DEN})",
                ha="center", va="center", fontsize=9, color="#7f1d1d",
                transform=ax.transAxes,
                bbox=dict(boxstyle="round,pad=0.5", facecolor="#fef2f2",
                          edgecolor="#fca5a5"),
            )
            ax.set_yticks([])
        else:
            ax.hlines(range(len(d)), 0, d[col], color="#94a3b8", linewidth=1.2)
            ax.plot(d[col], range(len(d)), "o", color="#1d4ed8", markersize=7)
            ax.set_yticks(range(len(d)))
            ax.set_yticklabels(
                [
                    f"{n}  (n={int(v)})"
                    for n, v in zip(d["location_name"], d[f"den_{col.split('_', 1)[1]}"])
                ],
                fontsize=8,
            )
        ax.set_xlim(0, 1)
        ax.set_xlabel("proportion", fontsize=9)
        ax.set_title(LABELS.get(col, col), fontsize=9)
        ax.grid(axis="x", alpha=0.25)

    fig_dom.suptitle(
        "Unit-level performance by domain", fontsize=12, fontweight="bold"
    )
    fig_dom.tight_layout()
    fig_dom
    return LABELS, axes, fig_dom, matplotlib, plt


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Validation against published dashboard values

        From the dashboard's `docs/portability_mimic.md`. Our numbers differ legitimately
        because we restrict to the notebook-01 cohort and open the scoring window at time
        zero, but they should not differ by an order of magnitude. A large gap means a
        definition was mistranscribed.
        """
    )
    return


@app.cell
def _(mo, np, pd, unit_scores):
    # comparable=False means our denominator is not yet the same quantity as the
    # dashboard's, so the gap is uninformative about correctness. SBT eligibility is
    # currently approximated (no NEE criterion) and therefore too permissive -- see
    # plan 02 section 6 "Deviation for this project".
    VALIDATION = [
        ("LTVV (Vt ≤ 8 mL/kg PBW, of assessable vent-ICU days)", "p_ltvv", 0.675, 0.831, True),
        ("SAT (of eligible vent-sedation days)", "p_sat", 0.589, 0.418, True),
        ("SBT (of eligible transition-candidate days)", "p_sbt", 0.447, 0.253, False),
        ("Proning (ever proned, of PROSEVA-eligible)", "p_prone", 0.170, 0.189, True),
    ]

    def _pooled(num_col, den_col):
        if num_col not in unit_scores.columns:
            return np.nan
        num = unit_scores[num_col].sum()
        den = unit_scores[den_col].sum()
        return num / den if den else np.nan

    validation = pd.DataFrame(
        [
            {
                "domain": label,
                "this run (pooled)": _pooled(f"num_{col.split('_', 1)[1]}",
                                             f"den_{col.split('_', 1)[1]}"),
                "dashboard MIMIC": mimic,
                "dashboard UChicago": uc,
                "comparable": "yes" if ok else "NO — definition incomplete",
            }
            for label, col, mimic, uc, ok in VALIDATION
        ]
    )
    mo.vstack([
        mo.ui.table(validation.round(3), selection=None),
        mo.md(
            """
            /// warning | SBT is not yet comparable to the dashboard

            SBT eligibility is approximated — the norepinephrine-equivalent criterion is not
            implemented, so the denominator is too permissive and the rate is biased
            downward. The gap against the dashboard reflects that, not a transcription
            error. See plan 02 section 6, "Deviation for this project".
            ///
            """
        ),
    ])
    return VALIDATION, validation


@app.cell
def _(mo):
    mo.md(r"""## Write outputs""")
    return


@app.cell
def _(
    DISPLAY_COLS,
    FINAL_DIR,
    INTERMEDIATE_DIR,
    domain_corr,
    fig_dom,
    ltvv_days,
    mo,
    pd,
    prone_df,
    sat_days,
    sbt_days,
    unit_scores,
    validation,
    weights_set,
):
    INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    unit_scores[[c for c in DISPLAY_COLS if c in unit_scores.columns]].to_csv(
        FINAL_DIR / "unit_quality_scores.csv", index=False
    )
    domain_corr.round(4).to_csv(FINAL_DIR / "domain_correlation.csv")
    validation.round(4).to_csv(FINAL_DIR / "validation_vs_dashboard.csv", index=False)
    fig_dom.savefig(FINAL_DIR / "domain_performance.png", dpi=150, bbox_inches="tight")

    assessability = unit_scores[
        [c for c in ("unit_key", "not_assessable_ltvv", "crude_ltvv", "p_ltvv")
         if c in unit_scores.columns]
    ]
    assessability.round(4).to_csv(FINAL_DIR / "assessability_by_unit.csv", index=False)

    # Per-patient and per-patient-day flags: PHI, and the file to inspect when a unit's
    # score looks wrong. Also what makes leave-one-patient-out in notebook 03 possible.
    flags = {
        "ltvv_patient_days": ltvv_days,
        "sat_patient_days": sat_days,
        "sbt_patient_days": sbt_days,
        "prone_encounters": prone_df,
    }
    for name, df in flags.items():
        if not df.empty:
            df.to_parquet(INTERMEDIATE_DIR / f"{name}.parquet", index=False)

    mo.md(
        f"""
        Wrote to `output/final_no_phi/`: `unit_quality_scores.csv`,
        `domain_correlation.csv`, `validation_vs_dashboard.csv`,
        `assessability_by_unit.csv`, `domain_performance.png`.

        Wrote to `output/intermediate_phi/` **(PHI)**:
        {", ".join(f"`{k}.parquet`" for k, v in flags.items() if not v.empty)}.

        **{len(unit_scores)} units scored.**
        {"Composite $Q$ computed." if weights_set else "Composite $Q$ pending weights."}
        """
    )
    return assessability, flags


if __name__ == "__main__":
    app.run()
