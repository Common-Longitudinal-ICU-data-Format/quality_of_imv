# To-do — CLIF IMV Quality Report

## Blocking: research team review

The workflow is **plans reviewed and edited → code updated to match**. The plans are drafted
and every contested choice is marked with an **Open decision** blockquote. Nothing below
should be coded until these are resolved.

### Highest priority — these change the analysis, not just the code

- [ ] **Quality score weights** (plan 02 §8.1). All `null`. Recommend equal 0.25.
      Must be fixed *before* looking at outcomes, or the inference is circular.
- [ ] **Proning denominator** (plan 02 §7.2). May be too small to score per unit. If
      `p_prone` is usually missing then `w_4` is decorative and `Q` is really a
      three-domain score. Decide before setting weights.
- [ ] **Between/within-hospital decomposition of Q** (plan 03 §6.1). If the between share
      is large, adopt the within-between specification so the two associations are reported
      separately rather than averaged.
- [ ] **How to handle hospital-level covariates** (plan 03 §6.1), given they cannot enter
      Model 3 alongside the hospital random effect.
- [ ] **Carry-forward parameters** (plan 01 §3). These partly define the cohort at a 4-hour
      threshold. Report cohort size under at least one alternative pair.
- [ ] **`interior_cap_hours` for SAT** (plan 02 §11). Run the segment-duration diagnostic
      per site first.
- [ ] **Presentation-window anchor** (plan 03 §3) and the resulting **lab missingness**
      strategy (plan 03 §10).
- [ ] **Software for the models** (plan 03 §11). Recommend Bayesian (`numpyro`/`PyMC`) as
      primary so PCV/VPC/MOR intervals come from the posterior.

### Also needs sign-off

- [ ] Tracheostomy and ECMO exclusions at time zero (plan 01 §5) — currently placeholders.
- [ ] Unit attribution for transfers (plan 01 §6, plan 02 §2.1) — outcomes and processes
      deliberately use different rules; confirm that is intended.
- [ ] Encounter stitching yes/no (plan 01 §2) — the dashboard stitches for SAT/SBT/proning
      but not LPV; we currently do not stitch at all.
- [ ] LTVV threshold 8 vs 6 (plan 02 §4.6) and aggregation grain (plan 02 §4.4).
- [ ] SAT paralytic list and prone/ECMO day exclusions (plan 02 §5.1) — currently a
      deliberate deviation from the dashboard.
- [ ] SBT `support_min_minutes` 2 vs 30 (plan 02 §6.2).
- [ ] Minimum cell size for `output/final_no_phi/` (plan 01 §10).

## Code work, once decisions land

- [ ] **Complete the SBT domain** — the largest code gap. Three components are
      approximated, all making eligibility too permissive, so `p_SBT` is biased downward and
      is **not comparable to the dashboard validation targets** until fixed. Table of the
      three gaps and their direction is in plan 02 §6, "Deviation for this project".
      - [ ] 12-hour controlled accrual from **waterfall scaffold hours**, not native rows.
      - [ ] 2-hour **contiguous** stability window with the 90-minute gap rule.
      - [ ] **Norepinephrine-equivalent criterion** — not implemented at all. Needs
            `standardize_dose_to_base_units` plus ASOF-merged weights from `vitals`, with a
            missing weight making the hour un-assessable rather than silently zero.
- [ ] Replace mean imputation with multiple imputation, 10 imputations (plan 03 §10).
- [ ] Competing-risks VFD model (plan 03 §8.5).
- [ ] Parametric bootstrap for PCV/VPC/MOR intervals (plan 03 §4.1), or switch to Bayesian.
- [ ] Leave-one-patient-out and temporal-split Q sensitivities (plan 03 §8.1).
- [ ] Cohort sensitivities: IMV > 24 h, IMV > 0 h, landmark at 24 h (plan 03 §8.2).
- [ ] Exposure-scale checks: quartiles and spline (plan 03 §2.1).
- [ ] Reliability/shrinkage adjustment of domain proportions (plan 02 §8.4).
- [ ] Table 1: merge in the presentation-window severity block and add missingness columns.

## First real-data contact

- [ ] `cp config/config_template.json config/config.json` and fill in.
- [ ] `cp config/unit_metadata_template.csv config/unit_metadata.csv` — needs `hospital_id`
      per `location_name`, which CLIF does not supply.
- [ ] Confirm `clif_version` (2.1 vs 3.0). Wrong casing yields silently empty filters.
- [ ] Verify the `clifpy` branches in all three notebooks — written against the 2.1.0 API
      but never run against a real database.
- [ ] Check PBW coverage immediately (notebook 02 asserts on it): exact-case
      `sex_category` is a known portability trap.
- [ ] Compare our domain rates to the dashboard targets in
      `output/final_no_phi/validation_vs_dashboard.csv`.

## Upstream — report to the dashboard author

Findings in plan 02 §12. Item 7 (uncapped interior infusion segments) is the one we believe
is a real correctness bug rather than tidiness; worth raising first.
