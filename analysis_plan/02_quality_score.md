---

editor_options: 
  markdown: 
    wrap: 72
---

# Analysis Plan 2 — Unit-Level IMV Quality Score

**CLIF IMV Quality Report** Corresponding notebook: [`code/02_calculate_quality_score.py`](../code/02_calculate_quality_score.py)

> **How to use this document.** This is the editable source of truth for the quality score. The research team reviews and edits this file; the notebook is then updated to match. Decisions needing team input are in **Open decision** blockquotes.

**Notebook output:** one row per unit with the four domain proportions, the composite score $Q_i$, its standardized version, and the number of patient-days denominator behind each proportion.

------------------------------------------------------------------------

## 1. Goal: a standardized, scalable ICU process measure built on CLIF

Summarize how well each ICU unit delivers four evidence-based IMV processes into a single unit-level score. The score is the unit-level **exposure** in the outcome analysis ([Plan 3](03_outcome_analysis.md))and the basis of any future MPOG-style unit CLIF feedback report.

1.  **Established RCT proven interventions.** Every domain measures whether a unit did the right thing when it had the opportunity. Nothing in $Q_i$ is a patient outcome. This is what makes the mechanical-coupling argument in [Plan 3 §8.1](03_outcome_analysis.md#81-mechanical-coupling--judged-not-a-material-problem-wfp-note-1) hold.
2.  **Broad inclusion of all IMV patients.** We will avoid applying somewhat arbitrary "exclusion" criteria for LTTV, SAT, and SBT. Instead, there will be some expected non-adherence to these practices, as they are inappropriate for some patients (e.g. severe acidosis for LTTV, paralysis for SAT). Proning will only be evaluated for patients who meet PROSEVA hypoxemia.

## 2. Unit of aggregation- ICU "unit"

A **unit** is the pair (`site`, `location_name`) restricted to ICU locations (`location_category == 'icu'`). `location_name` values are site-specific and may collide across sites, so site is always part of the key.

The dashboard publishes two dimensions side by side: `location_type` (e.g. `medical_icu`, with a pooled `__ALL__` row) and `location_name` (the specific physical unit, e.g. `N09S`, nested under its type as `parent`). **This project scores at `location_name`**, per the project objective, and carries `location_type` along as a unit-level covariate for [Plan 3 Model 3](03_outcome_analysis.md#6-model-3--add-unit-and-hospital-covariates).

**Note:** This unit *may* require site specific `location_name` -\> unit mappings. For example, `N09N` and `N09S` are really best thought of as one 24 bed unit at University of Chicago.

### 2.1 Denominator for each unit

The denominator for each unit should have followed the quality measure will dependent on the measure

- LTTV: all controlled mode mechanical ventilation hours while the patient was in the ICU

- SAT and SBT: the unit the IMV patient was in 7 AM. All patients on IMV are included in the primary analysis.

- Proning: $T_{\text{eligible}}$ - the location where the patient met PROSEVA criteria

## 3. Cohort for CLIF quality score: all adult IMV patients

The contributing population is **all cohort-eligible patients attributed to unit** $i$ per [Plan 1](01_cohort_identification.md).

## 4. Domain 1 — Lung-protective ventilation ($p^{\mathrm{LTVV}}_i$)

**Definition:** Proportion of controlled mode ventilator-hours where the patient was receiving \< 8 cc/kg/IBW

### 4.1 Predicted body weight

Height from `vitals` where `vital_category == 'height_cm'`, taken as the **median per hospitalization**, falling back to the median across that patient's other hospitalizations. Bounds `HEIGHT_CM_MIN = 100.0`, `HEIGHT_CM_MAX = 230.0` (outside → `NaN`).

$$\mathrm{PBW} =
\begin{cases}
50.0 + 2.3\,\left(\mathrm{height}_{\mathrm{in}} - 60\right) & \text{sex\_category} = \texttt{"Male"} \\
45.5 + 2.3\,\left(\mathrm{height}_{\mathrm{in}} - 60\right) & \text{sex\_category} = \texttt{"Female"}
\end{cases}
\qquad
\mathrm{height}_{\mathrm{in}} = \frac{\mathrm{height}_{\mathrm{cm}}}{2.54}$$

For missing heights or obvious data-entry errors, we will impute sex-specific median heights.

### 4.2 Tidal volume

$$\mathrm{VT}^{\mathrm{eff}} = \mathrm{tidal\_volume\_obs} \ \ \text{if present, else} \ \ \mathrm{tidal\_volume\_set},
\qquad
\mathrm{VT}^{\mathrm{norm}} = \frac{\mathrm{VT}^{\mathrm{eff}}}{\mathrm{PBW}}$$

**Observed tidal volume is preferred over set** in the primary analysis.

### 4.3 Eligible ventilator modes

``` python
ELIGIBLE_MODES = {
    "Assist Control-Volume Control",
    "Pressure-Regulated Volume Control",
    "SIMV",
    "Pressure Control",
}
```

**We exclude spontaneous modes in the primary analysis.** We

These are **CLIF 2.1 title-case** values. Under CLIF 3.0 the corresponding `mode_category` values are `acvc`, `prvc`, `simv`, `pressure_control`, and `device_category` is `imv`. The notebook must branch on `clif_version` — see §11.

### 4.4 Interval construction and carry-forward

LPV uses **raw native `respiratory_support` rows, not the clifpy waterfall**, because the waterfall's hourly scaffold rows would double-count minute-weighted intervals. Each row's interval runs to the next row's timestamp, split at local midnight.

| Constant | Value | Applies to |
|------------------------|------------------------|------------------------|
| `CF_FAST` | 2 h | tidal volume, PEEP, FiO₂ |
| `CF_SLOW` | 6 h | plateau pressure, mode, tracheostomy |
| `MAX_GAP` | 24 h | maximum interval before the signal is dropped |
| `TRAIL_CLIP` | 1 h | cap on the final row's interval |
| `DAY_CAP` | 1500 min | assertion bound (admits the 25-hour DST fall-back day) |

### 4.5 Per-day status and the four measures

Four measures each carry their **own denominator** (`MEASURES = ["vt", "plat", "dp", "comp"]`):

``` python
vt_present   = elig & pieces["tv_eff"].notna() & pieces["pbw_kg"].notna()
plat_present = elig & pieces["plateau_eff"].notna()
dp_present   = elig & pieces["driving_pressure"].notna()
comp_present = vt_present & dp_present
```

A day enters a measure's denominator only with at least `MIN_ASSESSABLE_MIN = 60` minutes of that signal. Given assessable minutes and in-target minutes:

$$\mathrm{status} =
\begin{cases}
\texttt{not\_assessable} & \text{assessable minutes} < 60 \\
\texttt{adherent} & \dfrac{\text{in-target minutes}}{\text{assessable minutes}} \ge 0.80 \\
\texttt{non\_adherent} & \text{otherwise}
\end{cases}$$

with `ADHERENCE_FRACTION = 0.80`. So a day is adherent if the patient spent at least 80% of assessable ventilated minutes at target — not all of it.

Thresholds: `PLATEAU_MAX = 30.0` cmH₂O, `DP_MAX = 15.0` cmH₂O. Driving pressure uses the PEEP **recorded concurrently with the plateau** (carried on the 6-hour window) to avoid spurious negative values, with negative results set to `NaN`.

### 4.6 The tidal volume threshold — the dashboard uses three

| Constant | Value | File | Role |
|------------------|------------------|------------------|------------------|
| `VT_MAX_DEFAULT` | **6.0** | `02_features.py` | cutoff at which the stored per-day status is classified (ARDSNet) |
| `VT_DEFAULT` | 8.0 | `03_aggregate.py` | dashboard slider initial position (presentational) |
| `SCORECARD_VT_CUTOFF` | **8.0** | `05_tile_feed.py` | the published tile headline |
| `LPV_GOAL` | 0.90 | `05_tile_feed.py` | goal line |

A `VT_GRID` of cutoffs from 4.0 to 10.0 is precomputed so the slider moves without recomputation. **The headline published number is 8 mL/kg PBW; the stored parquet status is 6.**

> **Open decision.** Use $\tau = 8$ mL/kg for $Q_i$ to match the dashboard's published headline (recommended, and the default in `config/project_params.json`), and report $\tau = 6$ as a secondary. A unit can hit 8 reliably while never attempting 6, so the two measure different things and the 6 version is the more demanding test of ARDSNet practice.

### 4.7 Two published rates

$$\text{assessable rate} = \frac{n_{\mathrm{adherent}}}{n_{\mathrm{adherent}} + n_{\mathrm{non\_adherent}}},
\qquad
\text{crude rate} = \frac{n_{\mathrm{adherent}}}{n_{\mathrm{total}}}$$

**Headline is the assessable rate.** The crude rate keeps not-assessable days in the denominator and is the conservative companion; the gap between the two *is* a measure of charting completeness, and is worth reporting per unit as a data-quality diagnostic.

$$p^{\mathrm{LTVV}}_i = \frac{n_{\mathrm{adherent}, i}}{n_{\mathrm{adherent}, i} + n_{\mathrm{non\_adherent}, i}}$$

### 4.8 Severity stratifier

The dashboard also publishes "Vt in severe" using `PF_THRESHOLD = 300.0`, `SF_THRESHOLD = 315.0`, `SPO2_MAX_FOR_SF = 97.0`, `PEEP_MIN = 5.0`, with FiO₂/PEEP paired to the oxygenation value by a 4-hour backward `merge_asof`, and the day classified by its worst value. PaO₂ from `labs.lab_category == 'po2_arterial'`; SpO₂ from `vitals.vital_category == 'spo2'`.

> **Note the code/docs disagreement.** The code uses strict `< 300`, `< 315`, and `peep > 5`; the dashboard's `METHODS.md` and README write `≤ 300`, `≤ 315`, `PEEP ≥ 5`. We follow the code and flag it upstream.

### Deviation for this project

- Restricted to the Plan 1 cohort and the §3 scoring window.
- Partial first and last days: the dashboard's 60-minute assessability floor already handles these gracefully, so no extra rule is needed.

> **Open decision.** The dashboard pools patient-days, which weights patients by ventilated duration — one patient ventilated three weeks can dominate a small unit's score. For a *unit feedback* product that is arguably correct (it reflects total care delivered). For a *patient-level exposure* in [Plan 3](03_outcome_analysis.md) it is more awkward, and it makes the leave-one-patient-out sensitivity analysis less clean. Recommend reporting the dashboard-matching day-pooled rate as primary (so numbers are comparable to existing work) and a per-patient-then-averaged rate as a pre-specified sensitivity analysis. `aggregate_within_patient_first` in `config/project_params.json` toggles this.

## 5. Domain 2 — Spontaneous awakening trials ($p^{\mathrm{SAT}}_i$)

**Grain: calendar day (site timezone) on which the patient is on IMV and in an ICU.** Built on the clifpy waterfall. The dashboard stores `icu_day` deliberately as a `"YYYY-MM-DD"` **string**, not a date dtype, for parquet and DuckDB merge-key robustness.

### 5.1 Eligibility (denominator)

``` python
out["eligible"] = out["on_sat_sedation"] & ~out["on_paralytic"]
```

evaluated as a day-overlap test against per-drug active-interval unions (`i.start < d.day_out AND i.end > d.day_in`).

From `definitions/sat.json`:

``` json
"sedative_analgesic_categories": ["propofol", "midazolam", "fentanyl", "hydromorphone",
                                  "morphine", "remifentanil", "ketamine"],
"dexmedetomidine_categories": ["dexmedetomidine"],
"paralytic_categories": ["cisatracurium"]
```

Source: `medication_admin_continuous` → `hospitalization_id`, `admin_dttm`, `med_category`, `med_dose`, `med_dose_unit`, `mar_action_category`. `med_category` matched **lowercased on both sides**.

Three facts that differ from how one might guess this works:

- **RASS is not used for eligibility.** The dashboard lists RASS as a "secondary validation lens only."
- **Dexmedetomidine-only days are excluded implicitly**, not by a filter: eligibility *requires* a SAT-relevant infusion, and dexmedetomidine is not in that set. `on_dex` is computed only for reporting.
- **Only cisatracurium** is in SAT's paralytic list, whereas SBT's is much broader (§6.1). This looks like an inconsistency in the dashboard rather than a clinical distinction.

> **Open decision.** Should we widen the SAT paralytic exclusion to SBT's list (`cisatracurium`, `rocuronium`, `vecuronium`, `atracurium`, `pancuronium`)? Recommend **yes** — a patient on continuous vecuronium is as ineligible for a SAT as one on cisatracurium, and the asymmetry appears unintentional. This is a deliberate deviation from the dashboard and should be flagged upstream to its maintainer.

> **Open decision.** The dashboard excludes **only** paralytic days. Prone positioning, ECMO, and therapeutic sedation for status epilepticus or intracranial hypertension are *not* excluded, so units caring for such patients are penalized. [Plan 2 draft §5.1 originally proposed excluding proning and ECMO days.] Proning and ECMO are both derivable in CLIF. Recommend adding them as a pre-specified deviation; the neurologic indications are not identifiable and belong in limitations.

### 5.2 Numerator — "SAT performed"

A SAT is a **hold**: a gap in the union of active SAT-relevant infusions.

``` python
active = (med_dose > 0) & (mar_action_category != "stop")
```

with segments running from each `admin_dttm` to the next, the final one capped at `TRAILING_CAP_H = 24`. Only the literal lowercase `"stop"` is special-cased; there is no `"start"` handling.

The gap scan **starts at the end of the first active block**, so pre-sedation lead-in can never be mistaken for a hold:

``` python
holds = [(gs, ge, res) for (gs, ge, res) in gaps if (ge - gs) >= hold_td]
sat_performed = len(holds) > 0
```

with `hold_min_minutes = 30` (inclusive), justified by roughly hourly charting. **Resumption is not required** for the hold to count. Dexmedetomidine continuing through the hold is invisible here, which is intended.

$$p^{\mathrm{SAT}}_i = \frac{n_{\mathrm{SAT}, i}}{n_{\mathrm{eligible}, i}}$$

The dashboard also publishes `rate_sat_of_vent`, `rate_resumed`, and `rate_extubated_of_sat`, plus a Kress ratio drill-down (per-drug post/pre dose for the first resumed hold, `kress_half_dose_threshold = 0.5`).

### Deviation for this project

- Restricted to the Plan 1 cohort and the §3 scoring window. **This also supplies the age filter the dashboard lacks** — the dashboard applies `age >= 18` only in LPV and proning, not SAT or SBT, so pediatric ventilator-days enter those denominators if present in the source data. Our cohort is adults by construction.
- Paralytic list and proning/ECMO exclusions per the open decisions above.

## 6. Domain 3 — Spontaneous breathing trials ($p^{\mathrm{SBT}}_i$)

Same ventilated-ICU-day grain as SAT, but SBT builds its **own** ICU ∩ IMV waterfall rather than reusing SAT's sedation-scoped cache, so never-sedated patients are included.

Mode vocabulary, lowercased (`definitions/sbt.json`):

``` json
"controlled_modes": ["assist control-volume control", "pressure control",
                     "pressure-regulated volume control", "simv"],
"support_modes":    ["pressure support/cpap"]
```

### 6.1 Eligibility (denominator) — after Jain et al., *Critical Care Medicine*

| Parameter                 | Value  |
|---------------------------|--------|
| `controlled_min_hours`    | 12     |
| `stability_min_hours`     | 2      |
| `fio2_max`                | 0.50   |
| `peep_max`                | 8      |
| `spo2_min`                | 88     |
| `ne_equiv_max_mcg_kg_min` | 0.2    |
| `exclude_trach_days`      | `true` |
| `exclude_paralytic_days`  | `true` |

**12 hours of controlled ventilation** is counted as waterfall scaffold hours strictly before the day's start (each hourly scaffold row ≈ 1 clock-hour), i.e. cumulative since intubation rather than within-day.

**≥ 2 contiguous hours of stability**: a scaffold hour is stable iff `FiO2 <= 0.50 & PEEP <= 8 & SpO2 >= 88 & NEE <= 0.2`, with `NaN` counting as *not* stable, SpO₂ and the norepinephrine-equivalent step function resampled onto each scaffold hour by backward `merge_asof`, and `MAX_HOUR_GAP = 90 min` defining contiguity. Three nested booleans are emitted for the dashboard's toggles: `stable_window` (all four criteria), `stable_window_no_ne` (oxygenation only), `stable_window_ne_only` (pressors only).

**Trach**: `tracheostomy >= 1` on any waterfall row in the day.

Status is a single categorical with priority trach \> paralytic \> stability/accrual:

``` python
out["eligibility_status"] = np.select(
    [cond_trach, cond_paral, cond_elig, cond_notassess],
    ["excluded_trach", "excluded_paralytic", "eligible", "not_assessable"],
    default="not_eligible",
)
```

plus a `notelig_reason` partition (`lt12h_controlled`, `failed_vasopressor`, `failed_oxy_peep`) with an assertion that the partition is exact. Assessability is tracked separately so all-missing days become `not_assessable` rather than silently not-eligible.

**Norepinephrine equivalents** use `standardize_dose_to_base_units`, then per-kg normalization with weight ASOF-merged from vitals. Factors: norepinephrine 1.0, epinephrine 1.0, phenylephrine 0.1, dopamine 0.01, vasopressin 2.5 (kept as u/min, not weight-normalized), and dobutamine, milrinone, isoproterenol, angiotensin all 0.0. A running catecholamine with a **missing weight makes the hour un-assessable rather than silently zero** — a good pattern to preserve.

Paralytic categories here: `cisatracurium`, `rocuronium`, `vecuronium`, `atracurium`, `pancuronium` (cf. §5.1).

### 6.2 Numerator — a controlled → support transition

Per native row, with two PEEP arms:

``` python
is_ctrl     = (dev == imv_category) & mode.isin(controlled_modes)
is_supp     = mode.isin(support_modes)
is_cpap_arm = (dev == "cpap") | ps.isna() | (ps == 0)
qual_ps     = is_supp & (~is_cpap_arm) & (peep <= 8)
qual_cpap   = is_supp & ( is_cpap_arm) & (peep <= 5)
```

The CPAP arm is detected as `device_category == 'cpap'` **or** `pressure_support_set` null or zero, and **CPAP pressure is read from `peep_set`** because CLIF has no dedicated CPAP column — a documented limitation.

Episodes are maximal run-length-encoded runs of one class over **native (non-scaffold) rows only**, with the trailing row capped at 1 hour. A transition is a qualifying-support episode whose immediately preceding episode is `controlled`. The day-attribution gate is `support_min_minutes = 2`:

``` sql
SUM(CASE WHEN t.dur_min >= 2.0 THEN 1 ELSE 0 END) > 0 AS sbt_delivered
```

**Two minutes, not thirty.** The gate is there to reject charting artefacts, not to verify a clinically complete trial. `sbt_delivered_any` (any duration) and `on_spontaneous` (parked on support all day, no transition required, no PEEP gate) are the looser nested numerators.

Extubation is **not** counted as an SBT. That is important for us: counting it would make the SBT domain partly a function of liberation, which is the coupling with VFD that [Plan 3 §8.1](03_outcome_analysis.md#81-mechanical-coupling--judged-not-a-material-problem-wfp-note-1) relies on being absent.

### 6.3 Headline rate

$$p^{\mathrm{SBT}}_i = \frac{n_{\mathrm{SBT}, i}}{n_{\text{eligible transition-candidate days}, i}}$$

where transition-candidate days are eligible days **minus** days spent parked on a spontaneous mode with no transition:

``` python
"n_eligible_txcand": int((elig & ~(g["on_spontaneous"] & ~g["nb_t"])).sum())
```

The simpler `n_sbt / n_eligible` is retained as `sbt_delivered_legacy`. Excluding already-spontaneous days is right: a patient parked on pressure support all day cannot demonstrate a controlled→support transition, so counting them as a missed SBT would be wrong.

> **Open decision.** `support_min_minutes = 2` is very permissive as a measure of "an SBT happened." A 30-minute version is closer to the clinical construct and is available from the same episode table. Recommend the dashboard's 2-minute definition as primary (for comparability with published dashboard numbers) plus a 30-minute secondary, and explicitly reporting both, since a large gap between them would tell us the measure is capturing brief mode blips rather than real trials.

### Deviation for this project

Restricted to the Plan 1 cohort and the §3 scoring window; adult-only follows from the cohort.

**Three parts of the dashboard's eligibility definition are currently approximated rather than reproduced**, in `utils/domains.py::sbt_patient_days`. All three make eligibility *more permissive*, so the denominator is currently **too large** and $p^{\mathrm{SBT}}_i$ is biased **downward**. None is a design decision; all are unfinished work, tracked in `.claude/claude-todo.md`.

| Component | Dashboard | Current implementation | Effect |
|------------------|------------------|------------------|------------------|
| 12-hour controlled accrual | Waterfall scaffold hours strictly before `day_in`, i.e. cumulative since intubation | Summed native-row interval durations | Accrual is over- or under-counted depending on charting density |
| 2-hour stability window | 2 **contiguous** scaffold hours, `MAX_HOUR_GAP = 90 min` defining contiguity | 2 hours of qualifying rows, **no contiguity requirement** | Days with scattered qualifying hours wrongly count as stable |
| Norepinephrine equivalents (`ne_equiv_max_mcg_kg_min = 0.2`) | Full NEE step function, weight-normalized, with a missing weight making the hour un-assessable | **Not implemented at all** | Patients on significant vasopressors are wrongly eligible |

> **Open decision — none, but a sequencing note.** Completing these needs `standardize_dose_to_base_units` plus ASOF-merged weights from `vitals`, and the waterfall scaffold rows rather than native rows. Until then, treat $p^{\mathrm{SBT}}_i$ as provisional and **do not compare it to the dashboard validation targets in §9** — the denominators are not the same quantity. The synthetic run gave 0.59 against dashboard values of 0.25–0.45, which is the direction this bias predicts.

## 7. Domain 4 — Prone positioning ($p^{\mathrm{prone}}_i$)

**Grain: the eligible encounter, not the patient-day.** This is the only domain with a patient-level denominator, which matters for how $Q_i$ combines them (§8.2).

### 7.1 Denominator — two nested gates

**(a) ARDS cohort at** $T_0$ (`ards_cohort` in `definitions/proning.json`):

``` python
pf_cand = pf[
    (pf["device_category"] == IMV_CATEGORY) & (pf["peep_set"] >= 5)
    & (pf["fio2_set"] >= 0.4) & (pf["pf_ratio"] <= 300)
    & (pf["age_at_admission"] >= 18)
]
```

PaO₂ from `labs.lab_category == 'po2_arterial'` (`lab_value_numeric`, `lab_collect_dttm`), matched to ventilator state by **backward `merge_asof` with a 6-hour tolerance**, by `encounter_block`; $P/F$ kept only in band $[10, 1000]$. FiO₂ is a **fraction**, so `pf_max = 300` is in mmHg; percent detection (95th percentile \> 1.5 → divide by 100) runs *before* range clipping. $T_0$ is the earliest qualifying arterial gas per encounter.

Berlin imaging criteria are **not** used, because CLIF 2.1 has no structured imaging. So the denominator is severe hypoxemia on adequate support, not adjudicated ARDS, and the domain should be named accordingly in the manuscript.

`use_sf_surrogate` is **`false`** by default (`sf_max 315`, `spo2_max 97` available if enabled). So the denominator requires an arterial blood gas.

> **Open decision.** With `use_sf_surrogate = false`, units that draw fewer arterial gases have smaller and differently-selected proning denominators — and gas-drawing frequency is itself a practice pattern plausibly correlated with overall unit quality, which makes this a real confounding path into the exposure. Enabling S/F substitution widens the denominator but mixes two measurement scales. Recommend **keeping the dashboard default (`false`) as primary** and running S/F-enabled as a sensitivity analysis, while reporting arterial-gas frequency per unit as a unit-level covariate for [Model 3](03_outcome_analysis.md#6-model-3--add-unit-and-hospital-covariates).

**(b) PROSEVA-strict eligibility** (`proning_eligibility`): `pf_max 150`, `fio2_min 0.6`, `peep_min 5`, `sustained_hours 12`.

$$T_{\text{eligible}} = T_{\text{first}} + 12\text{h}$$

where $T_{\text{first}}$ is the first gas meeting the strict thresholds, and eligibility requires **another** qualifying gas at or after $T_{\text{eligible}}$. $T_{\text{eligible}}$ is exactly $T_{\text{first}} + 12$ h, **not** the confirming gas's timestamp. Intermediate non-qualifying gases during weaning do not disqualify. An extubation during the 12-hour stabilization window does:

``` python
if bool((in_win & non_imv).any()):
    result["ineligibility_reason"] = "extubation event during 12h stabilization window"
```

### 7.2 Numerator — ever proned

From the CLIF `position` table, `position_category` lowercased, values exactly `{prone, not_prone}`.

Sessions are built by **prone / not_prone bookending, not by a time gap**:

``` python
pos["is_session_start"] = (pos["is_prone"] == 1) & (pos["prev_is_prone"] == 0)
pos["is_session_end"]   = (pos["position_category"] == NOT_PRONE) & (pos["prev_is_prone"] == 1)
```

An unclosed session falls back to the last prone row (`ended_by = "end_of_record"`).

$$p^{\mathrm{prone}}_i = \frac{n_{\text{ever proned}, i}}{n_{\text{PROSEVA-eligible}, i}}$$

**The headline numerator is "ever proned," not the ≥ 16 h adherent count.** `adherent_session_hours = 16` survives only as `any_session_adherent` in the federation CSV; the dashboard retired the "Adherent ≥16h" tile segments on 2026-06-24. The dashboard's METHODS document is explicit that ever-proned is a **process floor**, because the `position` table at that site charts only proning episodes.

`awake_proned` (a session starting before $T_0$, from the COVID-era HFNC/NIV practice) is flagged and excluded from timing clocks but **still counted in ever-proned**. `time_to_prone_hours` is measured from $T_{\text{eligible}}$ to the first prone session at or after $T_0$.

> **Open decision.** `session_gap_minutes: 60` appears in `definitions/proning.json`, `config_template.json`, `METHODS.md`, and `CLAUDE.md` in the dashboard — and is **never read by any Python file**. It is dead config. We should not replicate it; flag upstream.

> **Open decision.** If a site does not populate the `position` table, this domain is **missing, not zero**. Scoring it as zero would be a serious error that systematically penalizes sites with incomplete position data. §8.2 handles this via weight renormalization, but the team should confirm the rule: recommend requiring `position_data_present` for a unit's proning domain to be estimable at all.

> **Open decision — the proning denominator may be too small to score at unit level.** This is the domain's structural weakness, and it showed up immediately on synthetic data. Proning is the only **per-encounter** domain, and its denominator passes through two nested gates (P/F ≤ 300 on FiO₂ ≥ 0.4, then P/F ≤ 150 on FiO₂ ≥ 0.6 sustained 12 h) with no S/F substitution. In a 552-patient, 7-unit synthetic run, per-unit PROSEVA-eligible denominators were **8–15 patients — every one below the minimum of 20**, so the domain was suppressed for every unit and the composite fell back to three domains everywhere.
>
> The other three domains are **patient-day** denominators and had 42–112 per unit from the same cohort, roughly an order of magnitude more. Real cohorts are larger, but the ratio between domains will persist: proning will always be the first domain to become inestimable, and for smaller units it may never be estimable.
>
> Options: (a) accept it, and rely on the §8.2 renormalization with `min_estimable_domains = 3` — which effectively means most units are scored on three domains and $w_4$ rarely applies; (b) lower `min_denominator_per_domain` for proning specifically, accepting a noisier estimate; (c) enable S/F substitution to widen the denominator (see the open decision in §7.1); (d) score proning only at `location_type` or hospital level, where denominators pool, and treat it as a coarser signal; (e) drop it from the composite and report it separately as a descriptive measure.
>
> **This needs a decision before weights are set**, because if $p^{\mathrm{prone}}$ is usually missing then $w_4$ is mostly decorative and the composite is really a three-domain score. Run the diagnostic first: per-unit PROSEVA-eligible counts on real data.

## 8. The composite quality score

### 8.1 The dashboard has no composite — this is new

Worth stating plainly: **the dashboard computes no composite score and defines no weights.** Its `scorecard/build_scorecard.py` is, in its own documentation, "a pure aggregator — it computes nothing clinical"; it validates and renders five tile slots (`["lpv", "sat", "sbt", "proning", "mob"]`, where `mob` for mobilization is a "Coming soon…" placeholder with no implementing code). The only goal line anywhere is LPV's 0.90.

So $Q_i$ is this project's own contribution and there is no upstream convention to match.

$$Q_i = w_1\, p^{\mathrm{LTVV}}_i + w_2\, p^{\mathrm{SAT}}_i + w_3\, p^{\mathrm{SBT}}_i + w_4\, p^{\mathrm{prone}}_i$$

**Weights are intentionally left unspecified.** They are read from `config/project_params.json` (`quality_score.weights`), which ships with `null` values. The notebook computes and reports all four domain proportions regardless, and computes $Q_i$ only once weights are supplied.

> **Open decision — weights.** Options: 1. **Equal weights**, $w_k = 1/4$. Transparent, no tuning, the natural default. 2. **Evidence-graded weights**, reflecting the strength of evidence behind each process. 3. **Reliability weights**, $w_k \propto$ measure reliability, down-weighting domains with small denominators (notably proning, whose denominator is per-encounter and gated by two nested P/F criteria). 4. **Data-driven weights** — first principal component of the four proportions, or weights fit to the outcome. Fitting to the outcome and then testing the $Q$–outcome association in [Plan 3](03_outcome_analysis.md) is circular and would require cross-fitting.
>
> Recommend **equal weights as primary** with option 3 as a pre-specified sensitivity analysis. Whatever is chosen must be fixed before looking at outcomes.

Each $w_k \ge 0$ with $\sum_k w_k = 1$, so $Q_i \in [0,1]$ and reads as an overall proportion of opportunities met.

> **Open decision — mixed grain.** Three domains are proportions of **patient-days**; proning is a proportion of **encounters**. A weighted average across them is a defensible summary index but not a proportion of any single well-defined denominator, and the manuscript should say so rather than implying otherwise. The alternative is to recast LTVV, SAT, and SBT at patient level (proportion of the patient's eligible days met, then averaged over patients) so all four share a patient grain. That is cleaner conceptually and makes leave-one-patient-out trivial, at the cost of no longer matching the dashboard's published numbers. Recommend reporting both and pre-specifying the dashboard-matching version as primary.

### 8.2 Missing domains

If a unit has no estimable value for a domain — denominator below the minimum, or the source table unpopulated at that site — the missing domain is **not** scored as zero. $Q_i$ is computed over the observed domains with weights renormalized:

$$Q_i = \frac{\sum_{k \in \mathcal{O}_i} w_k\, p^{(k)}_i}{\sum_{k \in \mathcal{O}_i} w_k}$$

where $\mathcal{O}_i$ is the set of estimable domains for unit $i$. Every unit's $\mathcal{O}_i$ is reported with its score, and units with too few estimable domains are excluded from the exposure.

> **Open decision.** Minimum estimable domains for a unit to receive a score — draft **3 of 4**. And `min_denominator_per_domain` — draft **20**, versus the dashboard's `small_cell_min_den = 10`, which in the dashboard is **display-only graying in the JavaScript** and is never read by its aggregation code. Note this: the dashboard's shareable `metrics_slices.csv` and tile feeds **carry raw small counts unsuppressed**, and LPV has no small-cell rule at all. If this project has a data-sharing obligation, we must enforce suppression ourselves rather than inheriting it.

### 8.3 Standardization

$$Q^{\mathrm{std}}_i = \frac{Q_i - \bar{Q}}{\mathrm{SD}(Q)}$$

so $\beta_1$ in [Plan 3](03_outcome_analysis.md) reads per 1-SD increase in unit quality. Standardization is **unweighted by unit size** — each unit counts once, since the score is a property of units, not patients.

### 8.4 Reliability adjustment

Raw proportions from small denominators are noisy, and unreliable extremes attenuate the [Plan 3](03_outcome_analysis.md) association through exposure measurement error.

> **Open decision.** Recommend fitting each domain as a hierarchical (beta-binomial or random-intercept logistic) model across units and using the **shrunken posterior mean**, reporting raw proportions alongside. This is standard in unit-level quality reporting and matters most for proning. It does induce a dependence between units' scores, which should be noted. Draft assumes raw proportions first pass, shrunken as pre-specified sensitivity.

## 9. Validation targets

The dashboard reports these headline values at two sites (`docs/portability_mimic.md`), with vocabulary matching across both with no overrides. Our implementation should reproduce numbers of this order on comparable data; a large discrepancy means a definition was mistranscribed.

| Domain | Headline definition | MIMIC | UChicago |
|------------------|------------------|------------------|------------------|
| LPV | Vt ≤ 8 mL/kg PBW, of assessable ventilated ICU patient-days | 67.5% (58,656/86,917) | 83.1% (61,305/73,739) |
| SAT | SAT performed, of eligible ventilated-sedation days | 58.9% (57,251/97,264) | 41.8% (25,277/60,429) |
| SBT | SBT delivered, of eligible transition-candidate days | 44.7% (12,846/28,735) | 25.3% (8,706/34,439) |
| Proning | Ever proned, of PROSEVA-eligible encounters | 17.0% (523/3,080) | 18.9% (350/1,854) |

Our numbers will differ legitimately because we restrict to the Plan 1 cohort and open the scoring window at time zero (§3). They should not differ by an order of magnitude, and the notebook should print this table alongside our values as a smoke test.

Note the substantial between-site spread in every domain — good news for [Plan 3](03_outcome_analysis.md), since an exposure with no variance would have no power, but also a reminder that between-site differences in documentation are a competing explanation for between-unit differences in measured quality (§8.4 of Plan 3).

## 10. Outputs

To `output/final_no_phi/` (aggregate, subject to the minimum cell size):

- `unit_quality_scores.csv` — one row per (site, `location_name`): the four proportions with their numerators and denominators, $\mathcal{O}_i$, $Q_i$, $Q^{\mathrm{std}}_i$, contributing patients, and `location_type` as `parent`.
- `domain_performance.png` — per-domain unit-level dot plot with confidence intervals, so reviewers can see which domains actually discriminate between units.
- `domain_correlation.csv` — pairwise correlations among the four proportions. **Look at this early:** if the domains are strongly correlated, the composite is nearly one-dimensional and the weights barely matter; if they are uncorrelated or negatively correlated, a single composite may hide more than it reveals, and that is itself a finding.
- `assessability_by_unit.csv` — per unit and domain, the assessable-versus-crude gap and the not-assessable share. This is the data-quality readout that tells us whether we are measuring care or charting.

To `output/intermediate_phi/` (PHI, gitignored):

- `patient_domain_flags.parquet` — per patient and per patient-day, the eligibility and performance flags for each domain. This makes the leave-one-patient-out sensitivity analysis in [Plan 3](03_outcome_analysis.md) possible, and it is the file to inspect when a unit's score looks wrong.

## 11. Implementation traps

Carried over from the dashboard's own hard-won notes plus the clifpy API. Each of these has produced a real bug.

1.  **CLIF version determines the category vocabulary.** clifpy's `DEFAULT_CLIF_VERSION = "2.1"`, which uses title case (`IMV`, `Assist Control-Volume Control`). CLIF 3.0 uses snake_case (`imv`, `acvc`, `prvc`, `ps_or_cpap`). Every mode and device constant in this document is **2.1**. Set `clif_version` explicitly in `config/config.json` and branch the vocabulary on it — do not rely on the default. `clifpy.utils.crosswalk` provides `crosswalk_table_2_1_to_3_0` and `normalize_category_value`.
2.  **Classic SOFA is hardcoded to 2.1 vocabulary.** `clifpy.utils.sofa`'s `DEVICE_RANK_DICT` and `sofa_resp` key off title-case `'IMV'`, `'NIPPV'`, `'CPAP'`, so classic SOFA will silently mis-score CLIF 3.0 data.
3.  **`position` is excluded from `create_wide_dataset`** (`supported: false` in clifpy's `wide_tables_config.yaml`). Load and join it manually; do not expect prone columns to appear in a wide dataset.
4.  **The dashboard pins `clifpy==0.4.9`** because 0.5.0 changed `*_dttm` localization and produced "cannot subtract tz-naive and tz-aware" failures across sites. We target **clifpy ≥ 2.1.0**, so datetime handling must be re-verified rather than assumed — timezone bugs here are silent and produce wrong durations, not errors.
5.  **`encounter_block` dtype.** The dashboard's shared waterfall carries it as `float64` while SAT/SBT cast `.astype("Int64").astype(str)`. A str-versus-float join silently yields zero rows. If we use stitching at all, assert row counts after every join.
6.  **Waterfall input requirements.** `process_resp_support_waterfall` expects data **already in UTC** and is row-order dependent (forward-fill plus run-length encoding), so pre-sort to a canonical total order. Prefer the bound method `RespiratorySupport.waterfall()`, which handles the UTC round-trip. Avoid `bool[pyarrow]` dtypes, which have no `cumsum` kernel on pandas 3.
7.  **DST policy must be identical across all four domains**: `ambiguous="NaT"`, `nonexistent="shift_forward"`. Adding one day to a timezone-aware timestamp is a wall-clock add, so DST days are 23- or 25-hour windows — hence the dashboard's `DAY_CAP = 1500` minutes.
8.  **LPV must use raw native rows, not the waterfall**; the scaffold rows would double-count minute-weighted intervals. SAT, SBT, and proning all use the waterfall.
9.  **Exact-case `sex_category`** in the PBW formula (§4.1), against lowercased device and mode matching everywhere else.
10. **FiO₂ units**: percent-versus-fraction detection must run before range clipping, or clipping destroys the signal the detector needs.
11. **Interior infusion segments are uncapped**, and this silently deflates the SAT rate. A segment runs from its `admin_dttm` to the next row **of the same drug**, and only the *final* segment is capped (at 24 h). So if a drug is charted sporadically, or a `stop` row is missing, one row whose next same-drug row is three days later becomes **72 hours of continuous infusion** — and that spurious segment swallows every real off-gap inside it, so no SAT hold is detected. Nothing errors; the unit's SAT rate just looks bad. We hit exactly this during development on synthetic data where the sedative changed daily: the pooled SAT rate came out at 0.15 against an intended 0.5, from a single 102-hour phantom infusion. `utils/domains.active_segments` therefore takes an `interior_cap_hours` argument (`quality_score.sat.interior_cap_hours`), defaulting to `null` to reproduce the dashboard.

> **Open decision.** Should `interior_cap_hours` be set (e.g. 24 h) rather than left at the dashboard's uncapped behaviour? Capping departs from the dashboard but is robust to sparse charting; leaving it uncapped is faithful but depends on every site reliably charting `stop` actions. **Before deciding, run the diagnostic**: distribution of infusion-segment durations per site, and the count of segments longer than 24 h. If a site has many, its SAT rate is not interpretable and capping is not optional.

## 12. Points to confirm with the dashboard author

Not implementation questions — places where we believe the dashboard has an inconsistency, so the finding should go back upstream rather than being silently worked around.

1.  **SAT's paralytic list is only `cisatracurium`**, while SBT's includes five agents (§5.1). Believed unintentional.
2.  **`session_gap_minutes` in proning is dead config** — documented in four places, read nowhere (§7.2).
3.  **Five SAT config keys are never read**: `dex_only_days`, `zero_dose_sources`, `require_resume`, `unit_attribution_anchor`, `denominator_mode`.
4.  **LPV severity code uses strict `<`/`>`; METHODS.md and README use `≤`/`≥`** (§4.8).
5.  **No age filter in SAT or SBT** (§5, Deviation) — pediatric ventilator-days enter those denominators.
6.  **Small counts are unsuppressed** in the shareable `metrics_slices.csv` and tile feeds, and LPV has no small-cell rule (§8.2).
7.  **Uncapped interior infusion segments** in the SAT hold detection (§11, item 11). Under sparse charting or a missing `stop` row this manufactures multi-day phantom infusions that mask real sedation holds and deflate the SAT rate with no error raised. This is the one finding on this list we think is a genuine correctness bug rather than a tidiness issue, and it is worth raising first.
