# Lessons — CLIF IMV Quality Report

## Verify by running, not by reading

Five of the substantive findings this session came from executing the pipeline on synthetic
data and *looking at the numbers and figures*, not from writing the code carefully:

- An exclusion path that captured zero patients revealed that carry-forward was
  manufacturing cohort eligibility.
- A SAT rate of 0.15 against an intended 0.5 revealed a 102-hour phantom infusion segment.
- Model 3 coefficients of exactly `0.0` revealed collinearity with the hospital random
  effect.
- A visually flat caterpillar plot revealed a missing hospital random effect in the
  standardized predictions.
- A blank figure panel revealed the proning denominator is structurally too small.

**Rule: build synthetic data that deliberately exercises each edge case and each exclusion
path, then check that each path actually fires.** A path with a zero count is a bug signal,
not a clean result. Likewise, render every figure and look at it — two real bugs were only
visible in the image.

## Failures that return plausible numbers are the dangerous ones

None of the five findings above raised an exception. Variational Bayes returned `0.0`; REML
returned `160.7`; the SAT rate just looked bad. When a quantity can fail silently, add an
assertion or a visible diagnostic rather than trusting the output:

- Notebook 02 warns when PBW coverage is below 80% (the exact-case `sex_category` trap).
- Notebook 03 screens Model 3 covariates for within-hospital collinearity and reports what
  it dropped.
- Notebook 03 flags negative PCV as a fit-instability diagnostic, not a result.
- Failed model fits are stored as `"FAILED: ..."` strings and surfaced in the output table
  rather than being skipped.

## Transcribe reference implementations from source, never from docs

The QI dashboard's code and its own `METHODS.md` disagreed (strict `<` vs `≤`), and the
dashboard contains dead config documented in four places but read nowhere
(`session_gap_minutes`) plus five SAT keys that are never consumed. Several definitions were
also the opposite of the intuitive guess: observed tidal volume is preferred over set,
`Pressure Control` *is* an eligible LPV mode, RASS is *not* used for SAT eligibility, and the
SBT duration gate is 2 minutes rather than 30. Reading only the README would have produced
four wrong domains.

## Distinguish missing from zero, every time

A unit with no `position` data has a *missing* proning score, not a zero one. Scoring it as
zero systematically penalizes sites with incomplete data. The same applies to
`not_assessable` patient-days in LPV, and to empty figure panels — a blank panel reads as
zero unless it says otherwise.

## Keep analysis parameters in a committed file

`config/config.json` is gitignored (local paths), so anything in it is invisible to the
research team. Every analysis choice lives in `config/project_params.json` instead, with a
`_plan` key pointing at the section that justifies it. That is what makes the
plan-review-then-update-code workflow actually reviewable in a pull request.
