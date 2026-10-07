# Quality of IMV — CLIF IMV Quality Report

Grading ICU unit-level (`location_name`) performance across four invasive mechanical
ventilation (IMV) quality domains, and associating exposure to ICU quality with ICU
outcomes.

**Domains:** lung-protective tidal volume (LTVV) · spontaneous awakening trials (SAT) ·
spontaneous breathing trials (SBT) · prone positioning

Longer term, this is intended to support an MPOG-style unit-level quality feedback product.

---

## How this project works

The analysis plans are the source of truth, not the code.

```
analysis_plan/*.md   ──reviewed & edited by research team──▶   code/*.py
```

The research team reviews and edits the markdown plans; the notebooks are then updated to
match. Every plan contains **Open decision** blockquotes marking choices that need team
input — resolve those in the markdown first.

## Analysis plans

| Plan | Notebook | Purpose |
| --- | --- | --- |
| [1 — Cohort identification](analysis_plan/01_cohort_identification.md) | [`code/01_cohort_identification.py`](code/01_cohort_identification.py) | Adults with IMV > 4 h admitted to an ICU. Defines time zero. Produces Table 1, STROBE diagram, and the eligible `hospitalization_id` list. |
| [2 — Quality score](analysis_plan/02_quality_score.md) | [`code/02_calculate_quality_score.py`](code/02_calculate_quality_score.py) | Per-`location_name` performance in each of the four domains, combined into the weighted quality score `Q`. |
| [3 — Outcome analysis](analysis_plan/03_outcome_analysis.md) | [`code/03_outcome_analysis.py`](code/03_outcome_analysis.py) | Between-unit variation in risk-adjusted survival and ventilator-free days, and the share attributable to `Q`. |

`analysis_plan/03_outcome_analysis.md` is the converted and revised version of
`CLIF_IMV_quality_concept_WFP.pdf`; its change log records how WFP's five PDF comments were
applied.

## Setup

```bash
uv sync
```

Then create your site config and unit metadata from the templates:

```bash
cp config/config_template.json config/config.json
```

```bash
cp config/unit_metadata_template.csv config/unit_metadata.csv
```

Edit both for your site — see [`config/README.md`](config/README.md). Both are gitignored
because they contain local paths and unit names.

**Until `config/config.json` exists, the notebooks run on synthetic data** from
`utils/synthetic_clif.py` and say so in a banner at the top. That means you can run the
whole pipeline before a site is wired up; it also means any numbers you see are not real.

## Running the notebooks

These are [marimo](https://marimo.io) notebooks — plain Python files, diffable and
reviewable in git.

```bash
uv run marimo edit code/01_cohort_identification.py
```

To run non-interactively as a script:

```bash
uv run code/01_cohort_identification.py
```

Run them in order; each writes intermediate files the next one reads.

## Outputs

| Path | Contents | Shareable? |
| --- | --- | --- |
| `output/intermediate_phi/` | Patient-level files including `hospitalization_id` | **No — contains PHI.** Gitignored. |
| `output/final_no_phi/` | Aggregate tables and figures | Yes, subject to `disclosure.min_cell_size` in `config/project_params.json` |

## Tests

The time-zero logic is the one genuinely subtle piece of the project, so it is unit-tested
against every scenario the cohort plan enumerates:

```bash
uv run pytest utils/test_cohort.py -q
```

## Configuration

Two config files, deliberately separate:

- **`config/config.json`** — the clifpy site config. Gitignored, so anything in it is
  invisible to reviewers.
- **`config/project_params.json`** — every analysis parameter (the 4-hour IMV threshold, the
  LTVV cutoff, the SAT hold duration, the quality-score weights). **Committed**, each key
  carrying a `_plan` pointer to the plan section that justifies it, so analysis choices are
  reviewable in a pull request.

## Where things stand

See [`.claude/claude-progress.md`](.claude/claude-progress.md) for what has been done and
what running the pipeline revealed, and [`.claude/claude-todo.md`](.claude/claude-todo.md)
for the decisions currently blocking code work.

Quality-score weights are `null` by design. Notebook 02 reports all four domain
proportions regardless and computes `Q` only once weights are set; notebook 03 falls back to
clearly-labelled equal weights so the pipeline is demonstrable, and refuses to let those
results pass as reportable.

## Reference

- Quality metric definitions adapted from the [CLIF ventilator QI dashboard](https://github.com/shanguleria/clif-ventilator-qi-dashboard)
- Built on [`clifpy`](https://github.com/Common-Longitudinal-ICU-data-Format/clifpy) and the
  [CLIF](https://clif-consortium.github.io/website/) data format
