# Quality of IMV — CLIF IMV Quality Report

Grade ICU unit-level (`location_name`) performance across four invasive mechanical
ventilation quality domains, and associate exposure to ICU quality with ICU outcomes.
Downstream goal is an MPOG-style unit feedback product.

**Domains:** lung-protective tidal volume (LTVV) · spontaneous awakening trials (SAT) ·
spontaneous breathing trials (SBT) · prone positioning

---

## The workflow — read this before changing code

```
analysis_plan/*.md  ──reviewed & edited by the research team──▶  code/*.py
```

**The markdown plans in `analysis_plan/` are the source of truth, not the code.** The team
reviews and edits the plans; the notebooks are then updated to match. Do not change an
analysis choice in code without changing the plan that justifies it, and do not resolve an
**Open decision** blockquote on your own — those are marked precisely because they need a
human.

There are currently **36 open decisions** (9 cohort / 15 quality score / 12 outcome).

## Repo layout

| Path | Contents |
| --- | --- |
| `analysis_plan/01_cohort_identification.md` | Adults, IMV > 4 h, ICU. Time zero. Table 1, STROBE. |
| `analysis_plan/02_quality_score.md` | The four domains and the composite `Q`. |
| `analysis_plan/03_outcome_analysis.md` | Three nested-random-effect models. Converted from `CLIF_IMV_quality_concept_WFP.pdf`; its change log maps WFP's five PDF margin notes to what changed. |
| `code/01_cohort_identification.py` | marimo. Writes `cohort.parquet`, `hospitalization_ids.csv`, Table 1, STROBE. |
| `code/02_calculate_quality_score.py` | marimo. Per-unit domain proportions and `Q`. |
| `code/03_outcome_analysis.py` | marimo. Models 1–3, variance summaries, caterpillar plot. |
| `utils/cohort.py` | Time-zero and IMV-interval logic. **Unit-tested** — 13 tests. |
| `utils/domains.py` | The four quality domains. |
| `utils/severity.py` | Presentation-window SOFA. |
| `utils/project_config.py` | Config loading, CLIF-version-aware category vocabularies. |
| `utils/synthetic_clif.py` | Synthetic CLIF tables so notebooks run with no site data. |
| `config/project_params.json` | **Committed.** Every analysis parameter, each with a `_plan` pointer. |
| `config/config.json` | **Gitignored.** clifpy site config. Absent → notebooks use synthetic data. |
| `config/unit_metadata.csv` | **Gitignored.** Maps `location_name` → `hospital_id`; CLIF has no hospital level. |
| `.claude/claude-progress.md` | What has been done and what running it revealed. |
| `.claude/claude-todo.md` | Decisions blocking code work, prioritized. |
| `.claude/lessons.md` | Patterns to keep. Read before adding a new domain or model. |

Notebooks run **in order** — each reads what the previous wrote.

## Commands

`pip` is **not on PATH** on this machine. `uv` manages the environment.

```bash
uv sync
```

```bash
uv run marimo edit code/01_cohort_identification.py
```

```bash
uv run pytest utils/test_cohort.py -q
```

```bash
uvx marimo check code/01_cohort_identification.py
```

Run a notebook headless (script mode) to verify it end to end:

```bash
uv run code/01_cohort_identification.py
```

Pinned: clifpy 2.1.0, marimo 0.25.0, Python ≥ 3.10.

## Core concepts

**Time zero** — the one genuinely subtle piece. The first moment the patient is
simultaneously in an ICU *and* past 4 cumulative hours of IMV:

```
t0 = min { t : in_icu(t) and cumulative_imv(t) >= 4h }
```

IMV time accrued anywhere (ED, OR, ward) counts toward the threshold; only the *location at
t0* must be an ICU. Intubated in the ED for 8 h then admitted → `t0` = ICU admission.
Intubated in the ICU → `t0` = IMV onset + 4 h. Implemented in `utils/cohort.py`, tested
against every scenario in `utils/test_cohort.py`.

**The 4-hour threshold is used consistently** for cohort entry, the exposure clock, and the
close of the risk-adjustment window, so all three are anchored together.

**Risk adjustment window** is `[t0 - 4h, t0]` — closing *at* time zero, so covariates are
provably pre-exposure. On real data use clifpy's `calculate_sofa2`, which accepts an
arbitrary `cohort_df` of `[hospitalization_id, start_dttm, end_dttm]`.

**Quality score** `Q = w1*p_LTVV + w2*p_SAT + w3*p_SBT + w4*p_prone`. **Weights are `null`
by design** — the research team has not chosen them, and they must be fixed *before* anyone
looks at outcomes or the inference is circular. Notebook 02 reports all four proportions
regardless; notebook 03 falls back to clearly-labelled equal weights so the pipeline is
demonstrable and refuses to let those results pass as reportable.

Domain definitions are transcribed from the
[CLIF ventilator QI dashboard](https://github.com/shanguleria/clif-ventilator-qi-dashboard)
source at commit `7ea68ec` — **from the code, not its docs**, which disagree. Validation
targets are in plan 02 §9 and checked automatically by notebook 02.

## Traps that fail silently

Every one of these produced output that looked like a result. None raised an exception.

1. **CLIF 2.1 uses Title Case; 3.0 uses snake_case.** `IMV` / `Assist Control-Volume
   Control` vs `imv` / `acvc`. clifpy defaults to **2.1**. Wrong casing gives an empty
   filter, not an error. Set `clif_version` explicitly; get vocabularies from
   `utils.project_config.get_vocab()`, never inline literals.
2. **`missing` is never `zero`.** A unit with no `position` data has a *missing* proning
   score. Scoring it zero systematically penalizes sites with incomplete data. Same for
   `not_assessable` patient-days and for empty figure panels — a blank panel reads as zero
   unless it says otherwise.
3. **Carry-forward partly defines the cohort.** At a 4-hour threshold, a 6-hour trailing
   carry-forward lets two hourly IMV rows accrue 7 apparent hours. A 1-hour trailing clip
   (`device_trailing_clip_hours`) is why the "IMV ≤ 4 h" exclusion fires at all.
4. **Uncapped interior infusion segments deflate the SAT rate.** A drug whose next same-drug
   row is days later becomes a phantom multi-day infusion that swallows real sedation holds.
   See `active_segments(interior_cap_hours=...)`.
5. **Covariates constant within hospital cannot enter Model 3** — perfectly collinear with
   the hospital random intercept. Variational Bayes returns coefficients of exactly `0.0`;
   REML returns wild values. Notebook 03 screens for this and reports what it dropped.
6. **The hospital random effect absorbs ~47% of `Q`'s variance**, so β1 rests only on
   within-hospital contrasts. A small β1 means "little quality variation survives the
   hospital adjustment," *not* "quality doesn't matter."
7. **Exact-case `sex_category`** (`"Male"`/`"Female"`) in the PBW formula, against
   lowercased device and mode matching everywhere else. Wrong case → all-NaN PBW → silently
   empty LTVV denominator. Notebook 02 asserts on PBW coverage.
8. **`position` is `supported: false`** in clifpy's wide-table config, so
   `create_wide_dataset` excludes it. Join it manually.
9. **LPV must use raw native rows, not the waterfall** — scaffold rows double-count
   minute-weighted intervals. SAT, SBT, and proning all use the waterfall.
10. **Timezones.** Mixed naive/aware silently yields wrong durations. `process_resp_support_waterfall`
    expects UTC and is row-order dependent; prefer the bound method
    `RespiratorySupport.waterfall()`. DST policy must be identical everywhere:
    `ambiguous="NaT"`, `nonexistent="shift_forward"`.
11. **A negative PCV is a fit-instability diagnostic, not a finding.**

## Conventions

- **Analysis parameters go in `config/project_params.json`**, never in `config.json`
  (gitignored, so invisible to reviewers) and never hardcoded. Each key carries a `_plan`
  pointer to the section that justifies it.
- **Outputs split by data-sharing safety, not pipeline stage.**
  `output/intermediate_phi/` is patient-level and gitignored;
  `output/final_no_phi/` is aggregate and subject to `disclosure.min_cell_size` (default 10).
- **Verify by running, not by reading.** Build synthetic data that exercises each exclusion
  path, then check each path actually fires — a zero count is a bug signal. Render every
  figure and look at it; two real bugs were only visible in the image.
- **Guard silent failures with a visible diagnostic**, not a comment. Failed model fits are
  stored as `"FAILED: ..."` strings and surfaced in the output table rather than skipped.
- **marimo:** variables must be unique across cells; use `_name` sparingly. Never
  `sharey=True` across panels sorted differently — row *i* becomes a different unit per
  panel and the figure is silently mislabelled.
- Deviations from the dashboard are marked `DEVIATION` in config and explained in the plan.
  Suspected upstream bugs go in plan 02 §12.

## CLIF tables in use

`patient` · `hospitalization` · `adt` · `respiratory_support` · `vitals` · `labs` ·
`medication_admin_continuous` · `patient_assessments` · `position`

Plus site-supplied `config/unit_metadata.csv` for `hospital_id` and `location_type`, which
CLIF does not provide above `location_name`.

## Current state

Scaffold complete; all three notebooks run end to end on synthetic data; 13 tests pass;
`marimo check` clean. Not yet run against a real CLIF database — the clifpy branches are
written against the verified 2.1.0 API but untested, and are marked as placeholders.

Largest known code gap: the **SBT domain**. The 12-hour controlled accrual and 2-hour
contiguous stability are approximated from native rows rather than waterfall scaffold hours,
and the **norepinephrine-equivalent criterion is not implemented**, so SBT eligibility is
currently too permissive. See `utils/domains.py::sbt_patient_days` and plan 02 §6.1.
