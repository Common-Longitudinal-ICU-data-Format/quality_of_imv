---

editor_options: 
  markdown: 
    wrap: 72
---

# Analysis Plan 1 — Cohort Identification

**CLIF IMV Quality Report** Corresponding notebook: [`code/01_cohort_identification.py`](../code/01_cohort_identification.py)

> **How to use this document.** This is the editable source of truth for cohort construction. The research team reviews and edits this file; the notebook is then updated to match. Decisions that need team input are in **Open decision** blockquotes.

**Deliverables of this stage:** (1) a Table 1, (2) a STROBE diagram, (3) a saved list of eligible `hospitalization_id`s with each patient's time zero and attributed unit, consumed by [Plan 2](02_quality_score.md) and [Plan 3](03_outcome_analysis.md).

------------------------------------------------------------------------

## 1. Target population

All **adult patients receiving invasive mechanical ventilation for more than 4 hours who were admitted to an ICU from 1/1/2022- 12/31/2025.**

## 2. Unit of analysis

One row per **eligible ICU IMV episode**, and — in the primary analysis — **one episode per hospitalization**: the first episode that meets the entry criteria. `hospitalization_id` is therefore the primary key of the cohort table.

> **Open decision.** Patients with a second, separate ICU IMV episode in the same hospitalization (extubated, left the ICU, later re-intubated) contribute only their first episode. The alternative is one row per episode with a patient-level random effect. First episode only is assumed because it keeps the exposure–outcome mapping clean; please confirm.

> **Open decision.** Hospital transfers arrive in CLIF as separate `hospitalization_id`s. `clifpy`'s encounter-stitching utility can link them into a single episode. Stitching is more clinically correct but complicates unit attribution and outcome attribution across sites. The draft assumes **no stitching** for the primary analysis, with stitching as a sensitivity analysis. Please confirm.

## 3. Time zero

**Time zero is the first moment at which the patient is simultaneously (a) in an ICU and (b) has accumulated at least 4 hours of IMV during the hospitalization.**

Formally, for hospitalization $j$, let $\mathrm{ICU}_j(t)$ be the indicator that the patient is in an ICU location at time $t$, and let

$$A_j(t) = \int_{0}^{t} \mathbb{1}\!\left[\text{on IMV at } s\right]\, ds$$

be cumulative time on IMV. Then

$$t^{0}_j = \min\left\{\, t \;:\; \mathrm{ICU}_j(t) = 1 \ \ \text{and} \ \ A_j(t) \ge 4\text{h} \,\right\}$$

A hospitalization is eligible only if this set is non-empty — i.e. the patient was at some point both in an ICU and past 4 cumulative hours of IMV.

This single definition produces the two behaviours the team specified:

| Scenario | $A(t)$ at ICU admission | Time zero |
|------------------------|------------------------|------------------------|
| Intubated in the ED, 8 h of IMV, then admitted to ICU | 8 h (already ≥ 4 h) | **ICU admission time** — both conditions first hold at ICU arrival |
| Intubated in the ICU | 0 h at ICU arrival | **IMV onset + 4 h** — the ICU condition already holds, so the binding constraint is the 4-hour clock |
| Intubated in the ED for 2 h, then ICU, continues on IMV | 2 h | **ICU admission + 2 h** — the clock carries the ED time forward |

Note that IMV time accrued anywhere (ED, OR, ward, outside hospital) counts toward the 4 hours; only the *location at time zero* must be an ICU.

> **Open decision.** Must the 4 hours be **contiguous**, or is cumulative time across brief interruptions sufficient? The draft uses **cumulative**, which is more robust to documentation gaps in `respiratory_support` (a missing row is not the same as an extubation). A contiguous definition would require a rule for the maximum gap that does not break an episode.

> **Open decision — and the most consequential one in this document.** Gap handling in `respiratory_support`. Device is recorded at irregular intervals, so "on IMV at time $s$" requires carrying the last observed `device_category` forward. The draft uses **two** caps, following the dashboard's `MAX_GAP` and `TRAIL_CLIP`:
>
> - **Interior gaps: 6 hours.** A row followed by a later observation carries forward to that observation, or 6 hours, whichever is shorter.
> - **The final row of the record: 1 hour.**
>
> The second cap is not a detail. With a 6-hour trailing carry-forward, a patient with two hourly IMV observations accrues $1 + 6 = 7$ apparent hours of ventilation and **enters the cohort on the strength of a single unresolved observation** — at a 4-hour threshold, the carry-forward rule alone can manufacture eligibility. This was caught by the synthetic-data exclusion counts during development: with a 6-hour trailing cap, the "IMV ≤ 4 hours" exclusion path captured zero patients because every short episode was inflated past the threshold.
>
> Both values are arbitrary and should be set by the team. The notebook reads them from `config/project_params.json` (`device_carry_forward_max_hours`, `device_trailing_clip_hours`), and `utils/test_cohort.py` pins the behaviour. **Report the cohort size under at least one alternative pair**, since the 4-hour threshold sits in exactly the region where this choice bites.

## 4. Inclusion criteria

1.  **Adult** — age ≥ 18 years at hospital admission.
2.  **ICU admission** — at least one ADT record with `location_category == 'icu'`.
3.  **Invasive mechanical ventilation** — at least one `respiratory_support` record with `device_category == 'imv'`.
4.  **IMV \> 4 hours** — cumulative IMV duration exceeds 4 hours.
5.  **Time zero exists** — the patient was in an ICU at or after the moment the 4-hour threshold was crossed (§3).
6.  **Usable timestamps** — non-missing, ordered admission, ICU, and respiratory-support timestamps sufficient to compute time zero.

## 5. Exclusion criteria

- Age \< 18 at admission.
- No ICU stay during the hospitalization.
- No IMV during the hospitalization.
- Cumulative IMV ≤ 4 hours.
- Threshold crossed but never while in an ICU — e.g. ventilated in the ED and extubated or died before ICU arrival, or went from OR directly to a ward.
- Unusable or internally inconsistent timestamps (documented as a count, with reasons).

> **Open decision.** Should patients on **chronic invasive ventilation via tracheostomy at admission** be excluded? The four quality domains largely do not apply to them: they are not candidates for lung-protective-volume targeting in the usual sense, SAT/SBT protocols differ, and proning is rarely indicated. Including them would penalize units that care for many chronically ventilated patients. The draft **excludes** patients with a tracheostomy present at time zero, and reports the count. Please confirm — and note this is only identifiable if `device_category` or `tracheostomy` fields distinguish trach from endotracheal tube at baseline.

> **Open decision.** Should we exclude patients receiving **ECMO** at or before time zero? Ventilation targets are deliberately different on ECMO (ultra-protective settings, and liberation is not the immediate goal), so these patients would distort all four domains. Recommend excluding from the quality-score denominators at minimum; whether to exclude them from the outcome cohort entirely is a separate question.

> **Open decision.** Should patients with a **comfort-care / limitation-of-treatment order at or shortly after time zero** be excluded or flagged? A unit that appropriately withdraws support looks poor on both SAT/SBT process measures and on mortality. If CLIF code-status data is available at participating sites this is worth a flag; if not, it belongs in the limitations section.

## 6. Unit (`location_name`) attribution

Each eligible episode is attributed to **the ICU `location_name` the patient occupied at time zero**. This is the unit that "receives" the patient and whose quality score the patient's outcome is associated with in [Plan 3](03_outcome_analysis.md).

> **Open decision.** Patients who transfer between ICUs are attributed entirely to their time-zero unit, even if most of their ventilated time was elsewhere. Alternatives: (a) attribute to the unit with the **plurality of ventilated hours**; (b) attribute fractionally, weighting each unit by its share of the patient's ventilated time. Time-zero attribution is assumed because it is the only option that is unambiguously not influenced by post-exposure events (a patient transferred out *because* of a poor course would otherwise be reattributed). Report the proportion of patients who spend time in more than one ICU, since this bounds how much the choice can matter.

Units are identified by the pair (site, `location_name`), since `location_name` values are site-specific and may collide across sites.

## 7. STROBE diagram

Sequential counts, each reported as hospitalizations (and distinct patients):

```         
All hospitalizations in the CLIF database                            N = ...
  └─ excluded: age < 18 at admission                                 n = ...
Adult hospitalizations                                              N = ...
  └─ excluded: no ICU stay                                           n = ...
Adult hospitalizations with an ICU stay                             N = ...
  └─ excluded: no invasive mechanical ventilation                    n = ...
Adult ICU hospitalizations with any IMV                             N = ...
  └─ excluded: cumulative IMV ≤ 4 hours                              n = ...
Adult ICU hospitalizations with IMV > 4 hours                       N = ...
  └─ excluded: 4-hour threshold never reached while in an ICU        n = ...
  └─ excluded: unusable timestamps                                   n = ...
  └─ excluded: tracheostomy at time zero            [if adopted]     n = ...
  └─ excluded: ECMO at time zero                    [if adopted]     n = ...
ANALYTIC COHORT                                                     N = ...
  └─ in units below the minimum-denominator threshold for Q          n = ...
COHORT WITH AN ESTIMABLE UNIT QUALITY SCORE                         N = ...
```

The final step matters for [Plan 3](03_outcome_analysis.md): patients in units too small for a stable quality score stay in Model 1's variance estimate but drop out of Models 2 and 3, and that differential inclusion has to be visible.

## 8. Table 1

Stratified by **unit quality-score quartile** in the final manuscript, and by site during development for data-quality review. Continuous variables as median (IQR) unless stated.

**Demographics and administrative** - Age; sex; race and ethnicity; BMI - Admission source (ED, OR, ward, outside transfer) - Site; ICU `location_name`; unit type

**Severity at presentation** — all from the 4-hour presentation window ending at time zero (see [Plan 3 §3](03_outcome_analysis.md#3-risk-adjustment-uses-presentation-values-only)), so that Table 1 and the risk-adjustment model use identical definitions - Six SOFA components (respiratory, coagulation, liver, cardiovascular, CNS, renal) and total - P/F ratio (or S/F if P/F unavailable); ARDS severity category - Vasopressor use; lactate - Comorbidity index (Charlson and/or Elixhauser)

**Ventilation at time zero** - Intubated before ICU arrival (yes/no), and hours of IMV already accrued at time zero - Ventilator mode category; set tidal volume and mL/kg predicted body weight; PEEP; FiO₂ - Predicted body weight, and the height and sex used to compute it

**Course and outcomes** (descriptive here; analyzed in [Plan 3](03_outcome_analysis.md)) - Duration of IMV; ICU length of stay; hospital length of stay - Received prone positioning; received tracheostomy - In-hospital mortality; ventilator-free days at day 28

**A missingness column is required** for every variable, reported per site. Because the presentation window is only 4 hours, lab-based SOFA components will be materially more missing than in a 24-hour window — this table is how we find out how bad it is, and it feeds the imputation decision in [Plan 3 §10](03_outcome_analysis.md#10-missing-data).

## 9. CLIF tables required

| Table | Used for |
|------------------------------------|------------------------------------|
| `patient` | Age, sex, race, ethnicity |
| `hospitalization` | Admission and discharge timestamps, discharge disposition, admission source, age at admission |
| `adt` | ICU identification (`location_category == 'icu'`), `location_name` for unit attribution, ICU entry and exit times |
| `respiratory_support` | IMV identification (`device_category == 'imv'`), mode, tidal volume, PEEP, FiO₂ |
| `vitals` | Height and weight for predicted body weight and BMI; vitals for SOFA |
| `labs` | SOFA components (PaO₂, platelets, bilirubin, creatinine) |
| `medication_admin_continuous` | Vasopressors for cardiovascular SOFA; sedatives for SAT eligibility in [Plan 2](02_quality_score.md) |
| `patient_assessments` | GCS or RASS for CNS SOFA; RASS for SAT in [Plan 2](02_quality_score.md) |
| `position` | Prone positioning for [Plan 2](02_quality_score.md) |
| `hospitalization_diagnosis` | Comorbidity indices |

## 10. Outputs

Written to `output/intermediate/` (contains protected health information — never committed):

- `cohort.parquet` — one row per eligible hospitalization: `hospitalization_id`, `patient_id`, `site`, `location_name`, `time_zero`, `imv_start`, `imv_hours_at_t0`, `intubated_before_icu`, plus all Table 1 variables.
- `hospitalization_ids.csv` — the bare eligible ID list, for downstream notebooks.
- `strobe_counts.json` — every count in §7, so the diagram is reproducible.

Written to `output/final/` (aggregate only, safe to share):

- `table1.csv` / `table1.html`
- `strobe_diagram.png`

> **Open decision.** Minimum cell size for anything written to `output/final/`. CLIF convention is typically to suppress cells with fewer than 10 patients. Confirm the threshold so the Table 1 code can enforce it automatically.

## 11. Data-quality checks to run before trusting the cohort

These are not optional — every one of them has produced a real bug in a CLIF project before.

1.  **Time-zero sanity**: `time_zero` falls within the hospitalization, and within an ICU stay per `adt`. Zero tolerance for violations.
2.  **Timezone consistency**: all timestamps in a single site-local timezone as declared in `config.json`. Mixed naive and timezone-aware timestamps silently produce nonsense durations.
3.  **IMV duration distribution**: inspect for implausible values (negative, or longer than the hospitalization) and for spikes at round numbers that indicate imputed timestamps.
4.  **`location_name` cardinality**: count distinct ICU `location_name` values per site and eyeball them. Free-text or inconsistently-cased values will fragment units and destroy the unit-level denominators.
5.  **Unit denominators**: patients per `location_name`. Units with very few patients cannot support a stable quality score (see [Plan 2](02_quality_score.md)).
6.  **Device-category coverage**: proportion of `respiratory_support` rows with a non-null `device_category`, per site. Poor coverage makes the 4-hour clock unreliable.
