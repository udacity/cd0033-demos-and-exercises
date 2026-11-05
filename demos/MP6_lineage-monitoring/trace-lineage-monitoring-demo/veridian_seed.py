"""
veridian_seed.py — Veridian Health Medallion Lakehouse synthetic seed (for DEMOS).

PROVIDED FILE for instructor demos. Uses a completely separate company, domain model,
and Medallion Lakehouse architecture (Bronze / Silver / Gold zones) from the exercises
(Trailhead Provisions) and the capstone (Cardinal Outfitters).

Company: Veridian Health (multi-jurisdiction digital telehealth & diagnostics network)
Regimes: HIPAA Privacy & Security Rules (45 CFR §164), GDPR Art. 9 (Special Category
         Health Data), and CMS eCQM (Electronic Clinical Quality Measures) reporting.
Architecture: Medallion Lakehouse on AWS (`veridian_lakehouse` Glue database, S3 Parquet
              across `bronze/`, `silver/`, and `gold/` zones, Lake Formation TBAC/cell
              filters, and Amazon Athena).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

SEED = 137
EPOCH = datetime(2025, 1, 1, 0, 0, 0)
COMPANY = "Veridian Health"
DATABASE = "veridian_lakehouse"


# ----------------------------------------------------------------------------- #
# Medallion Lakehouse Catalog Model (Glue Data Catalog structure)
# ----------------------------------------------------------------------------- #

@dataclass
class MedallionColumn:
    name: str
    type: str
    sensitivity: Optional[str] = None   # PHI | CONFIDENTIAL | PUBLIC | None(=gap)
    description: str = ""


@dataclass
class MedallionTable:
    name: str
    zone: str                           # bronze | silver | gold
    domain: str
    columns: list[MedallionColumn]
    steward: Optional[str] = None
    sensitivity: Optional[str] = None
    retention_policy: Optional[str] = None
    description: str = ""
    lf_tags: dict[str, str] = field(default_factory=dict)

    def column(self, name: str) -> Optional[MedallionColumn]:
        return next((c for c in self.columns if c.name == name), None)


@dataclass
class LakehouseCatalog:
    database: str
    tables: dict[str, MedallionTable]
    semantic_conflicts: list[dict] = field(default_factory=list)

    def table(self, name: str) -> MedallionTable:
        return self.tables[name]


# ----------------------------------------------------------------------------- #
# Synthetic clinical & operational pools
# ----------------------------------------------------------------------------- #

_FIRST = ["Elena", "Marcus", "Priya", "Jonas", "Amara", "Devon", "claire".title(), "Tariq",
          "freja".title(), "Mateo", "Nadia", "Kieran", "Zoya", "Henrik", "Celeste", "Omar",
          "Leila", "Bastien", "Mina", "Ronan"]
_LAST = ["Kowalski", "Osei", "Subramanian", "Lindholm", "Vargas", "Chen", "Al-Mansoor",
         "Dupont", "Moreau", "Takahashi", "Novak", "Mercer", "Solis", "Bergstrom", "Patel"]
_JURISDICTIONS = ["US-HIPAA", "EU-GDPR", "CA-PIPEDA"]
_JURIS_COUNTRY = {
    "US-HIPAA": ["US"],
    "EU-GDPR": ["DE", "NL", "SE", "FR"],
    "CA-PIPEDA": ["CA"],
}
_PLANS = ["medicare_advantage", "commercial_ppo", "eu_statutory", "provincial_plus"]
_ICD10 = ["J06.9", "I10", "E11.9", "F41.1", "M54.5", "K21.9"]
_ACUITY = ["routine", "urgent", "emergent", "follow_up"]
_PANELS = [
    ("24323-8", "Comprehensive Metabolic Panel"),
    ("58410-2", "Complete Blood Count"),
    ("4548-4", "HbA1c Glycated Hemoglobin"),
    ("14647-2", "Lipid Panel"),
    ("11502-2", "High-Sensitivity Troponin"),
]
_PAYERS = ["AetnaHealth", "BlueCross", "AllianzCare", "SunLifeCA", "MedicareCMS"]
_CHANNELS = ["ios_app", "web_portal", "clinic_kiosk", "partner_referral"]


def _phone(rng: random.Random, jurisdiction: str, dirty: bool = False) -> str:
    cc = {"US-HIPAA": "+1", "EU-GDPR": "+49", "CA-PIPEDA": "+1"}[jurisdiction]
    num = "".join(str(rng.randint(0, 9)) for _ in range(9))
    if dirty:
        return rng.choice(["", "000-INVALID", num])
    return f"{cc}{num}"


def build() -> tuple[dict[str, pd.DataFrame], LakehouseCatalog]:
    """Build the Veridian Health Medallion Lakehouse tables + catalog metadata."""
    rng = random.Random(SEED)

    # --- 1. Patient Identity & Intake (silver_patient_master & bronze_patient_intake) --- #
    n_patients = 240
    combos = [(f, l) for f in _FIRST for l in _LAST]
    rng.shuffle(combos)
    base = combos[:n_patients]
    patients = []
    clean_ids = []
    for mpi_id in range(1001, 1001 + n_patients):
        first, last = base[mpi_id - 1001]
        juris = rng.choices(_JURISDICTIONS, weights=[50, 30, 20])[0]
        country = rng.choice(_JURIS_COUNTRY[juris])
        dom = rng.choice(["veridianmail.org", "healthpost.io", "medinbox.net"])
        dirty_mrn = rng.random() < 0.05
        mrn = "UNASSIGNED" if dirty_mrn else f"MRN-{mpi_id:06d}"
        dirty_email = rng.random() < 0.04
        email = ("missing_email" if dirty_email else f"{first}.{last}@{dom}").lower()
        phone = _phone(rng, juris, dirty=(rng.random() < 0.04))
        plan = rng.choice(_PLANS)
        research_auth = 1 if rng.random() < 0.55 else 0
        days_ago = rng.randint(5, 600) if rng.random() > 0.04 else rng.randint(2200, 3600)
        enrolled = EPOCH - timedelta(days=days_ago, hours=rng.randint(0, 23))
        patients.append((
            mpi_id, f"{first} {last}", mrn, email, phone, juris, country,
            plan, research_auth, enrolled.isoformat()
        ))
        if not dirty_email and not dirty_mrn:
            clean_ids.append(mpi_id)

    # 6 deliberate duplicate MPI profiles (2 exact -> auto-link, 4 email/whitespace variant -> steward-review)
    dup_mpi = rng.sample(clean_ids, 6)
    next_mpi = 1001 + n_patients
    for k, src_mpi in enumerate(dup_mpi):
        src = patients[src_mpi - 1001]
        name, email = src[1], src[3]
        if k >= 2:
            lp, dom = email.split("@", 1)
            new_dom = "healthpost.io" if dom != "healthpost.io" else "veridianmail.org"
            email = f"{lp}@{new_dom}" if k % 2 == 0 else f"{lp}{rng.randint(1, 9)}@{dom}"
            if k == 4:
                name = name.replace(" ", "  ")
        patients.append((
            next_mpi, name, f"MRN-{next_mpi:06d}", email, src[4], src[5], src[6],
            rng.choice(_PLANS), src[8], src[9]
        ))
        next_mpi += 1

    # 2 deliberate homonym non-matches (same patient name + similar email local part, different jurisdiction/phone)
    src_hom = patients[0]
    patients.append((
        next_mpi, src_hom[1], f"MRN-{next_mpi:06d}",
        f"{src_hom[3].split('@')[0]}9@medinbox.net",
        "+491769988776", "EU-GDPR", "DE", "eu_statutory", 0, "2021-09-10T11:30:00"
    ))
    next_mpi += 1
    src_hom2 = patients[2]
    patients.append((
        next_mpi, src_hom2[1], f"MRN-{next_mpi:06d}",
        f"{src_hom2[3].split('@')[0]}4@veridianmail.org",
        "+16045550199", "CA-PIPEDA", "CA", "provincial_plus", 0, "2020-11-04T09:15:00"
    ))

    # Bronze intake events
    intakes = []
    for iid in range(1, 321):
        pat = rng.choice(patients[:n_patients])
        intakes.append((
            iid, pat[3], pat[1], pat[5],
            (EPOCH - timedelta(days=rng.randint(1, 365))).isoformat(),
            rng.choice(_CHANNELS),
        ))

    # --- 2. Clinical Telehealth (silver_clinical_encounter) --- #
    n_encounters = 900
    encounters = []
    for eid in range(5001, 5001 + n_encounters):
        pat = patients[rng.randint(0, n_patients - 1)]
        mpi_id = pat[0]
        ets = EPOCH - timedelta(days=rng.randint(0, 390), hours=rng.randint(0, 23))
        acuity = rng.choices(_ACUITY, weights=[50, 25, 10, 15])[0]
        icd10 = rng.choice(_ICD10)
        if rng.random() < 0.06:
            icd10 = None  # completeness gap on diagnosis code
        copay = round(rng.uniform(0, 120), 2)
        if rng.random() < 0.02:
            copay = -copay  # accuracy defect: negative copay
        # Session research opt-in disagrees with Patient Identity hipaa_research_auth ~18% of the time
        hipaa_auth = pat[8]
        session_opt_in = hipaa_auth if rng.random() > 0.18 else (1 - hipaa_auth)
        encounters.append((
            eid, mpi_id, f"NPI-{rng.randint(100, 145)}", ets.isoformat(),
            icd10, acuity, copay, session_opt_in,
        ))

    # --- 3. Diagnostics & Labs (silver_lab_result & bronze_lab_device_calibration) --- #
    devices = []
    for did in range(1, 31):
        grade = rng.choice(["ISO-A", "ISO-B", "ISO-C"])
        if rng.random() < 0.15:
            grade = None
        devices.append((
            f"DEV-{did:03d}", rng.choice(["US", "DE", "NL", "CA"]),
            grade, round(rng.uniform(18.0, 420.0), 2),
        ))

    lab_results = []
    rid = 9001
    for (eid, mpi_id, npi, ets, icd10, acuity, copay, opt_in) in encounters:
        if acuity == "follow_up" and rng.random() < 0.35:
            continue
        loinc, panel = rng.choice(_PANELS)
        # Normal turnaround in minutes is 8..95 minutes; ~3% of feeds emit SECONDS (60x inflation)
        wait_min = round(rng.uniform(8.0, 95.0), 1)
        if rng.random() < 0.03:
            wait_min = round(wait_min * 60.0, 1)  # seconds-not-minutes unit defect!
        completed_ts = (datetime.fromisoformat(ets) + timedelta(minutes=min(wait_min, 120))).isoformat()
        lab_results.append((
            rid, eid, loinc, panel, wait_min,
            1 if wait_min > 60 else 0, completed_ts,
        ))
        rid += 1

    # --- 4. Claims & Revenue Cycle (silver_claim_billing) --- #
    claims = []
    for cid in range(7001, 7001 + 650):
        enc = rng.choice(encounters)
        pat = patients[enc[1] - 1001]
        claims.append((
            cid, enc[0], pat[3],  # keys patient by email string instead of mpi_id
            rng.choice(_PAYERS), round(rng.uniform(65.0, 980.0), 2),
            rng.choices(["paid", "adjudicating", "denied"], weights=[75, 15, 10])[0],
        ))

    tables_dfs = {
        "silver_patient_master": pd.DataFrame(
            patients,
            columns=[
                "mpi_id", "full_name", "mrn", "email", "phone", "jurisdiction",
                "country", "plan_tier", "hipaa_research_auth", "enrolled_ts",
            ],
        ),
        "bronze_patient_intake": pd.DataFrame(
            intakes,
            columns=["intake_id", "member_email", "raw_full_name", "jurisdiction", "intake_ts", "channel"],
        ),
        "silver_clinical_encounter": pd.DataFrame(
            encounters,
            columns=[
                "encounter_id", "mpi_id", "provider_npi", "encounter_ts",
                "icd10_code", "acuity_level", "copay_usd", "session_research_opt_in",
            ],
        ),
        "silver_lab_result": pd.DataFrame(
            lab_results,
            columns=[
                "result_id", "encounter_id", "loinc_code", "panel_name",
                "turnaround_min", "critical_flag", "completed_ts",
            ],
        ),
        "bronze_lab_device_calibration": pd.DataFrame(
            devices,
            columns=["device_id", "facility_country", "iso15189_grade", "reagent_cost_usd"],
        ),
        "silver_claim_billing": pd.DataFrame(
            claims,
            columns=[
                "claim_id", "encounter_id", "patient_email_ref",
                "payer_type", "billed_usd", "claim_status",
            ],
        ),
    }
    return tables_dfs, _build_catalog()


def _build_catalog() -> LakehouseCatalog:
    """Veridian Health's Medallion Lakehouse Glue Catalog with deliberate governance gaps."""
    C = MedallionColumn
    tables = {
        "silver_patient_master": MedallionTable(
            "silver_patient_master", "silver", "Patient Identity & Intake",
            [C("mpi_id", "INTEGER", "PUBLIC", "Master Patient Index surrogate key"),
             C("full_name", "TEXT", "PHI", "patient legal name"),
             C("mrn", "TEXT", None, "Medical Record Number (HIPAA direct identifier)"),  # GAP: untagged PHI
             C("email", "TEXT", "PHI", "patient contact email"),
             C("phone", "TEXT", "PHI", "patient mobile phone"),
             C("jurisdiction", "TEXT", "PUBLIC", "regulatory jurisdiction (US-HIPAA | EU-GDPR | CA-PIPEDA)"),
             C("country", "TEXT", "PUBLIC", "ISO country code"),
             C("plan_tier", "TEXT", "PUBLIC", "coverage tier"),
             C("hipaa_research_auth", "INTEGER", "CONFIDENTIAL", "HIPAA/GDPR research authorization SoR"),
             C("enrolled_ts", "TEXT", "PUBLIC", "MPI enrollment timestamp")],
            steward="patient-identity@veridian.health",
            sensitivity="PHI", retention_policy="P6Y",
            description="Conformed Silver Master Patient Index (system of record for identity & HIPAA auth)."),
        "bronze_patient_intake": MedallionTable(
            "bronze_patient_intake", "bronze", "Patient Identity & Intake",
            [C("intake_id", "INTEGER", "PUBLIC"),
             C("member_email", "TEXT", "PHI", "raw intake email"),
             C("raw_full_name", "TEXT", "PHI", "unstandardized intake name"),
             C("jurisdiction", "TEXT", "PUBLIC"),
             C("intake_ts", "TEXT", "PUBLIC"),
             C("channel", "TEXT", "PUBLIC")],
            steward="patient-identity@veridian.health",
            sensitivity="PHI", retention_policy=None,                                  # GAP
            description="Raw Bronze patient intake landing table."),
        "silver_clinical_encounter": MedallionTable(
            "silver_clinical_encounter", "silver", "Clinical Telehealth",
            [C("encounter_id", "INTEGER", "PUBLIC"),
             C("mpi_id", "INTEGER", "PUBLIC", "FK to silver_patient_master"),
             C("provider_npi", "TEXT", "PUBLIC", "attending clinician NPI"),
             C("encounter_ts", "TEXT", "PUBLIC"),
             C("icd10_code", "TEXT", "CONFIDENTIAL", "primary diagnosis code (mandatory per clinical standard)"),
             C("acuity_level", "TEXT", "PUBLIC"),
             C("copay_usd", "REAL", "CONFIDENTIAL"),
             C("session_research_opt_in", "INTEGER", "CONFIDENTIAL", "telehealth session opt-in checkbox")],
            steward=None,                                                              # GAP
            sensitivity="CONFIDENTIAL", retention_policy="P6Y",
            description="Conformed Silver telehealth clinical consultations."),
        "silver_lab_result": MedallionTable(
            "silver_lab_result", "silver", "Diagnostics & Labs",
            [C("result_id", "INTEGER", "PUBLIC"),
             C("encounter_id", "INTEGER", "PUBLIC"),
             C("loinc_code", "TEXT", "PUBLIC"),
             C("panel_name", "TEXT", "PUBLIC"),
             C("turnaround_min", "REAL", "PUBLIC", "diagnostic turnaround (minutes); CMS eCQM input"),
             C("critical_flag", "INTEGER", "PUBLIC"),
             C("completed_ts", "TEXT", "PUBLIC")],
            steward="diagnostics-lab@veridian.health",
            sensitivity=None, retention_policy="P7Y",                                  # GAP
            description="Conformed Silver diagnostic lab panel results."),
        "bronze_lab_device_calibration": MedallionTable(
            "bronze_lab_device_calibration", "bronze", "Diagnostics & Labs",
            [C("device_id", "TEXT", "PUBLIC"),
             C("facility_country", "TEXT", "PUBLIC"),
             C("iso15189_grade", "TEXT", "PUBLIC", "ISO 15189 clinical lab accreditation grade"),
             C("reagent_cost_usd", "REAL", None, "negotiated vendor reagent cost")],   # GAP: untagged CONFIDENTIAL
            steward="diagnostics-lab@veridian.health",
            sensitivity="CONFIDENTIAL", retention_policy=None,                         # GAP
            description="Raw Bronze analyzer calibration and vendor reagent cost logs."),
        "silver_claim_billing": MedallionTable(
            "silver_claim_billing", "silver", "Revenue Cycle & Quality Reporting",
            [C("claim_id", "INTEGER", "PUBLIC"),
             C("encounter_id", "INTEGER", "PUBLIC"),
             C("patient_email_ref", "TEXT", None, "patient email used as billing join key"),  # GAP: untagged PHI
             C("payer_type", "TEXT", "PUBLIC"),
             C("billed_usd", "REAL", "CONFIDENTIAL"),
             C("claim_status", "TEXT", "PUBLIC")],
            steward=None, sensitivity="CONFIDENTIAL", retention_policy=None,           # GAP x2
            description="Conformed Silver payer claims billing table."),
    }
    conflicts = [
        {"concept": "patient identity key",
         "domain_a": "Patient Identity & Intake",
         "field_a": "silver_patient_master.mpi_id (INTEGER Master Patient Index)",
         "domain_b": "Revenue Cycle & Quality Reporting",
         "field_b": "silver_claim_billing.patient_email_ref (email string)",
         "impact": "No shared surrogate key; cross-domain clinical/billing joins rely on mutable email strings."},
        {"concept": "secondary-use research authorization",
         "domain_a": "Patient Identity & Intake",
         "field_a": "silver_patient_master.hipaa_research_auth",
         "domain_b": "Clinical Telehealth",
         "field_b": "silver_clinical_encounter.session_research_opt_in",
         "impact": "Session opt-in disagrees with HIPAA authorization SoR ~18% of the time; secondary-use HIPAA/GDPR Art. 9 risk."},
        {"concept": "diagnostic turnaround unit of measure",
         "domain_a": "Diagnostics & Labs",
         "field_a": "silver_lab_result.turnaround_min (minutes)",
         "domain_b": "CMS eCQM Reporting (Gold)",
         "field_b": "3% of analyzer feeds recorded in seconds (60x scale)",
         "impact": "Mixed seconds/minutes inflate CMS Timely Diagnostic Care quarterly wait-time disclosures."},
    ]
    return LakehouseCatalog(database=DATABASE, tables=tables, semantic_conflicts=conflicts)


if __name__ == "__main__":
    dfs, cat = build()
    print(f"{COMPANY} ({cat.database}) — Medallion tables, rows, and governance gaps:")
    for t, tm in cat.tables.items():
        gaps = [a for a in ("steward", "sensitivity", "retention_policy") if getattr(tm, a) is None]
        untagged = [c.name for c in tm.columns if c.sensitivity is None]
        print(f"  [{tm.zone:6}] {t:30} rows={len(dfs[t]):4d}  gaps={gaps}  untagged={untagged}")
