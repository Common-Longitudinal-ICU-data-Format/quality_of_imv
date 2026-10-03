# `output/final_no_phi/` — aggregate results, safe to share

Aggregate tables and figures with no patient-level rows and no `patient_id`. Every reported
cell must have n ≥ the `disclosure.min_cell_size` in `config/project_params.json` (default 10).

Expected contents:

| File | Written by |
| --- | --- |
| `table1.csv`, `table1.html` | `01_cohort_identification.py` |
| `strobe_counts.json`, `strobe_diagram.png` | `01_cohort_identification.py` |
| `unit_quality_scores.csv` | `02_calculate_quality_score.py` |
| `domain_performance.png`, `domain_correlation.csv` | `02_calculate_quality_score.py` |
| `model_estimates.csv`, `variance_summaries.csv` | `03_outcome_analysis.py` |
| `caterpillar_survival.png`, `caterpillar_vfd.png` | `03_outcome_analysis.py` |

Before sharing anything from this directory, confirm no cell falls below the minimum size.
