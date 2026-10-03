---
output:
  pdf_document: default
  html_document: default
editor_options: 
  markdown: 
    wrap: 72
---

# Analysis Plan 3 — Outcome Analysis

**Does ICU-level IMV quality explain between-unit variation in
ventilated-patient outcomes?**

Project concept — CLIF Consortium — draft Corresponding notebook:
[`code/03_outcome_analysis.py`](../code/03_outcome_analysis.py)

> **How to use this document.** This is the editable source of truth for
> the outcome analysis. The research team reviews and edits this file;
> the notebook is then updated to match. Please edit prose directly and
> leave decisions you want discussed in the **Open decisions**
> blockquotes.
>
> **Revision note (this draft):** converted from
> `CLIF_IMV_quality_concept_WFP.pdf` and updated to incorporate WFP's
> five PDF comments. Every change is tagged **[WFP note N]** so
> reviewers can see what moved. A change log is at the end.

------------------------------------------------------------------------

## 1. Aim

Quantify between-ICU variation in risk-adjusted survival and
ventilator-free days (VFD) among invasively ventilated patients, and
estimate the fraction of that variation attributable to a unit-level
summary of invasive mechanical ventilation (IMV) quality — the **CLIF
quality score**.

## 2. Setup and notation

Because units are nested in hospitals **[WFP note 4]**, indices are
three-level throughout:

- Hospitals $h = 1, \dots, H$
- ICU units $i = 1, \dots, K$, with unit $i$ nested in hospital $h(i)$.
  A unit is a distinct `location_name` within a site (see [Plan
  2](02_quality_score.md)).
- Patients $j$, nested in unit $i$.

| Quantity | Definition |
|------------------------------------|------------------------------------|
| **Cohort** | All adult patients receiving IMV for **\> 4 h** while in an ICU. Cohort construction, time zero, and the STROBE diagram are specified in [Plan 1](01_cohort_identification.md). **[WFP note 2]** |
| **Exposure** | $Q_i$, the CLIF quality score of unit $i$, standardized to mean 0, SD 1 across units. Defined in [Plan 2](02_quality_score.md). |
| **Adjustment** | $X_{hij}$, the six SOFA components (respiratory, coagulation, liver, cardiovascular, CNS, renal), taken as **worst values in the 4-hour presentation window ending at time zero** — see §3. **[WFP note 3]** |
| **Unit/hospital covariates** | $C_i$, unit- and hospital-level characteristics used in Model 3 — see §6. |
| **Outcomes** | $Y_{hij} \in \{0,1\}$, survival to hospital discharge alive. $V_{hij} \in [0, 28]$, VFD at day 28, with death $\Rightarrow V_{hij} = 0$. |

### 2.1 Exposure scale

$Q_i$ enters the models as a continuous standardized score. Because a
linear-in-$Q$ effect is an assumption and not a finding, we also report:

1.  $Q_i$ in quartiles (so a dose-response gradient is visible without a
    linearity assumption), and
2.  a spline in $Q_i$ (natural cubic, 3 knots) as a functional-form
    check.

> **Open decision.** Should $Q_i$ be standardized within the whole
> consortium (comparing a unit to all CLIF units) or within site
> (comparing a unit to its own hospital's units)? Consortium-wide
> standardization is assumed below, but it confounds unit quality with
> site-level data-capture differences. This interacts directly with
> §7.4.

## 3. Risk adjustment uses presentation values only

We therefore define the **presentation window** as the 4 hours ending at
time zero:

$$W_{hij} = [\, t^{0}_{hij} - 4\text{h},\ t^{0}_{hij} \,]$$

and take $X_{hij}$ as the worst value of each SOFA component within
$W_{hij}$. Because the window closes at time zero, every adjustment
covariate is measured at or before the moment exposure to ICU quality
begins, so it cannot be a post-treatment variable with respect to time
zero.

Two cases follow from the time-zero definition in [Plan
1](01_cohort_identification.md):

- **Intubated before ICU arrival** (e.g. 8 h of IMV in the ED): $t^0$ is
  ICU admission, so $W$ is the last 4 h *before* ICU arrival — severity
  is measured entirely free of ICU practice. This is the cleanest case.
- **Intubated in the ICU**: $t^0$ is 4 h after IMV onset, so $W$ is the
  first 4 h of IMV, during which cumulative exposure to unit practice is
  minimal but not zero.

> **Open decision.** Alternative window definitions the team may prefer
> instead: (a) `[ICU admit, ICU admit + 4h]` — "first 4 hours in the
> ICU" read literally, but for ED-intubated patients this sits *after*
> time zero and reintroduces the post-treatment problem; (b)
> `[intubation, intubation + 4h]` — anchored to IMV onset regardless of
> location. The window above was chosen because it is the only one
> guaranteed to close at or before $t^0$ for every patient. Flagging
> because the note said "first 4 hours" without naming the anchor.

> **Open decision.** Should we additionally adjust for a small set of
> pre-ICU covariates that are unambiguously not post-treatment — age,
> sex, comorbidity burden (Charlson or Elixhauser from
> `hospitalization_diagnosis`), admission source, and whether the
> patient was intubated before ICU arrival? These are cheap and
> strengthen case-mix adjustment without contamination. The draft
> assumes **yes** for age, sex, and comorbidity index; SOFA components
> alone are the concept-paper version.

## 4. Model 1 — nested unit and hospital random intercepts, case-mix adjustment only

**[WFP note 4]** A hospital-level random effect is included in **all**
models, so that between-unit variation is separated from
between-hospital variation rather than being pooled into a single unit
term.

**Survival (three-level logistic):**

$$\operatorname{logit} \Pr\!\left(Y_{hij} = 1 \mid w_h, u_i, X_{hij}\right)
= \beta_0 + w_h + u_i + \beta^{\top} X_{hij},
\qquad
w_h \sim N(0, \sigma^2_w), \quad u_i \sim N(0, \sigma^2_u)
\tag{1}$$

**VFD (three-level linear):**

$$V_{hij} = \gamma_0 + z_h + v_i + \gamma^{\top} X_{hij} + \varepsilon_{hij},
\qquad
z_h \sim N(0, \sigma^2_z), \quad v_i \sim N(0, \sigma^2_v), \quad
\varepsilon_{hij} \sim N(0, \sigma^2_\varepsilon)
\tag{2}$$

### 4.1 Unit-specific predictions

**[WFP note 5]** Rather than evaluating predictions at a single mean
covariate vector $\bar{X}$ — which under a logit link does not return
the marginal risk — we report **population-standardized** unit estimates
as the primary summary. For each unit $i$ we predict the outcome for
**every patient in the full analytic cohort** as if that patient had
been cared for in unit $i$, then average over the empirical covariate
distribution (G-computation / direct standardization):

$$\hat{p}^{\text{std}}_i = \frac{1}{N} \sum_{n=1}^{N}
\operatorname{expit}\!\left(\hat{\beta}_0 + \hat{w}_{h(i)} + \hat{u}_i + \hat{\beta}^{\top} X_n\right),
\qquad
\hat{E}^{\text{std}}\!\left[V \mid i\right] = \frac{1}{N} \sum_{n=1}^{N}
\left(\hat{\gamma}_0 + \hat{z}_{h(i)} + \hat{v}_i + \hat{\gamma}^{\top} X_n\right)
\tag{3}$$

where $\hat{u}_i, \hat{v}_i, \hat{w}_h, \hat{z}_h$ are empirical Bayes
(shrunken) estimates and the sum runs over all $N$ patients in the
cohort, not just those in unit $i$. This is the same
counterfactual-standardization logic as a survival-benefit calculation:
hold the candidate population fixed and vary only the unit assignment.

Confidence intervals for $\hat{p}^{\text{std}}_i$ come from a parametric
bootstrap over the joint posterior of the fixed effects and the
empirical Bayes random effects (default 1000 draws).

**Secondary, for interpretability only**, the "typical patient" version
at the reference covariate vector $\bar{X}$:

$$\hat{p}_i = \operatorname{expit}\!\left(\hat{\beta}_0 + \hat{w}_{h(i)} + \hat{u}_i + \hat{\beta}^{\top} \bar{X}\right),
\qquad
\hat{E}\!\left[V \mid i, \bar{X}\right] = \hat{\gamma}_0 + \hat{z}_{h(i)} + \hat{v}_i + \hat{\gamma}^{\top} \bar{X}
\tag{4}$$

> **Open decision.** For the reference patient $\bar{X}$, use
> component-wise **medians** (a realizable patient) rather than means
> (which can produce non-integer SOFA components that no patient has).
> The draft assumes medians. WFP's note also raised borrowing the
> approach from the heart-transplant survival-benefit work — the
> standardization in (3) is our reading of that approach; **please
> confirm the intended method and citation** so we describe it correctly
> in the manuscript.

### 4.2 Figure 1 — caterpillar plot

Units ranked by $\hat{p}^{\text{std}}_i$ (and, in a second panel, by
$\hat{E}^{\text{std}}[V \mid i]$) with 95% intervals, points colored by
$Q_i$ quartile. Visual test: are high-$Q$ units concentrated at the
favorable end? This is a descriptive companion to the formal test in §5,
not a substitute for it.

## 5. Model 2 — add unit-level IMV quality

$$\operatorname{logit} \Pr\!\left(Y_{hij} = 1 \mid w^{*}_h, u^{*}_i, X_{hij}, Q_i\right)
= \beta_0 + w^{*}_h + u^{*}_i + \beta_1 Q_i + \beta^{\top} X_{hij}
\tag{5}$$

$$V_{hij} = \gamma_0 + z^{*}_h + v^{*}_i + \gamma_1 Q_i + \gamma^{\top} X_{hij} + \varepsilon_{hij}
\tag{6}$$

with $u^{*}_i \sim N(0, \sigma^2_{u^*})$,
$w^{*}_h \sim N(0, \sigma^2_{w^*})$, and analogously for the VFD model.

### 5.1 Variance summaries

**Proportional change in between-unit variance** (how much of the
unit-level variance $Q_i$ accounts for):

$$\mathrm{PCV}_Y = \frac{\hat{\sigma}^2_u - \hat{\sigma}^2_{u^*}}{\hat{\sigma}^2_u},
\qquad
\mathrm{PCV}_V = \frac{\hat{\sigma}^2_v - \hat{\sigma}^2_{v^*}}{\hat{\sigma}^2_v}
\tag{7}$$

**Median odds ratio**, the median OR between two randomly chosen units
at the same covariate values:

$$\mathrm{MOR} = \exp\!\left(\sqrt{2\sigma^2}\ \Phi^{-1}(0.75)\right)
\tag{8}$$

reported for $\sigma^2 = \hat{\sigma}^2_u$ (between-unit) and
$\sigma^2 = \hat{\sigma}^2_w$ (between-hospital) separately, under
Models 1 and 2.

**Variance partition coefficients** — because the model is now
three-level, we report how the total latent-scale variance splits across
hospital, unit, and patient. Using the latent-response formulation for
the logistic model ($\pi^2/3$ for the level-1 variance):

$$\mathrm{VPC}_{\text{hosp}} = \frac{\sigma^2_w}{\sigma^2_w + \sigma^2_u + \pi^2/3},
\qquad
\mathrm{VPC}_{\text{unit}} = \frac{\sigma^2_u}{\sigma^2_w + \sigma^2_u + \pi^2/3}
\tag{9}$$

Confidence intervals for PCV and VPC come from the parametric bootstrap
in §4.1, since these are nonlinear functions of variance components.

## 6. Model 3 — add unit and hospital covariates

**[WFP note 4]** New model. Unobservable confounding cannot be resolved,
but we can control for observable structural differences between units
and hospitals, and ask whether the $Q_i$ association survives them.

$$\operatorname{logit} \Pr\!\left(Y_{hij} = 1 \mid w^{**}_h, u^{**}_i, X_{hij}, Q_i, C_i\right)
= \beta_0 + w^{**}_h + u^{**}_i + \beta_1 Q_i + \beta_2^{\top} C_i + \beta^{\top} X_{hij}
\tag{10}$$

$$V_{hij} = \gamma_0 + z^{**}_h + v^{**}_i + \gamma_1 Q_i + \gamma_2^{\top} C_i + \gamma^{\top} X_{hij} + \varepsilon_{hij}
\tag{11}$$

Candidate elements of $C_i$, all derivable from CLIF or from site
metadata:

- **Unit IMV volume** — count of cohort patients per unit per year
  (log-transformed).
- **Unit type** — medical / surgical / cardiac / neuro / mixed, from
  `location_name` mapped by each site.

> **Open decision.** Which elements of $C_i$ are actually obtainable
> across participating CLIF sites? Volume and data completeness are
> computable from the data we already have; unit type, hospital size,
> and academic status require a short site survey. If the survey is not
> feasible, Model 3 reduces to volume + completeness and we should say
> so.

> **Open decision.** With $K$ units (likely tens, not hundreds), the
> number of unit-level covariates that can be estimated alongside $Q_i$
> is small — $Q_i$ and $C_i$ compete for the same $K$ degrees of
> freedom. We should pre-specify a maximum of 4–5 unit-level terms and
> rank them by priority now, before seeing results.

### 6.1 Two identifiability constraints that follow from the hospital random effect

Both of these were found by running the pipeline on synthetic data, and
both silently produce output that looks like a result. They constrain
what Model 3 can contain.

**(a) A covariate constant within hospital cannot be estimated alongside
the hospital random intercept.** It is perfectly collinear with it. Of
the candidate covariates in §6, **hospital size and academic status are
hospital-level by definition**, so neither can enter Model 3 as written.
Unit type, unit volume, and data completeness vary between units within
a hospital and are therefore admissible.

This does not raise an error. In our synthetic run, the
variational-Bayes logistic fit returned coefficients of *exactly* `0.0`
for `hospital_beds` and `academic`, and the REML VFD fit returned
`academic = 160.7` days — a nonsense value with no standard error.
Either could be mistaken for a finding. `code/03_outcome_analysis.py`
therefore screens candidate covariates and drops any that are constant
within hospital, reporting what it dropped.

> **Open decision.** Hospital-level structural covariates are still
> worth knowing about even though they cannot go in Model 3. Options:
> (a) report them descriptively alongside the hospital random-effect
> estimates, and interpret $\hat{w}_h$ as "what hospital-level factors,
> observed or not, contribute"; (b) fit a **separate hospital-level
> model** with $\hat{w}_h$ as the outcome and the hospital covariates as
> predictors — a two-stage approach that is transparent about having
> only $H$ observations; (c) drop the hospital random effect in one
> sensitivity model specifically to estimate hospital covariates,
> accepting that unit and hospital effects are then confounded.
> Recommend (a) as primary with (b) as a secondary, given how few
> hospitals CLIF sites will contribute.

**(b) The hospital random effect absorbs all between-hospital variation
in** $Q_i$, so $\beta_1$ is identified only from within-hospital
contrasts between units. This is the direct cost of [WFP note 4], and it
needs to be quantified before $\beta_1$ is interpreted. Decompose the
exposure's variance:

$$\text{share between} = \frac{\sum_i \left(\bar{Q}_{h(i)} - \bar{Q}\right)^2}{\sum_i \left(Q_i - \bar{Q}\right)^2}$$

In the synthetic run, **47% of** $Q$'s variance was between hospitals,
leaving 53% to identify $\beta_1$. Real CLIF data may well be worse,
since practice is plausibly more similar between units of one hospital
than across hospitals. If most of $Q$'s variance is between hospitals,
then a small $\beta_1$ or $\mathrm{PCV}$ means *"little quality
variation survives the hospital adjustment"* — **not** *"quality does
not affect outcomes."* Those are very different conclusions and the
manuscript must not conflate them.

> **Open decision.** If the between-hospital share is large, consider
> decomposing the exposure explicitly into its hospital mean and its
> within-hospital deviation:
> $$Q_i = \bar{Q}_{h(i)} + \left(Q_i - \bar{Q}_{h(i)}\right)$$ and
> entering both terms, so the within-hospital association (cleanly
> identified) and the between-hospital association (confounded by
> everything else about the hospital) are reported as separate
> coefficients rather than averaged into one. This is a standard
> within-between random-effects specification and it makes the
> confounding structure visible instead of hidden. Recommend adopting it
> if the between share exceeds \~30%, and reporting the effective number
> of within-hospital unit contrasts alongside $\beta_1$ either way.

## 7. Hypotheses

- **H1.** $\beta_1 > 0$ and $\gamma_1 > 0$ — higher unit IMV quality is
  associated with higher odds of survival and more ventilator-free days.
- **H2.** $\mathrm{PCV}_Y$ and $\mathrm{PCV}_V$ are large — i.e. $Q_i$
  explains a substantial share of between-unit variation in outcomes.
- **H3** (new, from Model 3). The association in H1 persists after
  adjustment for observable unit and hospital structural covariates
  $C_i$.

Primary inference is on $\beta_1$ (survival). $\gamma_1$ and the PCV/VPC
quantities are co-primary descriptive targets. No multiplicity
adjustment is planned across the two outcomes; we will report both
regardless of direction.

## 8. Threats to validity and how this plan handles them

### 8.1 Mechanical coupling — *judged not a material problem* **[WFP note 1]**

The concern: if $Q_i$ is computed from the same patients who contribute
outcomes, domains linked to liberation (notably SBT performance) are
partly a function of VFD itself, and the $Q$–VFD association is then
partly tautological.

**Team position (WFP): not a problem.** The supporting argument is
quantitative. $Q_i$ is a unit-level mean over $n_i$ patients, so
removing any single patient moves it by $O(1/n_i)$; with the unit sizes
we expect ($n_i$ in the hundreds to thousands), an individual patient's
own contribution to their unit's score is negligible, and the domains
are *process* measures (was a SAT/SBT performed when eligible) rather
than outcome measures.

**What we will still do**, because it is nearly free:

- Report a leave-one-patient-out $Q_i^{(-j)}$ sensitivity analysis for
  the VFD outcome. If the coupling argument is right, estimates will be
  indistinguishable.
- Report a temporal-split sensitivity analysis: compute $Q_i$ from an
  earlier period and outcomes from a later period. This also breaks any
  residual coupling, and is the more persuasive design for a skeptical
  reviewer.

> **Open decision.** The temporal split costs sample size and needs a
> split date and a stability assumption (that unit quality is reasonably
> stable across the split). Is it worth running as a named secondary
> analysis, or only if a reviewer asks?

### 8.2 Cohort selection on a post-exposure variable **[WFP note 2]**

"IMV \> 24 h" conditions on surviving and remaining ventilated for a
day, excluding both early extubations and early deaths — outcomes
plausibly *caused* by unit quality. This is selection on a post-exposure
variable and it biases the $Q$–outcome association toward null (the best
units lose their best patients from the denominator).

**Change: the primary cohort is IMV \> 4 h**, not \> 24 h. Four hours is
short enough that very little quality-driven selection can occur, and it
matches the 4-hour threshold used for time zero and for the presentation
window, so the cohort, exposure clock, and adjustment window are all
anchored consistently.

Sensitivity analyses: (a) IMV \> 24 h, reproducing the original
concept-paper cohort; (b) IMV \> 0 h, i.e. any IMV in the ICU; (c) a
landmark analysis at 24 h among patients alive and ventilated at 24 h,
which makes the conditioning explicit rather than implicit.

### 8.3 Post-treatment adjustment

Resolved by the presentation-window definition in §3. Residual concern:
for patients intubated in the ICU, the window overlaps the first 4 h of
unit care. Sensitivity analysis: restrict to patients intubated *before*
ICU arrival, for whom $X$ is measured entirely pre-exposure. This is a
cleaner but smaller and differently-selected cohort.

### 8.4 Unit-level confounding **[WFP note 4]**

$Q_i$ may proxy for volume, staffing, academic status, or data
completeness across CLIF sites. Two responses: the nested hospital
random effect in all models (§4), which absorbs hospital-level
differences and prevents them from masquerading as unit effects; and
Model 3 (§6), which adjusts for observable unit and hospital covariates.

**This remains an association, not a causal decomposition.** PCV is a
variance-accounting quantity, not an estimate of a causal effect of
quality on outcomes, and we will not describe it as one. Unobservable
unit-level confounding cannot be resolved by this design.

### 8.5 VFD is not Gaussian

VFD is bounded on $[0, 28]$ and zero-inflated by death, so the linear
model in (2) is **descriptive only**. Primary VFD inference uses a
competing-risks formulation — liberation from IMV versus in-hospital
death as competing events, with a subdistribution hazard model for
liberation and a unit-level random effect. A zero-inflated or hurdle
model is the fallback if the competing-risks model will not converge
with three levels.

> **Open decision.** Competing-risks models with nested random effects
> are awkward in practice. Options: (a) subdistribution hazard with unit
> frailty only, dropping the hospital level for this outcome; (b)
> cause-specific hazards with nested random effects; (c) ordinal model
> for VFD categories. Recommend (b) as primary because nested random
> effects are the point of [WFP note 4], with (a) as sensitivity.

### 8.6 "Mean patient" ≠ average patient **[WFP note 5]**

Resolved by making population-standardized estimates (3) primary, with
the reference-patient version (4) secondary and labelled as such.

## 9. Analysis sequence

1.  Load the cohort and `hospitalization_id` list from [Plan
    1](01_cohort_identification.md).
2.  Load unit-level $Q_i$ and its four domain proportions from [Plan
    2](02_quality_score.md).
3.  Build the analytic frame: one row per patient, with `location_name`
    (unit), site/hospital, $X$ from the presentation window, and both
    outcomes.
4.  Describe: outcome rates and $Q_i$ distribution by unit; unit sizes;
    missingness in $X$.
5.  Fit Model 1; produce Figure 1 caterpillar plots and the variance
    summaries.
6.  Fit Model 2; report $\beta_1$, $\gamma_1$, PCV, MOR, VPC.
7.  Fit Model 3; report whether $\beta_1$ persists.
8.  Run the competing-risks VFD model.
9.  Run the sensitivity analyses in §8 and the exposure-scale checks in
    §2.1.

## 10. Missing data

Unit-level $Q_i$ requires a minimum denominator per domain to be
estimable; units failing it are excluded from the exposure (see [Plan
2](02_quality_score.md)) and therefore from Models 2 and 3, though they
remain in Model 1's variance estimate. This differential inclusion must
be reported in the STROBE diagram.

For patient-level $X$, the default is multiple imputation by chained
equations (10 imputations) with the outcome and unit included in the
imputation model, and a complete-case sensitivity analysis.

> **Open decision.** SOFA components in a 4-hour window will be
> substantially more missing than in a 24-hour window — that is the
> price of the [WFP note 3] change. In particular coagulation, liver,
> and renal components depend on labs that may not be drawn within 4 h.
> Options: (a) multiple imputation as above; (b) carry forward the most
> recent value from up to 24 h *before* $t^0$, which stays pre-exposure
> and is clinically standard; (c) use a reduced adjustment set of the
> components that are reliably available in 4 h (respiratory,
> cardiovascular, CNS). **Recommend (b) then (a) for what remains** —
> please confirm, since this is the most consequential downstream effect
> of narrowing the window.

## 11. Software

Mixed models in Python via `statsmodels` are limited for nested random
effects and three-level logistic models. Options, in order of
preference:

1.  **R via `lme4`/`glmmTMB`** called from the notebook (`rpy2` or a
    subprocess writing intermediate Parquet). `glmmTMB` handles nested
    random effects and zero-inflation.
2.  **`pymer4`**, a Python wrapper around `lme4`.
3.  **Bayesian**, via `numpyro` or `PyMC`, which handles nested random
    effects naturally and gives PCV/VPC intervals directly from the
    posterior without a bootstrap.

> **Open decision.** Option 3 is the cleanest fit for this analysis —
> PCV, VPC, and MOR are all nonlinear functions of variance components,
> and a posterior gives their intervals for free rather than via
> parametric bootstrap. It also sidesteps the R dependency across CLIF
> sites. Recommend Bayesian with weakly informative priors as primary.
> The notebook currently scaffolds the model-fitting step as a
> placeholder pending this decision.

------------------------------------------------------------------------

## Change log — WFP PDF comments applied to this draft

The five comments below are WFP's highlights and margin notes on
`CLIF_IMV_quality_concept_WFP.pdf`, with what changed in response.

| Note | Highlighted passage | WFP comment | Change |
|------------------|------------------|------------------|------------------|
| **1** | "Mechanical coupling: if $Q_i$ is computed from the same patients … Compute $Q_i$ leave-one-patient-out or from a prior time period." | *"not a problem IMO"* | §8.1 — downgraded from a threat to resolve before analysis to a documented team position, with the $O(1/n_i)$ justification. LOPO and temporal split retained as cheap sensitivity analyses rather than required design changes. |
| **2** | "Report sensitivity with IMV \> 0 h and landmarking." | *"fine I guess, maybe IMV \> 4 hours is better for primary analysis"* | §2, §8.2 — **primary cohort changed from IMV \> 24 h to IMV \> 4 h**, consistent with time zero in Plan 1. IMV \> 24 h demoted to sensitivity alongside IMV \> 0 h and landmarking. |
| **3** | "adjustment may absorb part of the effect" | *"that's why we only calculate these values using presentation values (i.e. first 4 hours, presumably before ICU quality kicks in)"* | §3 — **SOFA adjustment window changed from worst-in-first-24 h to worst-in-4-h-window ending at time zero**, guaranteeing pre-exposure measurement. New open decisions on the window anchor (§3) and on the resulting lab missingness (§10). |
| **4** | "Add unit/hospital covariates and a hospital level (units nested in hospitals)." | *"let's add random hospital effect to all models. we won't be able to resolve confounding from unobservables, but we can control for some unit or hospital level factors in a 3rd model"* | §2, §4, §5, §6 — notation made three-level; **hospital random intercept added to all models**; **new Model 3** with unit/hospital covariates $C_i$; VPC added (§5.1); §8.4 states plainly that unobservable confounding is not resolved. **New §6.1 documents two consequences that need team attention**: hospital-level covariates (size, academic status) become inestimable alongside the hospital random effect, and the random effect absorbs between-hospital $Q$ variance (47% in the synthetic run), so $\beta_1$ rests only on within-hospital contrasts. |
| **5** | "report standardized (population-averaged) unit estimates as well." | *"yeah I don't think this matters much, we just need to pick covariates for a 'typical patient'. we could also take the approach I used in my heart survival benefit transplant paper"* | §4.1 — **population-standardized estimates (3) made primary**, via G-computation over the full cohort (our reading of the survival-benefit approach); reference-patient estimates (4) retained as secondary with medians. Flagged for WFP to confirm the intended method and citation. |
