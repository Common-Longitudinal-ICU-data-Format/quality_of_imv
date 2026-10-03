"""Tiny synthetic CLIF tables so the notebooks run before a site is wired up.

This is a DEVELOPMENT SCAFFOLD, not a simulation. It exists so that every notebook can
be executed end to end -- and so the cohort logic can be checked against hand-built
edge cases -- without access to a real CLIF database. When a site config exists at
``config/config.json``, the notebooks load real data via clifpy instead and ignore this
module entirely.

The generated cohort deliberately includes the edge cases that
analysis_plan/01_cohort_identification.md section 3 specifies, so the time-zero logic is
exercised rather than merely executed:

* ``ED_THEN_ICU``   -- 8 h of IMV in the ED, then ICU. Time zero = ICU admission.
* ``IMV_IN_ICU``    -- intubated after ICU arrival. Time zero = IMV onset + 4 h.
* ``ED_SHORT``      -- 2 h of IMV in the ED, then ICU. Time zero = ICU admit + 2 h.
* ``SHORT_IMV``     -- 2 h of IMV total. Excluded (never reaches 4 h).
* ``NO_ICU``        -- ventilated on a ward only. Excluded (no ICU).
* ``PEDS``          -- age 12. Excluded (not adult).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Seven units across two hospitals, so the nested random effects in notebook 03 are
# actually estimable rather than degenerate.
UNIT_META = [
    # location_name, hospital_id, location_type, hospital_beds, academic
    ("MICU_A1", "HOSP_A", "medical_icu", 820, 1),
    ("MICU_A2", "HOSP_A", "medical_icu", 820, 1),
    ("SICU_A3", "HOSP_A", "surgical_icu", 820, 1),
    ("CCU_A4", "HOSP_A", "mixed_cardiothoracic_icu", 820, 1),
    ("MICU_B1", "HOSP_B", "medical_icu", 310, 0),
    ("SICU_B2", "HOSP_B", "surgical_icu", 310, 0),
    ("NSICU_B3", "HOSP_B", "mixed_neuro_icu", 310, 0),
]

UNITS = [u[0] for u in UNIT_META]
UNIT_HOSPITAL = {u[0]: u[1] for u in UNIT_META}
UNIT_TYPES = {u[0]: u[2] for u in UNIT_META}

# Per-unit adherence propensities, so the quality score has real between-unit variation
# and a true Q-outcome association exists for notebook 03 to recover.
UNIT_QUALITY = {
    "MICU_A1": dict(ltvv=0.88, sat=0.75, sbt=0.65, prone=0.50),
    "MICU_A2": dict(ltvv=0.80, sat=0.66, sbt=0.58, prone=0.42),
    "SICU_A3": dict(ltvv=0.70, sat=0.55, sbt=0.50, prone=0.34),
    "CCU_A4": dict(ltvv=0.64, sat=0.48, sbt=0.44, prone=0.30),
    "MICU_B1": dict(ltvv=0.58, sat=0.42, sbt=0.38, prone=0.26),
    "SICU_B2": dict(ltvv=0.50, sat=0.35, sbt=0.32, prone=0.21),
    "NSICU_B3": dict(ltvv=0.44, sat=0.29, sbt=0.27, prone=0.17),
}

SCENARIOS = ["ED_THEN_ICU", "IMV_IN_ICU", "ED_SHORT", "SHORT_IMV", "NO_ICU", "PEDS"]

# Scenario mix: most patients are ordinary, a few exercise each exclusion path.
SCENARIO_WEIGHTS = [0.34, 0.34, 0.12, 0.08, 0.06, 0.06]

BASE = pd.Timestamp("2024-01-01 00:00:00")
SEDATIVES = ["propofol", "fentanyl", "midazolam"]


def _sex(rng):
    # Exact case, matching CLIF 2.1 patient.sex_category and the PBW formula in
    # analysis_plan/02_quality_score.md section 4.1.
    return "Male" if rng.random() < 0.55 else "Female"


def make_demo_tables(n_hosp: int = 700, seed: int = 7) -> dict[str, pd.DataFrame]:
    """Build a dict of CLIF-shaped pandas DataFrames keyed by table name."""
    rng = np.random.default_rng(seed)

    patients, hosps, adt, resp, vitals, labs, meds, position, assess = (
        [], [], [], [], [], [], [], [], []
    )

    for k in range(n_hosp):
        hid = f"H{k:05d}"
        pid = f"P{k:05d}"
        scenario = rng.choice(SCENARIOS, p=SCENARIO_WEIGHTS)
        unit = UNITS[k % len(UNITS)]

        age = 12 if scenario == "PEDS" else int(rng.integers(19, 88))
        sex = _sex(rng)
        height = float(rng.normal(170 if sex == "Male" else 158, 9))

        adm = BASE + pd.Timedelta(hours=float(rng.integers(0, 24 * 300)))
        los_h = float(rng.integers(72, 600))
        dsc = adm + pd.Timedelta(hours=los_h)

        # Mortality rises as unit quality falls, plus a hospital-level offset, so the
        # models in notebook 03 have a real signal to recover rather than pure noise.
        q_unit = UNIT_QUALITY[unit]
        q_mean = sum(q_unit.values()) / 4.0
        hosp_offset = 0.03 if UNIT_HOSPITAL[unit] == "HOSP_B" else -0.03
        p_die = min(max(0.42 - 0.35 * q_mean + hosp_offset, 0.05), 0.65)
        died = bool(rng.random() < p_die)

        patients.append(
            {
                "patient_id": pid,
                "sex_category": sex,
                "race_category": rng.choice(["White", "Black or African American", "Asian", "Other"]),
                "ethnicity_category": rng.choice(["Non-Hispanic", "Hispanic"]),
            }
        )
        hosps.append(
            {
                "hospitalization_id": hid,
                "patient_id": pid,
                "admission_dttm": adm,
                "discharge_dttm": dsc,
                "age_at_admission": age,
                "discharge_category": "Expired" if died else "Home",
                "admission_type_category": rng.choice(["ED", "OR", "Transfer"]),
            }
        )

        # --- ADT: build an ED/ward leg then (usually) an ICU leg -------------
        if scenario == "NO_ICU":
            adt.append(
                {"hospitalization_id": hid, "in_dttm": adm, "out_dttm": dsc,
                 "location_category": "ward", "location_name": "WARD_1"}
            )
            icu_in = None
        else:
            ed_h = 10.0
            adt.append(
                {"hospitalization_id": hid, "in_dttm": adm,
                 "out_dttm": adm + pd.Timedelta(hours=ed_h),
                 "location_category": "ed", "location_name": "ED_MAIN"}
            )
            icu_in = adm + pd.Timedelta(hours=ed_h)
            icu_out = min(icu_in + pd.Timedelta(hours=float(rng.integers(48, 400))), dsc)
            adt.append(
                {"hospitalization_id": hid, "in_dttm": icu_in, "out_dttm": icu_out,
                 "location_category": "icu", "location_name": unit}
            )
            if icu_out < dsc:
                adt.append(
                    {"hospitalization_id": hid, "in_dttm": icu_out, "out_dttm": dsc,
                     "location_category": "ward", "location_name": "WARD_1"}
                )

        # --- Ventilation timeline -------------------------------------------
        # imv_start relative to admission, and total hours of IMV.
        if scenario == "ED_THEN_ICU":
            imv_start, imv_h = adm + pd.Timedelta(hours=2), float(rng.integers(30, 260))
        elif scenario == "IMV_IN_ICU":
            imv_start, imv_h = icu_in + pd.Timedelta(hours=3), float(rng.integers(30, 260))
        elif scenario == "ED_SHORT":
            imv_start, imv_h = adm + pd.Timedelta(hours=8), float(rng.integers(30, 200))
        elif scenario == "SHORT_IMV":
            imv_start, imv_h = adm + pd.Timedelta(hours=2), 2.0
        elif scenario == "NO_ICU":
            imv_start, imv_h = adm + pd.Timedelta(hours=2), float(rng.integers(10, 100))
        else:  # PEDS
            imv_start, imv_h = icu_in + pd.Timedelta(hours=3), float(rng.integers(30, 150))

        imv_end = min(imv_start + pd.Timedelta(hours=imv_h), dsc)

        p_ltvv = q_unit["ltvv"]
        p_sat = q_unit["sat"]
        p_sbt = q_unit["sbt"]
        p_prone = q_unit["prone"]

        pbw = (50.0 if sex == "Male" else 45.5) + 2.3 * (height / 2.54 - 60.0)

        # Hourly respiratory_support rows across the IMV episode.
        t, hours = imv_start, 0
        while t < imv_end:
            spont = hours > 0.7 * imv_h and rng.random() < 0.35
            mode = "Pressure Support/CPAP" if spont else rng.choice(
                ["Assist Control-Volume Control", "Pressure Control",
                 "Pressure-Regulated Volume Control", "SIMV"]
            )
            target = rng.random() < p_ltvv
            vt = pbw * (rng.uniform(5.2, 7.6) if target else rng.uniform(8.4, 11.0))
            resp.append(
                {
                    "hospitalization_id": hid,
                    "recorded_dttm": t,
                    "device_category": "IMV",
                    "mode_category": mode,
                    "tracheostomy": 0,
                    "tidal_volume_set": round(vt, 1),
                    "tidal_volume_obs": round(vt * rng.uniform(0.97, 1.03), 1),
                    "peep_set": float(rng.choice([5, 8, 10, 12])),
                    "fio2_set": float(rng.choice([0.3, 0.4, 0.5, 0.6, 0.8])),
                    "pressure_support_set": 8.0 if spont else np.nan,
                    "plateau_pressure_obs": float(rng.normal(24, 5)),
                    "resp_rate_set": float(rng.integers(12, 26)),
                }
            )
            t += pd.Timedelta(hours=1)
            hours += 1

        # Height / weight / vitals.
        vitals.append({"hospitalization_id": hid, "recorded_dttm": adm,
                       "vital_category": "height_cm", "vital_value": round(height, 1)})
        vitals.append({"hospitalization_id": hid, "recorded_dttm": adm,
                       "vital_category": "weight_kg", "vital_value": round(float(rng.normal(82, 18)), 1)})
        for h in range(0, int(min(imv_h, 240)), 4):
            ts = imv_start + pd.Timedelta(hours=h)
            vitals.append({"hospitalization_id": hid, "recorded_dttm": ts,
                           "vital_category": "spo2", "vital_value": float(rng.normal(94, 4))})
            vitals.append({"hospitalization_id": hid, "recorded_dttm": ts,
                           "vital_category": "map", "vital_value": float(rng.normal(74, 12))})

        # Labs for SOFA and P/F.
        for h in range(0, int(min(imv_h, 240)), 6):
            ts = imv_start + pd.Timedelta(hours=h)
            for cat, val in [
                ("po2_arterial", float(rng.normal(85, 28))),
                ("creatinine", float(abs(rng.normal(1.4, 0.9)))),
                ("platelet_count", float(abs(rng.normal(180, 70)))),
                ("bilirubin_total", float(abs(rng.normal(1.1, 0.9)))),
            ]:
                labs.append({"hospitalization_id": hid, "lab_result_dttm": ts,
                             "lab_collect_dttm": ts, "lab_category": cat,
                             "lab_value_numeric": val})

        # GCS for CNS SOFA.
        for h in range(0, int(min(imv_h, 240)), 8):
            assess.append({
                "hospitalization_id": hid,
                "recorded_dttm": imv_start + pd.Timedelta(hours=h),
                "assessment_category": "gcs_total",
                "numerical_value": float(rng.integers(3, 16)),
            })

        # Continuous sedation, with daily interruptions at unit-specific probability.
        n_days = max(int(imv_h // 24), 1)
        # One sedative for the whole episode. Switching drugs daily would leave each
        # drug charted in isolated daily blocks, and because interior infusion segments
        # run to the next row of the *same* drug, that manufactures multi-day spurious
        # infusions which swallow the SAT holds.
        med = str(rng.choice(SEDATIVES))
        for d in range(n_days):
            day0 = imv_start + pd.Timedelta(days=d)
            interrupt = rng.random() < p_sat
            for h in range(24):
                ts = day0 + pd.Timedelta(hours=h)
                if ts >= imv_end:
                    break
                # A 2-hour hole in the morning represents a sedation interruption.
                dose = 0.0 if (interrupt and h in (7, 8)) else float(abs(rng.normal(30, 8)))
                meds.append({
                    "hospitalization_id": hid, "admin_dttm": ts, "med_category": med,
                    "med_dose": dose, "med_dose_unit": "mcg/kg/min",
                    "mar_action_category": "stop" if dose == 0.0 else "continue",
                })
            # Norepinephrine on some days, to exercise the SBT vasopressor criterion.
            if rng.random() < 0.3:
                for h in range(0, 24, 2):
                    ts = day0 + pd.Timedelta(hours=h)
                    if ts >= imv_end:
                        break
                    meds.append({
                        "hospitalization_id": hid, "admin_dttm": ts,
                        "med_category": "norepinephrine",
                        "med_dose": float(abs(rng.normal(0.08, 0.05))),
                        "med_dose_unit": "mcg/kg/min", "mar_action_category": "continue",
                    })
            # An SBT appears as a spontaneous-mode block following controlled ventilation.
            if rng.random() < p_sbt:
                ts = day0 + pd.Timedelta(hours=10)
                if ts < imv_end:
                    resp.append({
                        "hospitalization_id": hid, "recorded_dttm": ts,
                        "device_category": "IMV", "mode_category": "Pressure Support/CPAP",
                        "tracheostomy": 0, "tidal_volume_set": np.nan,
                        "tidal_volume_obs": round(pbw * rng.uniform(6, 9), 1),
                        "peep_set": 5.0, "fio2_set": 0.4, "pressure_support_set": 8.0,
                        "plateau_pressure_obs": np.nan, "resp_rate_set": np.nan,
                    })

        # Position: prone episodes for some patients.
        if rng.random() < p_prone:
            pstart = imv_start + pd.Timedelta(hours=float(rng.integers(12, 48)))
            if pstart < imv_end:
                position.append({"hospitalization_id": hid, "recorded_dttm": pstart,
                                 "position_category": "prone"})
                position.append({
                    "hospitalization_id": hid,
                    "recorded_dttm": min(pstart + pd.Timedelta(hours=18), imv_end),
                    "position_category": "not_prone",
                })
        else:
            position.append({"hospitalization_id": hid,
                             "recorded_dttm": imv_start + pd.Timedelta(hours=6),
                             "position_category": "not_prone"})

    return {
        "patient": pd.DataFrame(patients),
        "hospitalization": pd.DataFrame(hosps),
        "adt": pd.DataFrame(adt),
        "respiratory_support": pd.DataFrame(resp).sort_values(
            ["hospitalization_id", "recorded_dttm"]
        ).reset_index(drop=True),
        "vitals": pd.DataFrame(vitals),
        "labs": pd.DataFrame(labs),
        "medication_admin_continuous": pd.DataFrame(meds),
        "position": pd.DataFrame(position),
        "patient_assessments": pd.DataFrame(assess),
        # Not a CLIF table: site-supplied unit metadata for Model 3 in notebook 03.
        # The real-data equivalent is config/unit_metadata_template.csv.
        "unit_metadata": pd.DataFrame(
            [
                {"location_name": n, "hospital_id": h, "location_type": t,
                 "hospital_beds": b, "academic": a}
                for n, h, t, b, a in UNIT_META
            ]
        ),
    }
