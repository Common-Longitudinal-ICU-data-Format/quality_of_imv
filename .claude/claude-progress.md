# Progress — CLIF IMV Quality Report

_Last updated: 2026-09-27 (session 2)_

## Session 2 (2026-09-27) — project CLAUDE.md

Added `CLAUDE.md` at the project root. It was absent, so every fresh session had to
rediscover the layout, the plans-then-code workflow, and the eleven silent-failure traps.
Content is the workflow, repo layout, verified commands, the core concepts (time zero, the
presentation window, `Q`), the trap list, conventions, and current state.

Verified rather than assumed: every command in it runs, every API reference resolves, every
config key exists with the cited value, and every plan section number it points at is
correct.

Two fixes fell out of that verification:

- **`pytest` was not a declared dependency**, so the documented
  `uv run pytest utils/test_cohort.py -q` would have failed for anyone following the file.
  Added as a `dev` dependency group; `uv sync` then `uv run pytest` now both work, and all
  three notebooks run headless with a plain `uv run` (no `--with` flags).
- **Plan/code drift in the SBT domain.** Plan 02 claimed the dashboard definition was
  "adopted as-is", which was false — the code approximates the 12-hour accrual and the
  2-hour stability window, and does not implement the norepinephrine-equivalent criterion at
  all. Since all three make eligibility more permissive, the denominator is too large and
  `p_SBT` is biased *downward*, which matches the synthetic run (0.57 against dashboard
  0.25–0.45). Plan 02 §6 now carries a table of the three gaps and their direction, and
  notebook 02's validation output marks SBT `comparable = NO — definition incomplete` so the
  gap is not mistaken for a transcription error.

This is exactly the drift the plans-then-code workflow exists to catch, and it was caught by
checking a cross-reference rather than by reading the code.

## Session 1 (2026-09-27) — project set up from scratch

Started from a directory containing only `CLIF_IMV_quality_concept_WFP.pdf` and `plan.rtf`.

### Delivered

**Three analysis plan markdowns** (`analysis_plan/`), the reviewable source of truth:

- `01_cohort_identification.md` — adults, IMV > 4 h, ICU. Time zero formalized as
  `t0 = min{t : in_icu(t) and cumulative_imv(t) >= 4h}`, which reproduces both scenarios
  the team specified.
- `02_quality_score.md` — the four domains transcribed from the QI dashboard source
  (commit `7ea68ec`), with every constant quoted and its file named. `Q` with weights left
  unspecified.
- `03_outcome_analysis.md` — converted from the PDF with all five WFP margin notes applied.
  A change log at the end maps each note to what changed.

**Three marimo notebooks** (`code/`), all runnable end to end on synthetic data.

**Testable logic modules** (`utils/`): `cohort.py` (13 passing tests), `domains.py`,
`severity.py`, `project_config.py`, `synthetic_clif.py`.

### The five WFP PDF notes, and how each was applied

| Note | Change |
| --- | --- |
| "not a problem IMO" (mechanical coupling) | Downgraded to a documented team position with the O(1/n_i) argument. LOPO and temporal split kept as cheap sensitivities. |
| "maybe IMV > 4 hours is better for primary" | **Primary cohort changed from IMV > 24 h to > 4 h.** 24 h demoted to sensitivity. |
| "only calculate these values using presentation values" | **SOFA window changed from worst-in-first-24 h to a 4-hour window ending at time zero**, so covariates are pre-exposure. |
| "add random hospital effect to all models ... 3rd model" | Notation made three-level; hospital random intercept in all models; **new Model 3**; VPC added. |
| "covariates for a typical patient ... heart survival benefit paper" | **Population-standardized predictions made primary** via G-computation; reference-patient version secondary. Method flagged for WFP to confirm. |

### Findings from running the pipeline (each is written into the relevant plan)

These are the substantive things that came out of actually executing the code, not from
reading it. All five are documented as open decisions in the plans.

1. **Carry-forward can manufacture cohort eligibility.** With a 6-hour trailing
   carry-forward, two hourly IMV rows accrue 7 apparent hours and clear the 4-hour
   threshold. The "IMV ≤ 4 h" exclusion path captured *zero* patients until a 1-hour
   trailing clip was added. At a 4-hour threshold the carry-forward rule is a cohort
   definition. → plan 01 §3
2. **Uncapped interior infusion segments silently deflate the SAT rate.** A drug whose next
   same-drug row is days later becomes a multi-day phantom infusion that swallows real
   sedation holds. Produced a pooled SAT rate of 0.15 against an intended 0.5 from a single
   102-hour phantom segment. Believed to be a genuine bug in the dashboard. → plan 02 §11
3. **Hospital-level covariates cannot enter Model 3.** Constant within hospital means
   perfectly collinear with the hospital random intercept. Does not error: VB returned
   coefficients of exactly `0.0`, REML returned `academic = 160.7` days. → plan 03 §6.1
4. **The hospital random effect absorbs ~47% of Q's variance.** β1 rests only on
   within-hospital unit contrasts. A small β1 would then mean "little quality variation
   survives the hospital adjustment," not "quality doesn't matter." → plan 03 §6.1
5. **The proning denominator may be too small to score per unit.** Per-encounter and gated
   by two nested P/F criteria: 8–15 eligible per unit against 42–112 for the patient-day
   domains, so it was suppressed for every unit. → plan 02 §7.2

### Verification done

- `utils/test_cohort.py`: 13 tests, all passing, covering each time-zero scenario in the
  plan plus the exclusion paths.
- All three notebooks run clean via `uv run`, producing every declared output.
- `marimo check`: no errors on any notebook (only cosmetic `markdown-indentation`).
- Figures inspected visually; two real bugs found and fixed that way — a flat caterpillar
  plot (missing hospital random effect in the standardized predictions) and a
  `sharey=True` domain figure where row *i* was a different unit in each panel.

### Reference material gathered

- clifpy **2.1.0** verified by introspection. `ClifOrchestrator(config_path=...)`, `.df` is
  pandas, `Table.from_file(columns=, filters=)`. `calculate_sofa2(cohort_df)` takes
  arbitrary `[id, start_dttm, end_dttm]` windows — an exact fit for the 4-hour presentation
  window.
- **CLIF 2.1 uses title case** (`IMV`, `Assist Control-Volume Control`); 3.0 uses snake_case
  (`imv`, `acvc`). clifpy defaults to 2.1. Wrong casing gives empty filters, not errors.
- `position` is `supported: false` in clifpy's wide-table config, so it must be joined
  manually.
- Dashboard validation targets recorded in plan 02 §9 and checked automatically by
  notebook 02.
