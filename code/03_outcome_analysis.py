# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "marimo",
#     "pandas",
#     "numpy",
#     "matplotlib",
#     "scipy",
#     "statsmodels",
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
        # 3 — Outcome Analysis

        **Plan:** [`analysis_plan/03_outcome_analysis.md`](../analysis_plan/03_outcome_analysis.md)

        Does ICU-level IMV quality explain between-unit variation in ventilated-patient
        outcomes?

        Three models, all with **nested unit and hospital random intercepts**:

        | Model | Specification |
        | --- | --- |
        | 1 | case-mix only — $\beta_0 + w_h + u_i + \beta^{\top} X_{hij}$ |
        | 2 | add unit quality — $+\ \beta_1 Q_i$ |
        | 3 | add unit/hospital covariates — $+\ \beta_2^{\top} C_i$ |

        Risk adjustment uses the **4-hour presentation window ending at time zero**, so
        covariates are pre-exposure.
        """
    )
    return


@app.cell
def _():
    import sys
    import warnings
    from pathlib import Path

    import marimo as mo
    import numpy as np
    import pandas as pd

    ROOT = Path(__file__).resolve().parent.parent
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    from utils.project_config import (
        FINAL_DIR,
        INTERMEDIATE_DIR,
        load_clif_config,
        load_params,
    )
    from utils.severity import presentation_windows, sofa_components

    warnings.filterwarnings("ignore", category=FutureWarning)
    return (
        FINAL_DIR,
        INTERMEDIATE_DIR,
        ROOT,
        load_clif_config,
        load_params,
        mo,
        np,
        pd,
        presentation_windows,
        sofa_components,
        warnings,
    )


@app.cell
def _(FINAL_DIR, INTERMEDIATE_DIR, load_clif_config, load_params, mo, pd):
    params = load_params()
    clif_config = load_clif_config()
    USING_REAL_DATA = clif_config is not None
    PW = params["presentation_window"]
    OA = params["outcome_analysis"]

    cohort_path = INTERMEDIATE_DIR / "cohort.parquet"
    scores_path = FINAL_DIR / "unit_quality_scores.csv"
    for pth, nb in ((cohort_path, "01_cohort_identification"),
                    (scores_path, "02_calculate_quality_score")):
        if not pth.exists():
            raise FileNotFoundError(f"{pth} not found. Run code/{nb}.py first.")

    cohort = pd.read_parquet(cohort_path)
    unit_scores = pd.read_csv(scores_path)

    mo.md(
        f"""
        **{len(cohort):,}** patients · **{cohort["location_name"].nunique()}** units ·
        **{cohort["hospital_id"].nunique()}** hospitals
        ({"site data" if USING_REAL_DATA else "**synthetic demo data**"}).
        """
    )
    return (
        OA,
        PW,
        USING_REAL_DATA,
        clif_config,
        cohort,
        cohort_path,
        params,
        scores_path,
        unit_scores,
    )


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Exposure — the unit quality score

        If `quality_score.weights` is still `null`, the notebook falls back to **equal
        weights purely so the pipeline is demonstrable end to end**. Those results are
        illustrative and must not be reported.
        """
    )
    return


@app.cell
def _(mo, np, params, unit_scores):
    weights = params["quality_score"]["weights"]
    DOMAINS = {"p_ltvv": "w_ltvv", "p_sat": "w_sat", "p_sbt": "w_sbt", "p_prone": "w_prone"}
    weights_set = all(weights.get(w) is not None for w in DOMAINS.values())

    use_w = (
        {d: weights[w] for d, w in DOMAINS.items()}
        if weights_set
        else {d: 0.25 for d in DOMAINS}
    )

    scores = unit_scores.copy()
    num = sum(
        scores[d].fillna(0.0) * w * scores[d].notna().astype(float)
        for d, w in use_w.items()
    )
    den = sum(w * scores[d].notna().astype(float) for d, w in use_w.items())
    scores["n_estimable_domains"] = scores[list(DOMAINS)].notna().sum(axis=1)
    scores["Q"] = np.where(
        scores["n_estimable_domains"] >= params["quality_score"]["min_estimable_domains"],
        num / den.replace(0, np.nan),
        np.nan,
    )
    sd_q = scores["Q"].std(ddof=1)
    scores["Q_std"] = (scores["Q"] - scores["Q"].mean()) / sd_q

    exposure_banner = mo.md(
        r"""
        /// danger | Weights are unspecified — results below are ILLUSTRATIVE ONLY

        `quality_score.weights` in `config/project_params.json` is all `null`. This run uses
        **equal weights (0.25 each)** so the pipeline can be demonstrated, but the research
        team has not chosen weights. See
        [plan 02 section 8.1](../analysis_plan/02_quality_score.md).

        Fix the weights **before** interpreting any estimate here — choosing them after
        seeing outcomes invalidates the inference.
        ///
        """
        if not weights_set
        else "Using the weights set in `config/project_params.json`."
    )
    exposure_banner
    return DOMAINS, den, exposure_banner, num, scores, sd_q, use_w, weights, weights_set


@app.cell
def _(mo, scores):
    mo.ui.table(
        scores[["unit_key", "location_name", "n_patients", "p_ltvv", "p_sat", "p_sbt",
                "p_prone", "Q", "Q_std"]].round(3),
        selection=None,
    )
    return


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Risk adjustment — the presentation window

        $$W_{hij} = [\, t^{0}_{hij} - 4\text{h},\ t^{0}_{hij} \,]$$

        On real data this hands the window straight to clifpy's `calculate_sofa2`, which
        accepts an arbitrary `cohort_df` of `[hospitalization_id, start_dttm, end_dttm]`.
        The synthetic branch uses the simplified fallback in `utils/severity.py`.
        """
    )
    return


@app.cell
def _(
    PW,
    USING_REAL_DATA,
    cohort,
    mo,
    presentation_windows,
    sofa_components,
):
    win = presentation_windows(cohort, PW["hours_before_t0"])

    if USING_REAL_DATA:
        # PLACEHOLDER FOR REAL-DATABASE DEVELOPMENT.
        # calculate_sofa2 takes exactly this cohort_df shape and requires non-overlapping
        # windows, which [t0-4h, t0] satisfies by construction (one window per patient).
        # Untested against a real CLIF database; verify column names on first contact.
        from clifpy import calculate_sofa2

        sofa = calculate_sofa2(
            win, clif_config_path="config/config.json", id_name="hospitalization_id"
        )
        sofa_col = "sofa2_total"
    else:
        from utils.synthetic_clif import make_demo_tables

        demo = make_demo_tables()
        sofa = sofa_components(
            cohort,
            demo["labs"],
            demo["vitals"],
            demo["respiratory_support"],
            demo["patient_assessments"],
            demo["medication_admin_continuous"],
            hours_before=PW["hours_before_t0"],
            carry_forward_hours=PW["lab_carry_forward_max_hours"],
        )
        sofa_col = "sofa_total"

    SOFA_COMPONENTS = [
        c for c in ("sofa_resp", "sofa_coag", "sofa_liver", "sofa_renal", "sofa_cns",
                    "sofa_cv")
        if c in sofa.columns
    ]

    missingness = (
        sofa[SOFA_COMPONENTS].isna().mean().rename("proportion missing").reset_index()
        .rename(columns={"index": "component"})
    )
    mo.vstack([
        mo.md(
            f"""
            Severity computed for **{len(sofa):,}** patients from a
            **{PW["hours_before_t0"]}-hour** window, with lab carry-forward up to
            **{PW["lab_carry_forward_max_hours"]} h** before the window.

            **Component missingness is the price of narrowing the window from 24 h to 4 h**
            — plan 03 section 10 flags this as the most consequential downstream effect of
            that change.
            """
        ),
        mo.ui.table(missingness.round(3), selection=None),
    ])
    return SOFA_COMPONENTS, demo, missingness, sofa, sofa_col, win


@app.cell
def _(mo):
    mo.md(r"""## Build the analytic frame""")
    return


@app.cell
def _(SOFA_COMPONENTS, cohort, mo, np, scores, sofa):
    frame = (
        cohort.merge(sofa, on="hospitalization_id", how="left")
        .merge(
            scores[["location_name", "Q", "Q_std", "n_estimable_domains"]],
            on="location_name",
            how="left",
        )
    )

    # Mean-impute SOFA components so Model 1 is estimable on the demo. Plan 03 section 10
    # specifies multiple imputation (10 imputations, outcome and unit in the imputation
    # model) plus a complete-case sensitivity analysis -- NOT mean imputation, which
    # understates uncertainty. This is a scaffold, not the analysis.
    for c in SOFA_COMPONENTS:
        frame[c] = frame[c].fillna(frame[c].mean())

    frame["Q_quartile"] = (
        frame.groupby("location_name")["Q"].transform("first").rank(pct=True)
        .pipe(lambda s: np.ceil(s * 4).clip(1, 4))
    )
    frame["survived"] = frame["survived_to_discharge"].astype(int)

    modelable = frame.dropna(subset=["Q_std"] + SOFA_COMPONENTS).copy()
    mo.md(
        f"""
        Analytic frame: **{len(frame):,}** patients, of whom **{len(modelable):,}** have an
        estimable unit quality score and complete adjustment covariates.

        Patients in units without an estimable score stay in Model 1's variance estimate but
        drop out of Models 2 and 3 — that differential inclusion belongs in the STROBE
        diagram (plan 01 section 7).
        """
    )
    return frame, modelable


@app.cell
def _(mo, modelable, np, pd):
    by_unit = (
        modelable.groupby(["hospital_id", "location_name"])
        .agg(
            n=("survived", "size"),
            survival=("survived", "mean"),
            vfd_mean=("vfd_28", "mean"),
            Q=("Q", "first"),
        )
        .reset_index()
        .sort_values("Q", ascending=False)
    )
    mo.vstack([
        mo.md("### Crude outcomes by unit, ranked by quality score"),
        mo.ui.table(by_unit.round(3), selection=None),
    ])
    return (by_unit,)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## How much of $Q$ varies *within* hospitals?

        Read this before interpreting $\beta_1$. A hospital random intercept is in every
        model (WFP note 4), and it absorbs all **between**-hospital variation in $Q_i$ —
        so $\beta_1$ is identified only from **within**-hospital contrasts between units.

        If most of $Q$'s variance sits between hospitals, the hospital random effect
        removes most of the exposure's usable variance, and a small $\beta_1$ or
        $\mathrm{PCV}$ would mean "not much quality variation survives the hospital
        adjustment" rather than "quality does not matter."
        """
    )
    return


@app.cell
def _(mo, modelable, np, pd):
    q_units = (
        modelable.groupby(["hospital_id", "location_name"])["Q"].first().reset_index()
    )
    q_grand = q_units["Q"].mean()
    q_hosp_mean = q_units.groupby("hospital_id")["Q"].transform("mean")
    ss_between = float(((q_hosp_mean - q_grand) ** 2).sum())
    ss_total = float(((q_units["Q"] - q_grand) ** 2).sum())
    share_between = ss_between / ss_total if ss_total > 0 else np.nan

    q_decomp = pd.DataFrame(
        [
            {"component": "between hospitals", "share of Q variance": share_between},
            {"component": "within hospitals", "share of Q variance": 1 - share_between},
        ]
    )

    decomp_note = mo.md(
        f"""
        /// warning | {share_between:.0%} of the quality score's variance is between hospitals

        The hospital random intercept absorbs that share, so $\beta_1$ is estimated from
        the remaining **{1 - share_between:.0%}** of within-hospital variation across
        {len(q_units)} units in {q_units["hospital_id"].nunique()} hospitals. Report the
        effective number of within-hospital unit contrasts alongside $\beta_1$, and
        consider the between/within decomposition of $Q$ described in plan 03 section 6.1.
        ///
        """
        if np.isfinite(share_between) and share_between > 0.3
        else f"**{share_between:.0%}** of $Q$ variance is between hospitals."
    )
    mo.vstack([mo.ui.table(q_decomp.round(3), selection=None), decomp_note])
    return (
        decomp_note,
        q_decomp,
        q_grand,
        q_hosp_mean,
        q_units,
        share_between,
        ss_between,
        ss_total,
    )


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Models

        /// warning | Software placeholder

        These fits use `statsmodels`, which is limited for three-level and nested
        random-effects models. `BinomialBayesMixedGLM` is a **variational Bayes
        approximation** — usable for a scaffold, but its variance components should not be
        reported as final.

        Plan 03 section 11 recommends a **fully Bayesian fit (`numpyro`/`PyMC`) as
        primary**, because PCV, VPC, and MOR are all nonlinear functions of variance
        components and a posterior gives their intervals directly instead of via parametric
        bootstrap. That decision is still open.
        ///
        """
    )
    return


@app.cell
def _(SOFA_COMPONENTS, modelable, np, pd):
    import statsmodels.api as sm
    from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM
    from statsmodels.regression.mixed_linear_model import MixedLM

    X_TERMS = " + ".join(SOFA_COMPONENTS)
    # Nested random intercepts: unit within hospital, in every model (WFP note 4).
    VC = {"unit": "0 + C(location_name)", "hosp": "0 + C(hospital_id)"}

    # --- Model 3 covariate screen -------------------------------------------------
    # A covariate that is CONSTANT WITHIN HOSPITAL is perfectly collinear with the
    # hospital random intercept and cannot be estimated alongside it. Left in, the fit
    # does not error -- it returns coefficients pinned at exactly 0.0 (variational Bayes)
    # or wild unidentified values (REML). Both look like results. Screen them out and say
    # so. See plan 03 section 6.1.
    C_CANDIDATES = ["unit_volume_log", "hospital_beds_z", "academic"]

    mdl = modelable.copy()
    vol = mdl.groupby("location_name")["survived"].transform("size")
    mdl["unit_volume_log"] = np.log(vol)
    if "hospital_beds" in mdl.columns:
        hb = pd.to_numeric(mdl["hospital_beds"], errors="coerce")
        mdl["hospital_beds_z"] = (hb - hb.mean()) / (hb.std(ddof=0) or 1.0)

    C_KEPT, C_DROPPED = [], []
    for cand in C_CANDIDATES:
        if cand not in mdl.columns or mdl[cand].nunique(dropna=True) < 2:
            C_DROPPED.append((cand, "absent or constant overall"))
            continue
        within = mdl.groupby("hospital_id")[cand].nunique(dropna=True)
        if (within <= 1).all():
            C_DROPPED.append((cand, "constant within hospital; collinear with the hospital random effect"))
        else:
            C_KEPT.append(cand)

    C_TERMS = " + ".join(C_KEPT)
    SPECS = {
        "Model 1 (case-mix only)": X_TERMS,
        "Model 2 (+ Q)": f"Q_std + {X_TERMS}",
        "Model 3 (+ unit/hospital covariates)": (
            f"Q_std + {C_TERMS} + {X_TERMS}" if C_KEPT else f"Q_std + {X_TERMS}"
        ),
    }

    def fit_survival(rhs):
        m = BinomialBayesMixedGLM.from_formula(
            f"survived ~ {rhs}", VC, mdl, vcp_p=2.0
        )
        return m.fit_vb(verbose=False)

    def fit_vfd(rhs):
        # MixedLM: hospital as the grouping factor, unit as a nested variance component.
        return MixedLM.from_formula(
            f"vfd_28 ~ {rhs}",
            groups="hospital_id",
            re_formula="1",
            vc_formula={"unit": "0 + C(location_name)"},
            data=mdl,
        ).fit(reml=True)

    surv_fits, vfd_fits = {}, {}
    for _spec, _rhs in SPECS.items():
        try:
            surv_fits[_spec] = fit_survival(_rhs)
        except Exception as exc:  # a failed fit must be visible, not silently skipped
            surv_fits[_spec] = f"FAILED: {type(exc).__name__}: {exc}"
        try:
            vfd_fits[_spec] = fit_vfd(_rhs)
        except Exception as exc:
            vfd_fits[_spec] = f"FAILED: {type(exc).__name__}: {exc}"
    return (
        BinomialBayesMixedGLM,
        C_CANDIDATES,
        C_DROPPED,
        C_KEPT,
        C_TERMS,
        MixedLM,
        SPECS,
        VC,
        X_TERMS,
        fit_survival,
        fit_vfd,
        hb,
        mdl,
        sm,
        surv_fits,
        vfd_fits,
        vol,
    )


@app.cell
def _(C_DROPPED, C_KEPT, mo, pd):
    screen = pd.DataFrame(
        [{"covariate": c, "status": "kept"} for c in C_KEPT]
        + [{"covariate": c, "status": f"DROPPED — {why}"} for c, why in C_DROPPED]
    )
    screen_note = (
        mo.md(
            """
            /// danger | Some Model 3 covariates were dropped as unidentifiable

            A covariate constant within hospital is perfectly collinear with the hospital
            random intercept. Left in, the fit does **not** error — variational Bayes pins
            the coefficient at exactly `0.0` and REML returns wild values. Both look like
            results, so they are screened out here instead. See plan 03 section 6.1.
            ///
            """
        )
        if C_DROPPED
        else mo.md("All candidate Model 3 covariates are identifiable.")
    )
    mo.vstack([mo.ui.table(screen, selection=None), screen_note])
    return screen, screen_note


@app.cell
def _(mo, np, pd, surv_fits, vfd_fits):
    est_rows = []
    for spec, sfit in surv_fits.items():
        if isinstance(sfit, str):
            est_rows.append({"outcome": "survival", "model": spec, "term": "—",
                             "estimate": np.nan, "sd": np.nan, "note": sfit})
            continue
        exog = list(sfit.model.exog_names)
        for j, term in enumerate(exog):
            if term == "Intercept" or term.startswith("sofa_"):
                continue
            est_rows.append({
                "outcome": "survival (log-odds)",
                "model": spec,
                "term": term,
                "estimate": float(sfit.fe_mean[j]),
                "sd": float(sfit.fe_sd[j]),
                "note": "",
            })

    for spec, vfit in vfd_fits.items():
        if isinstance(vfit, str):
            est_rows.append({"outcome": "VFD", "model": spec, "term": "—",
                             "estimate": np.nan, "sd": np.nan, "note": vfit})
            continue
        for term in vfit.params.index:
            if term in ("Intercept", "unit Var", "hospital_id Var", "Group Var") \
               or term.startswith("sofa_"):
                continue
            est_rows.append({
                "outcome": "VFD (days)",
                "model": spec,
                "term": term,
                "estimate": float(vfit.params[term]),
                "sd": float(vfit.bse[term]) if term in vfit.bse.index else np.nan,
                "note": "",
            })

    estimates = pd.DataFrame(est_rows)
    mo.vstack([
        mo.md(
            r"""
            ### Fixed effects

            $\beta_1$ (survival) and $\gamma_1$ (VFD) are the `Q_std` rows — the
            association per 1-SD increase in unit quality. **H1** predicts both positive.
            """
        ),
        mo.ui.table(estimates.round(4), selection=None, page_size=20),
    ])
    return est_rows, estimates


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Variance summaries

        Proportional change in between-unit variance, how much of it $Q_i$ accounts for:

        $$\mathrm{PCV}_Y = \frac{\hat{\sigma}^2_u - \hat{\sigma}^2_{u^*}}{\hat{\sigma}^2_u}$$

        Median odds ratio between two randomly chosen units at the same covariate values:

        $$\mathrm{MOR} = \exp\!\left(\sqrt{2\sigma^2}\ \Phi^{-1}(0.75)\right)$$

        Variance partition across hospital, unit, and patient on the latent scale:

        $$\mathrm{VPC}_{\text{unit}} = \frac{\sigma^2_u}{\sigma^2_w + \sigma^2_u + \pi^2/3}$$
        """
    )
    return


@app.cell
def _(mo, np, pd, surv_fits, vfd_fits):
    from scipy.stats import norm

    def mor(var):
        if var is None or not np.isfinite(var) or var <= 0:
            return np.nan
        return float(np.exp(np.sqrt(2.0 * var) * norm.ppf(0.75)))

    def surv_vars(fit):
        """Variance components from BinomialBayesMixedGLM.

        vcp_mean holds the LOG standard deviation of each variance component, so the
        variance is exp(2 * vcp_mean). Reading it as a variance directly is an easy and
        silent error.
        """
        if isinstance(fit, str):
            return {}
        out = {}
        for nm, val in zip(fit.model.vcp_names, fit.vcp_mean):
            out[nm] = float(np.exp(2.0 * val))
        return out

    def vfd_vars(fit):
        if isinstance(fit, str):
            return {}
        out = {}
        for k, v in fit.vcomp_names_map().items() if hasattr(fit, "vcomp_names_map") else []:
            out[k] = v
        # cov_re is the hospital-level covariance; vcomp holds the nested unit component.
        try:
            out["hosp"] = float(np.asarray(fit.cov_re)[0, 0])
        except Exception:
            pass
        try:
            names = list(getattr(fit.model, "exog_vc", None).names) \
                if getattr(fit.model, "exog_vc", None) is not None else ["unit"]
            for nm, v in zip(names, np.atleast_1d(fit.vcomp)):
                out[nm] = float(v)
        except Exception:
            pass
        return out

    M1, M2, M3 = (
        "Model 1 (case-mix only)",
        "Model 2 (+ Q)",
        "Model 3 (+ unit/hospital covariates)",
    )

    sv = {k: surv_vars(v) for k, v in surv_fits.items()}
    vv = {k: vfd_vars(v) for k, v in vfd_fits.items()}

    def pcv(d1, d2, key):
        a, b = d1.get(key), d2.get(key)
        if a is None or b is None or not np.isfinite(a) or a <= 0:
            return np.nan
        return float((a - b) / a)

    LATENT = np.pi**2 / 3.0

    def vpc(d, key):
        u, w = d.get("unit"), d.get("hosp")
        if u is None or w is None:
            return np.nan
        tot = u + w + LATENT
        return float(d[key] / tot) if tot > 0 else np.nan

    variance_rows = [
        {"quantity": "sigma^2_unit (survival), Model 1", "value": sv.get(M1, {}).get("unit", np.nan)},
        {"quantity": "sigma^2_unit (survival), Model 2", "value": sv.get(M2, {}).get("unit", np.nan)},
        {"quantity": "sigma^2_hosp (survival), Model 1", "value": sv.get(M1, {}).get("hosp", np.nan)},
        {"quantity": "sigma^2_hosp (survival), Model 2", "value": sv.get(M2, {}).get("hosp", np.nan)},
        {"quantity": "PCV_Y (unit variance explained by Q)", "value": pcv(sv.get(M1, {}), sv.get(M2, {}), "unit")},
        {"quantity": "MOR unit (survival), Model 1", "value": mor(sv.get(M1, {}).get("unit"))},
        {"quantity": "MOR hosp (survival), Model 1", "value": mor(sv.get(M1, {}).get("hosp"))},
        {"quantity": "VPC unit (survival), Model 1", "value": vpc(sv.get(M1, {}), "unit")},
        {"quantity": "VPC hosp (survival), Model 1", "value": vpc(sv.get(M1, {}), "hosp")},
        {"quantity": "sigma^2_unit (VFD), Model 1", "value": vv.get(M1, {}).get("unit", np.nan)},
        {"quantity": "sigma^2_unit (VFD), Model 2", "value": vv.get(M2, {}).get("unit", np.nan)},
        {"quantity": "PCV_V (unit variance explained by Q)", "value": pcv(vv.get(M1, {}), vv.get(M2, {}), "unit")},
    ]
    variances = pd.DataFrame(variance_rows)

    neg_pcv = [
        r["quantity"] for r in variance_rows
        if r["quantity"].startswith("PCV") and np.isfinite(r["value"]) and r["value"] < 0
    ]
    pcv_note = mo.md(
        f"""
        /// danger | Negative PCV: {", ".join(neg_pcv)}

        A negative proportional change means the between-unit variance *increased* when
        $Q$ was added, which is not substantively interpretable. It is a **fit-instability
        diagnostic**, not a finding: with few units, a near-zero unit variance, or a
        non-converged fit, PCV is essentially noise. Do not report it until the model
        converges cleanly and the interval is available.
        ///
        """
    ) if neg_pcv else mo.md("")

    mo.vstack([
        mo.ui.table(variances.round(4), selection=None, page_size=15),
        pcv_note,
        mo.md(
            """
            /// warning | No confidence intervals here

            PCV, VPC, and MOR are nonlinear functions of variance components, so their
            intervals need the parametric bootstrap of plan 03 section 4.1 (or a posterior).
            Point estimates alone are not reportable — and with few units they are very
            unstable.
            ///
            """
        ),
    ])
    return (LATENT, M1, M2, M3, mor, neg_pcv, norm, pcv, pcv_note, sv, surv_vars,
            variance_rows, variances, vfd_vars, vpc, vv)


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Figure 1 — caterpillar plot

        Units ranked by **population-standardized** predicted survival, coloured by quality
        score. Standardization predicts the outcome for *every patient in the cohort* as if
        they had been cared for in each unit, then averages over the empirical covariate
        distribution (WFP note 5):

        $$\hat{p}^{\text{std}}_i = \frac{1}{N} \sum_{n=1}^{N} \operatorname{expit}\!\left(\hat{\beta}_0 + \hat{w}_{h(i)} + \hat{u}_i + \hat{\beta}^{\top} X_n\right)$$

        This differs from evaluating at a mean covariate vector, which under a logit link
        does not return the marginal risk.
        """
    )
    return


@app.cell
def _(M1, SOFA_COMPONENTS, mdl, np, pd, surv_fits):
    def standardized_predictions(fit, data, sofa_cols):
        """Population-standardized predicted survival per unit (plan 03 formula 3).

        For each unit, predict the outcome for EVERY patient in the cohort as if they had
        been cared for in that unit, then average over the empirical covariate
        distribution. The counterfactual population is held fixed and only the unit
        assignment varies.

        Both random effects must be added: the unit effect and the effect of the hospital
        that unit sits in. Omitting the hospital term flattens the whole plot, because the
        hospital intercepts are the larger of the two (in our synthetic run, hospital
        effects were +/-0.24 on the logit scale against +/-0.06 for units).
        """
        if isinstance(fit, str):
            return pd.DataFrame(columns=["location_name", "p_std"])

        beta = np.asarray(fit.fe_mean)
        X = np.asarray(fit.model.exog, dtype=float)

        # Fixed-effect linear predictor for every patient. This fit is Model 1, which has
        # no Q term, so there is nothing unit-specific hiding in the fixed part.
        eta_fixed = X @ beta

        # Random effects come from vc_names formatted as "C(location_name)[MICU_A1]".
        re_map = {}
        for nm, val in zip(list(fit.model.vc_names), np.asarray(fit.vc_mean)):
            if "(" not in nm or "[" not in nm:
                continue
            var = nm.split("(", 1)[1].split(")", 1)[0]
            level = nm.split("[", 1)[1].rstrip("]").replace("T.", "")
            re_map[(var, level)] = float(val)

        unit_to_hosp = data.groupby("location_name")["hospital_id"].first().to_dict()

        rows = []
        for unit in sorted(data["location_name"].unique()):
            re_unit = re_map.get(("location_name", unit), 0.0)
            re_hosp = re_map.get(("hospital_id", unit_to_hosp.get(unit)), 0.0)
            prob = 1.0 / (1.0 + np.exp(-(eta_fixed + re_unit + re_hosp)))
            rows.append(
                {
                    "location_name": unit,
                    "p_std": float(np.mean(prob)),
                    "re_unit": re_unit,
                    "re_hospital": re_hosp,
                }
            )
        return pd.DataFrame(rows)

    p_std = standardized_predictions(surv_fits.get(M1), mdl, SOFA_COMPONENTS)
    return p_std, standardized_predictions


@app.cell
def _(modelable, np, p_std, pd, scores):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    obs = (
        modelable.groupby("location_name")
        .agg(n=("survived", "size"), crude=("survived", "mean"),
             vfd=("vfd_28", "mean"), Q=("Q", "first"))
        .reset_index()
    )
    cat = obs.merge(p_std, on="location_name", how="left")
    cat["plot_p"] = cat["p_std"].fillna(cat["crude"])
    # Standardized predictions are shrunken toward the mean relative to crude rates; the
    # spread of each is worth seeing side by side.
    cat["crude_minus_std"] = cat["crude"] - cat["plot_p"]
    # Binomial interval on the crude rate; a real version needs the parametric bootstrap
    # over the joint posterior of fixed and random effects (plan 03 section 4.1).
    cat["se"] = np.sqrt(cat["crude"] * (1 - cat["crude"]) / cat["n"])
    cat = cat.sort_values("plot_p")

    fig_cat, (ax_a, ax_b) = plt.subplots(1, 2, figsize=(12, 5.2))

    qmin, qmax = cat["Q"].min(), cat["Q"].max()
    norm_q = (cat["Q"] - qmin) / (qmax - qmin) if qmax > qmin else cat["Q"] * 0 + 0.5
    colors = plt.cm.viridis(norm_q)

    y = np.arange(len(cat))
    ax_a.errorbar(cat["plot_p"], y, xerr=1.96 * cat["se"], fmt="none",
                  ecolor="#cbd5e1", elinewidth=1.6, capsize=3)
    ax_a.scatter(cat["crude"], y, facecolor="none", edgecolor="#94a3b8", s=70,
                 zorder=2, linewidth=1.1, label="crude (unshrunken)")
    ax_a.scatter(cat["plot_p"], y, c=colors, s=95, zorder=3, edgecolor="#1e293b",
                 linewidth=0.6, label="standardized")
    ax_a.axvline(modelable["survived"].mean(), color="#dc2626", linestyle="--",
                 linewidth=1.1, label="cohort mean")
    ax_a.set_yticks(y)
    ax_a.set_yticklabels(cat["location_name"], fontsize=9)
    ax_a.set_xlabel("standardized predicted survival", fontsize=10)
    ax_a.set_title("Survival to hospital discharge", fontsize=11, fontweight="bold")
    ax_a.legend(fontsize=8, loc="lower right")
    ax_a.grid(axis="x", alpha=0.25)

    cat_v = cat.sort_values("vfd")
    yv = np.arange(len(cat_v))
    norm_qv = (cat_v["Q"] - qmin) / (qmax - qmin) if qmax > qmin else cat_v["Q"] * 0 + 0.5
    ax_b.scatter(cat_v["vfd"], yv, c=plt.cm.viridis(norm_qv), s=95, zorder=3,
                 edgecolor="#1e293b", linewidth=0.6)
    ax_b.axvline(modelable["vfd_28"].mean(), color="#dc2626", linestyle="--",
                 linewidth=1.1)
    ax_b.set_yticks(yv)
    ax_b.set_yticklabels(cat_v["location_name"], fontsize=9)
    ax_b.set_xlabel("mean ventilator-free days at 28 days", fontsize=10)
    ax_b.set_title("Ventilator-free days", fontsize=11, fontweight="bold")
    ax_b.grid(axis="x", alpha=0.25)

    sm_q = plt.cm.ScalarMappable(
        cmap="viridis", norm=plt.Normalize(vmin=qmin, vmax=qmax)
    )
    cbar = fig_cat.colorbar(sm_q, ax=[ax_a, ax_b], fraction=0.025, pad=0.02)
    cbar.set_label("quality score $Q_i$", fontsize=9)

    fig_cat.suptitle(
        "Figure 1 — unit-level outcomes, coloured by IMV quality score",
        fontsize=12, fontweight="bold",
    )
    fig_cat
    return (
        ax_a,
        ax_b,
        cat,
        cat_v,
        cbar,
        colors,
        fig_cat,
        matplotlib,
        norm_q,
        norm_qv,
        obs,
        plt,
        qmax,
        qmin,
        sm_q,
        y,
        yv,
    )


@app.cell
def _(mo):
    mo.md(
        r"""
        ## Not yet implemented

        Each of these is specified in the plan and deliberately left as a stub rather than
        approximated, because a wrong version would be worse than an absent one.

        | Analysis | Plan | Why it is a stub |
        | --- | --- | --- |
        | Competing-risks VFD (liberation vs. death) | §8.5 | The linear VFD model above is **descriptive only** — VFD is bounded and zero-inflated by death. Needs a cause-specific hazard model with nested random effects; the approach is an open decision. |
        | Parametric bootstrap for PCV / VPC / MOR intervals | §4.1, §5.1 | 1000 draws over the joint posterior of fixed and empirical-Bayes random effects. Blocked on the Bayesian-versus-`lme4` software decision (§11). |
        | Multiple imputation (10 imputations) | §10 | Mean imputation is used above as a scaffold; it understates uncertainty. |
        | Leave-one-patient-out $Q$ sensitivity | §8.1 | Computable from `output/intermediate_phi/*_patient_days.parquet`. |
        | Temporal-split $Q$ sensitivity | §8.1 | Needs a split date and a stability assumption. |
        | Cohort sensitivity: IMV > 24 h, IMV > 0 h, landmark at 24 h | §8.2 | Re-runs notebook 01 with a different threshold. |
        | Exposure-scale checks: quartiles, spline | §2.1 | A linear-in-$Q$ effect is an assumption, not a finding. |
        | Restriction to patients intubated before ICU arrival | §8.3 | The only group whose covariates are fully pre-exposure. |
        """
    )
    return


@app.cell
def _(mo):
    mo.md(r"""## Write outputs""")
    return


@app.cell
def _(
    FINAL_DIR,
    INTERMEDIATE_DIR,
    SOFA_COMPONENTS,
    by_unit,
    cat,
    estimates,
    fig_cat,
    mo,
    modelable,
    scores,
    variances,
    weights_set,
):
    INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)
    FINAL_DIR.mkdir(parents=True, exist_ok=True)

    estimates.round(5).to_csv(FINAL_DIR / "model_estimates.csv", index=False)
    variances.round(5).to_csv(FINAL_DIR / "variance_summaries.csv", index=False)
    by_unit.round(4).to_csv(FINAL_DIR / "unit_outcomes.csv", index=False)
    fig_cat.savefig(FINAL_DIR / "caterpillar_survival_vfd.png", dpi=150,
                    bbox_inches="tight")

    keep = [
        "hospitalization_id", "location_name", "hospital_id", "site", "time_zero",
        "survived", "vfd_28", "Q", "Q_std", *SOFA_COMPONENTS,
    ]
    modelable[[c for c in keep if c in modelable.columns]].to_parquet(
        INTERMEDIATE_DIR / "analytic_frame.parquet", index=False
    )

    mo.md(
        f"""
        Wrote to `output/final_no_phi/`: `model_estimates.csv`,
        `variance_summaries.csv`, `unit_outcomes.csv`,
        `caterpillar_survival_vfd.png`.

        Wrote to `output/intermediate_phi/` **(PHI)**: `analytic_frame.parquet`
        ({len(modelable):,} rows).

        {
            "**Reminder: quality-score weights are unspecified, so every estimate above "
            "used illustrative equal weights and must not be reported.**"
            if not weights_set else ""
        }
        """
    )
    return keep


if __name__ == "__main__":
    app.run()
