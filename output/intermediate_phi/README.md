# `output/intermediate_phi/` — CONTAINS PHI, DO NOT SHARE

Patient-level working files written by the notebooks in `code/`. Every file here may contain
`patient_id`, `hospitalization_id`, and row-level clinical records.

This directory is git-ignored. Do not commit its contents, attach them to email or Slack, or
copy them outside your institution's approved environment.

Expected contents:

| File | Written by | Contents |
| --- | --- | --- |
| `cohort.parquet` | `01_cohort_identification.py` | One row per eligible hospitalization: IDs, time zero, attributed unit, Table 1 variables |
| `hospitalization_ids.csv` | `01_cohort_identification.py` | Eligible ID list consumed by notebooks 02 and 03 |
| `patient_domain_flags.parquet` | `02_calculate_quality_score.py` | Per-patient and per-patient-day eligibility and performance flags for each quality domain |
| `analytic_frame.parquet` | `03_outcome_analysis.py` | Modeling frame: outcomes, presentation-window covariates, unit and hospital keys |

Aggregate, shareable results go to `output/final_no_phi/` instead, subject to the minimum
cell size in `config/project_params.json`.
