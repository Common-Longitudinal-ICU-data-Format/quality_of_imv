# `config/`

| File | Committed? | Purpose |
| --- | --- | --- |
| `config_template.json` | yes | Template for the clifpy site config. Copy to `config.json`. |
| `config.json` | **no** (gitignored) | Your site's clifpy config: `data_directory`, `filetype`, `timezone`. |
| `project_params.json` | yes | Analysis parameters. Reviewed by the research team against `analysis_plan/`. |
| `unit_metadata_template.csv` | yes | Template for site-supplied unit metadata. Copy to `unit_metadata.csv`. |
| `unit_metadata.csv` | **no** (gitignored) | Maps each ICU `location_name` to its hospital and structural covariates. |

## Setup

```bash
cp config/config_template.json config/config.json
cp config/unit_metadata_template.csv config/unit_metadata.csv
```

Then edit both for your site.

## Why `project_params.json` is separate from `config.json`

`config.json` holds local paths and is gitignored, so anything in it is invisible to the
research team. Every analysis choice — the 4-hour IMV threshold, the LTVV cutoff, the SAT
hold duration, the quality-score weights — belongs in `project_params.json` instead, so it
can be reviewed in a pull request against the plan documents that justify it.

## `unit_metadata.csv`

Needed for [Model 3](../analysis_plan/03_outcome_analysis.md#6-model-3--add-unit-and-hospital-covariates),
which adjusts for unit and hospital structural covariates, and for the nested hospital
random effect in all three models. CLIF has no hospital identifier above
`location_name`, so this mapping has to come from the site.

`hospital_id` and `location_type` are required. `hospital_beds` and `academic` are
optional — if your site cannot supply them, Model 3 reduces to unit volume and data
completeness, which are computable from the data itself. Note that in
`analysis_plan/03_outcome_analysis.md` section 6 this is flagged as an open decision.
