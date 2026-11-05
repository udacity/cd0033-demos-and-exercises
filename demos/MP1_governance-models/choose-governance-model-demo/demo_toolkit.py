"""
demo_toolkit.py — Medallion Lakehouse governance engine for Veridian Health (DEMOS).

PROVIDED FILE for instructor demos. Completely independent of the exercise toolkit
(`governance_toolkit.py` / Trailhead Provisions) and capstone (Cardinal Outfitters).

Maps Veridian Health's Medallion Lakehouse (Bronze / Silver / Gold) onto live AWS:

    Glue Data Catalog  -> Medallion zone & stewardship audit (`audit_lakehouse_catalog`,
                          `set_table_governance`, `classify_column`)
    Lake Formation     -> Healthcare persona grants (`grant_column_subset`,
                          `define_jurisdiction_filter`, `grant_filtered_rows`,
                          `tag_medallion_table`, `grant_lf_tag`, `grant_schema_only`)
    Athena (query-as)  -> `query_as_persona(persona, sql)` enforcing Lake Formation grants
    Medallion Quality  -> `run_medallion_quality()` + `medallion_slos()`
    Master Patient Idx -> `resolve_patient_mpi()` + `adjudicate_mpi_matches()`
    OpenLineage        -> `MedallionLineage` (`trace_downstream`, `trace_upstream`)
    CMS eCQM Reporting -> `run_cms_quality_report()`
    Unified Operations -> `medallion_governance_audit()`
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

import veridian_seed
from veridian_seed import LakehouseCatalog

EPOCH = veridian_seed.EPOCH


class AccessDenied(Exception):
    """Raised when a healthcare persona's Lake Formation grants deny a query."""


HEALTHCARE_PERSONAS = {
    "vh_clinical_researcher":      "arn:aws:iam::ACCOUNT:role/vh_clinical_researcher",
    "vh_eu_care_coordinator":      "arn:aws:iam::ACCOUNT:role/vh_eu_care_coordinator",
    "vh_him_steward":              "arn:aws:iam::ACCOUNT:role/vh_him_steward",
    "vh_hipaa_compliance_auditor": "arn:aws:iam::ACCOUNT:role/vh_hipaa_compliance_auditor",
}

PHI_COLUMN_NAMES = {"full_name", "mrn", "email", "phone", "member_email", "raw_full_name", "patient_email_ref"}

MEDALLION_SLOS = [
    {"table": "bronze_lab_device_calibration", "zone": "bronze", "dimension": "completeness", "column": "iso15189_grade",          "slo_target": ">= 98.0% non-null",              "steward": "diagnostics-lab@veridian.health"},
    {"table": "silver_clinical_encounter",     "zone": "silver", "dimension": "completeness", "column": "icd10_code",              "slo_target": ">= 99.0% primary ICD-10 coded",  "steward": "clinical-ops@veridian.health"},
    {"table": "silver_patient_master",         "zone": "silver", "dimension": "validity",     "column": "mrn",                     "slo_target": ">= 99.5% MRN-XXXXXX format",     "steward": "patient-identity@veridian.health"},
    {"table": "silver_patient_master",         "zone": "silver", "dimension": "validity",     "column": "email",                   "slo_target": ">= 99.5% valid email format",    "steward": "patient-identity@veridian.health"},
    {"table": "silver_patient_master",         "zone": "silver", "dimension": "validity",     "column": "phone",                   "slo_target": ">= 99.5% E.164 format",          "steward": "patient-identity@veridian.health"},
    {"table": "silver_clinical_encounter",     "zone": "silver", "dimension": "accuracy",     "column": "copay_usd",               "slo_target": ">= 99.9% non-negative USD",      "steward": "clinical-ops@veridian.health"},
    {"table": "silver_lab_result",             "zone": "silver", "dimension": "accuracy",     "column": "turnaround_min",          "slo_target": "100% in minutes (0 < min <= 240)", "steward": "diagnostics-lab@veridian.health"},
    {"table": "silver_patient_master",         "zone": "silver", "dimension": "uniqueness",   "column": "mpi_id",                  "slo_target": "100% unique MPI key",            "steward": "patient-identity@veridian.health"},
    {"table": "silver_patient_master",         "zone": "silver", "dimension": "timeliness",   "column": "enrolled_ts",             "slo_target": ">= 98.0% active within 1825d",   "steward": "patient-identity@veridian.health"},
    {"table": "silver_clinical_encounter",     "zone": "silver", "dimension": "consistency",  "column": "session_research_opt_in", "slo_target": ">= 99.0% match HIPAA auth SoR",  "steward": "clinical-ops@veridian.health"},
]


def medallion_slos() -> pd.DataFrame:
    """Return Veridian Health's Medallion Lakehouse quality SLO targets."""
    return pd.DataFrame(MEDALLION_SLOS)


def lh_backend() -> str:
    """Return 'live' if connected to the AWS Glue `veridian_lakehouse` database, else 'disconnected'."""
    try:
        import awswrangler  # noqa: F401
        import boto3
        region = os.environ.get("VERIDIAN_AWS_REGION", os.environ.get("CARDINAL_AWS_REGION", "us-east-1"))
        sess = boto3.Session(region_name=region)
        sess.client("sts").get_caller_identity()
        db = os.environ.get("VERIDIAN_GLUE_DATABASE", veridian_seed.DATABASE)
        sess.client("glue").get_database(Name=db)
        return "live"
    except Exception:
        return "disconnected"


def connect_lakehouse():
    """Return the live AWS Medallion Lakehouse engine (`AwsMedallionLakehouse`)."""
    os.environ.setdefault("VERIDIAN_LF_LIVE", "1")
    os.environ.setdefault("VERIDIAN_AWS_REGION", "us-east-1")
    try:
        from aws_backend import AwsMedallionLakehouse
        return AwsMedallionLakehouse()
    except Exception as e:
        raise RuntimeError(
            "Veridian Health AWS Cloud Lab is not connected or not seeded yet. "
            "Run the 'Step 0: Connect to your Cloud Lab' cell at the top of the demo notebook "
            "(which sets your AWS credentials and runs `setup_aws.main()`) "
            f"before running this cell. Underlying error: {e}"
        ) from e


@dataclass
class TableGrant:
    columns: list[str] | None = None
    row_filter: str | None = None


@dataclass
class RoleGrants:
    table_grants: dict[str, TableGrant] = field(default_factory=dict)
    tag_grants: set[tuple[str, str]] = field(default_factory=set)
    describe_only: bool = False


class MedallionLakehouse:
    """Base Medallion Lakehouse catalog + Lake Formation model (subclassed by AwsMedallionLakehouse)."""

    def __init__(self):
        self.tables_dfs, self.catalog = veridian_seed.build()
        self._grants: dict[str, RoleGrants] = {r: RoleGrants() for r in HEALTHCARE_PERSONAS}
        self._row_filters: dict[str, dict] = {}
        self.lineage = build_medallion_lineage()

    def query(self, sql: str) -> pd.DataFrame:
        raise RuntimeError("Direct SQL queries require a live AWS Cloud Lab connection via connect_lakehouse().")

    def tables(self) -> list[str]:
        return list(self.catalog.tables)

    def describe_table(self, table: str) -> pd.DataFrame:
        tm = self.catalog.table(table)
        return pd.DataFrame([
            {"column": c.name, "type": c.type, "zone": tm.zone,
             "sensitivity": c.sensitivity or "(untagged)",
             "description": c.description}
            for c in tm.columns
        ])

    def medallion_slos(self) -> pd.DataFrame:
        return medallion_slos()

    # ---- MP2: Medallion Catalog Audit & Remediation ------------------------- #

    def audit_lakehouse_catalog(self) -> pd.DataFrame:
        rows = []
        for name, tm in self.catalog.tables.items():
            for attr in ("steward", "sensitivity", "retention_policy"):
                if getattr(tm, attr) is None:
                    rows.append({
                        "table": name, "zone": tm.zone, "domain": tm.domain,
                        "gap_type": f"missing_{attr}", "detail": attr,
                    })
            for col in tm.columns:
                if col.sensitivity is None:
                    rows.append({
                        "table": name, "zone": tm.zone, "domain": tm.domain,
                        "gap_type": "untagged_column",
                        "detail": f"{col.name} (type {col.type})",
                    })
        return pd.DataFrame(rows)

    def semantic_conflicts(self) -> pd.DataFrame:
        return pd.DataFrame(self.catalog.semantic_conflicts)

    def set_table_governance(self, table: str, steward: str | None = None,
                             sensitivity: str | None = None,
                             retention_policy: str | None = None) -> None:
        tm = self.catalog.table(table)
        if steward is not None:
            tm.steward = steward
        if sensitivity is not None:
            tm.sensitivity = sensitivity
        if retention_policy is not None:
            tm.retention_policy = retention_policy

    def classify_column(self, table: str, column: str, sensitivity: str) -> None:
        col = self.catalog.table(table).column(column)
        if col is None:
            raise ValueError(f"table {table!r} has no column {column!r}")
        col.sensitivity = sensitivity

    # ---- MP7: Lake Formation Healthcare Persona Grants ---------------------- #

    def _cols(self, table: str) -> list[str]:
        return [c.name for c in self.catalog.table(table).columns]

    def _check_role(self, role: str) -> None:
        if role not in HEALTHCARE_PERSONAS:
            raise ValueError(f"unknown healthcare persona {role!r}; expected one of {list(HEALTHCARE_PERSONAS)}")

    def grant_column_subset(self, role: str, table: str,
                            exclude: list[str] | None = None,
                            include: list[str] | None = None) -> None:
        self._check_role(role)
        all_cols = self._cols(table)
        allowed = [c for c in all_cols if c in include] if include is not None else [
            c for c in all_cols if c not in (exclude or [])
        ]
        self._grants[role].table_grants[table] = TableGrant(columns=allowed, row_filter=None)

    def define_jurisdiction_filter(self, name: str, table: str, expr: str) -> None:
        self._row_filters[name] = {"table": table, "expr": expr}

    def grant_filtered_rows(self, role: str, table: str, filter_name: str) -> None:
        self._check_role(role)
        rf = self._row_filters[filter_name]
        g = self._grants[role].table_grants.setdefault(table, TableGrant())
        g.row_filter = rf["expr"]
        if g.columns is None:
            g.columns = self._cols(table)

    def tag_medallion_table(self, table: str, key: str, value: str) -> None:
        self.catalog.table(table).lf_tags[key] = value

    def grant_lf_tag(self, role: str, key: str, value: str) -> None:
        self._check_role(role)
        self._grants[role].tag_grants.add((key, value))

    def grant_schema_only(self, role: str) -> None:
        self._check_role(role)
        self._grants[role].describe_only = True

    def reset_grants(self) -> None:
        self._grants = {r: RoleGrants() for r in HEALTHCARE_PERSONAS}
        self._row_filters = {}
        for tm in self.catalog.tables.values():
            tm.lf_tags = {}

    def grants_summary(self) -> pd.DataFrame:
        rows = []
        for role, g in self._grants.items():
            tagged = {
                name for name, tm in self.catalog.tables.items()
                if any((k, v) in g.tag_grants for k, v in tm.lf_tags.items())
            }
            for table, tg in g.table_grants.items():
                cols = "all" if tg.columns is None or len(tg.columns) == len(self._cols(table)) else (
                    f"{len(tg.columns)} of {len(self._cols(table))}"
                )
                rows.append({"persona": role, "table": table,
                             "access": f"cols={cols}; rows={tg.row_filter or 'all'}"})
            for table in sorted(tagged - set(g.table_grants)):
                rows.append({"persona": role, "table": table, "access": "via LF-Tag (all cols/rows)"})
            if g.describe_only and not g.table_grants and not g.tag_grants:
                rows.append({"persona": role, "table": "(all)", "access": "DESCRIBE only (metadata)"})
            if not g.table_grants and not g.tag_grants and not g.describe_only:
                rows.append({"persona": role, "table": "(none)", "access": "no grants"})
        return pd.DataFrame(rows)

    def query_as_persona(self, role: str, sql: str) -> pd.DataFrame:
        self._check_role(role)
        if hasattr(self, "_query_as_live"):
            return self._query_as_live(role, sql)
        raise RuntimeError("Persona queries require a live AWS Cloud Lab connection via connect_lakehouse().")

    def _table_has_tag(self, table: str, tag_grants: set[tuple[str, str]]) -> bool:
        tm = self.catalog.table(table)
        return any((k, v) in tag_grants for k, v in tm.lf_tags.items())

    def _phi_table_governed(self, table: str) -> bool:
        tm = self.catalog.table(table)
        phi_cols = {c.name for c in tm.columns if c.sensitivity == "PHI" or c.name in PHI_COLUMN_NAMES}
        for role, g in self._grants.items():
            if role == "vh_him_steward":
                continue
            tg = g.table_grants.get(table)
            if tg is not None and tg.row_filter is None:
                granted = set(tg.columns if tg.columns is not None else self._cols(table))
                if granted & phi_cols:
                    return False
        all_tag_grants = set().union(*(g.tag_grants for g in self._grants.values()))
        if any((k, v) in all_tag_grants for k, v in tm.lf_tags.items()):
            return True
        if any(table in g.table_grants for role, g in self._grants.items() if role != "vh_him_steward"):
            return True
        return False

    # ---- MP4, MP5, MP8, MP9 wrappers ---------------------------------------- #

    def run_medallion_quality(self) -> pd.DataFrame:
        return run_medallion_quality(self.query)

    def resolve_patient_mpi(self) -> "MpiMatchResult":
        return resolve_patient_mpi(self.query)

    def run_cms_quality_report(self) -> "CmsReportResult":
        return run_cms_quality_report(self.query)

    def medallion_governance_audit(self, contracts_valid: bool = True) -> pd.DataFrame:
        return medallion_governance_audit(self, contracts_valid=contracts_valid)


# ============================================================================= #
# MP3: Medallion Data Contract Schema & Validator
# ============================================================================= #

MEDALLION_CONTRACT_SCHEMA = {
    "type": "object",
    "required": ["dataset", "medallion_zone", "domain", "steward", "columns", "governance"],
    "properties": {
        "dataset": {"type": "string"},
        "medallion_zone": {"type": "string", "enum": ["bronze", "silver", "gold"]},
        "domain": {"type": "string"},
        "steward": {"type": "string", "format": "email"},
        "version": {"type": "string"},
        "columns": {
            "type": "array", "minItems": 1,
            "items": {
                "type": "object", "required": ["name", "type"],
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "phi": {"type": "boolean"},
                },
            },
        },
        "governance": {
            "type": "object",
            "required": ["phi_columns", "retention_policy", "regulatory_regime", "quality_slos"],
            "properties": {
                "phi_columns": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                "retention_policy": {"type": "string", "pattern": r"^P\d+[YMD]$"},
                "regulatory_regime": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                "quality_slos": {
                    "type": "array", "minItems": 1,
                    "items": {
                        "type": "object", "required": ["dimension", "threshold"],
                        "properties": {
                            "dimension": {"type": "string"},
                            "threshold": {"type": "number", "minimum": 0.0, "maximum": 1.0, "exclusiveMinimum": 0.0},
                        },
                    },
                },
            },
        },
    },
}


def base_encounter_contract() -> dict:
    """Starting ungoverned Silver contract for `silver_clinical_encounter`."""
    return {
        "dataset": "silver_clinical_encounter",
        "medallion_zone": "silver",
        "domain": "Clinical Telehealth",
        "steward": "clinical-ops@veridian.health",
        "version": "1.0.0",
        "columns": [
            {"name": "encounter_id", "type": "integer"},
            {"name": "mpi_id", "type": "integer"},
            {"name": "provider_npi", "type": "string"},
            {"name": "encounter_ts", "type": "timestamp"},
            {"name": "icd10_code", "type": "string"},
            {"name": "acuity_level", "type": "string"},
            {"name": "copay_usd", "type": "double"},
            {"name": "session_research_opt_in", "type": "integer"},
        ],
    }


def validate_medallion_contract(contract: dict) -> tuple[bool, list[str]]:
    """Validate a Medallion Lakehouse contract against JSON Schema and semantic PHI/SLO rules."""
    import jsonschema
    validator = jsonschema.Draft202012Validator(MEDALLION_CONTRACT_SCHEMA)
    errors = [f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}"
              for e in sorted(validator.iter_errors(contract), key=lambda e: list(e.path))]

    cols = contract.get("columns", [])
    gov = contract.get("governance")
    if isinstance(cols, list) and isinstance(gov, dict):
        col_names = {c.get("name") for c in cols if isinstance(c, dict) and c.get("name")}
        marked_phi = {c.get("name") for c in cols if isinstance(c, dict) and c.get("phi") is True}
        phi_cols = gov.get("phi_columns")
        if isinstance(phi_cols, list):
            unknown = [c for c in phi_cols if c not in col_names]
            if unknown:
                errors.append(f"governance/phi_columns: unknown column(s) not in contract: {unknown}")
            if not marked_phi:
                errors.append("columns: at least one PHI/linkable column must be marked with col['phi'] = True")
            elif set(phi_cols) != marked_phi:
                errors.append(
                    f"governance/phi_columns: phi_columns {sorted(set(phi_cols))} must match columns marked "
                    f"col['phi']=True {sorted(marked_phi)}"
                )
    return (len(errors) == 0, errors)


# ============================================================================= #
# MP4: Medallion Six-Dimension Quality Suite
# ============================================================================= #

_MRN_RE = re.compile(r"^MRN-\d{6}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _exp(table, zone, column, etype, dimension, total, unexpected, **extra):
    pct = round(100.0 * unexpected / total, 2) if total else 0.0
    return {
        "table": table, "zone": zone, "column": column, "expectation": etype,
        "dimension": dimension, "success": unexpected == 0,
        "element_count": total, "unexpected_count": unexpected,
        "unexpected_percent": pct, **extra,
    }


def run_medallion_quality(query_fn: Callable[[str], pd.DataFrame]) -> pd.DataFrame:
    results = []

    # 1. completeness
    dev = query_fn("SELECT iso15189_grade FROM bronze_lab_device_calibration")
    dev_null = int((dev["iso15189_grade"].isna() | (dev["iso15189_grade"].fillna("") == "")).sum())
    results.append(_exp("bronze_lab_device_calibration", "bronze", "iso15189_grade",
                        "expect_column_values_to_not_be_null", "completeness", len(dev), dev_null))

    enc = query_fn("SELECT icd10_code, copay_usd FROM silver_clinical_encounter")
    icd_null = int((enc["icd10_code"].isna() | (enc["icd10_code"].fillna("") == "")).sum())
    results.append(_exp("silver_clinical_encounter", "silver", "icd10_code",
                        "expect_column_values_to_not_be_null", "completeness", len(enc), icd_null))

    # 2. validity
    pat = query_fn("SELECT mpi_id, mrn, email, phone, enrolled_ts FROM silver_patient_master")
    bad_mrn = int((~pat["mrn"].fillna("").map(lambda s: bool(_MRN_RE.match(s)))).sum())
    results.append(_exp("silver_patient_master", "silver", "mrn",
                        "expect_column_values_to_match_mrn_format", "validity", len(pat), bad_mrn))

    bad_email = int((~pat["email"].fillna("").map(lambda s: bool(_EMAIL_RE.match(s)))).sum())
    results.append(_exp("silver_patient_master", "silver", "email",
                        "expect_column_values_to_match_email_regex", "validity", len(pat), bad_email))

    bad_phone = int((~pat["phone"].fillna("").str.startswith("+")).sum())
    results.append(_exp("silver_patient_master", "silver", "phone",
                        "expect_column_values_to_match_e164", "validity", len(pat), bad_phone))

    # 3. accuracy
    neg_copay = int((enc["copay_usd"] < 0).sum())
    results.append(_exp("silver_clinical_encounter", "silver", "copay_usd",
                        "expect_column_values_to_be_non_negative", "accuracy", len(enc), neg_copay))

    labs = query_fn("SELECT turnaround_min FROM silver_lab_result")
    sec_inflated = int((labs["turnaround_min"] > 240).sum())
    results.append(_exp("silver_lab_result", "silver", "turnaround_min",
                        "expect_turnaround_minutes_within_clinical_bounds", "accuracy", len(labs), sec_inflated))

    # 4. uniqueness
    dup_mpi = int(len(pat) - pat["mpi_id"].nunique())
    results.append(_exp("silver_patient_master", "silver", "mpi_id",
                        "expect_column_values_to_be_unique", "uniqueness", len(pat), dup_mpi))

    # 5. timeliness
    ages = pd.to_datetime(pat["enrolled_ts"]).map(lambda t: (EPOCH - t).days)
    stale = int((ages > 1825).sum())
    results.append(_exp("silver_patient_master", "silver", "enrolled_ts",
                        "expect_enrollment_recency_within_5y", "timeliness", len(pat), stale))

    # 6. consistency (HIPAA research authorization vs session opt-in)
    auth = query_fn("""
        SELECT e.encounter_id,
               e.session_research_opt_in AS session_opt_in,
               p.hipaa_research_auth AS hipaa_sor
        FROM silver_clinical_encounter e
        JOIN silver_patient_master p ON e.mpi_id = p.mpi_id""")
    mism = int((auth["session_opt_in"] != auth["hipaa_sor"]).sum())
    results.append(_exp("silver_clinical_encounter", "silver", "session_research_opt_in",
                        "expect_session_opt_in_to_match_hipaa_sor", "consistency", len(auth), mism))

    return pd.DataFrame(results)


# ============================================================================= #
# MP5: Master Patient Index (MPI) Resolution
# ============================================================================= #

@dataclass
class MpiMatchResult:
    candidates: pd.DataFrame
    steward_queue: pd.DataFrame


def _norm_name(name: str) -> str:
    return " ".join(name.lower().split())


def resolve_patient_mpi(query_fn: Callable[[str], pd.DataFrame]) -> MpiMatchResult:
    pat = query_fn(
        "SELECT mpi_id, full_name, mrn, email, phone, jurisdiction, country, enrolled_ts FROM silver_patient_master"
    )
    pat = pat[pat["email"].fillna("").str.contains("@")].copy()
    pat["nkey"] = pat["full_name"].map(_norm_name)
    pat["elocal"] = pat["email"].str.split("@").str[0].str.replace(r"\d+$", "", regex=True)

    pairs = []
    for local, grp in pat.groupby("elocal"):
        if not local or len(grp) < 2:
            continue
        recs = grp.sort_values("mpi_id").to_dict("records")
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                a, b = recs[i], recs[j]
                score = 0.0
                if a["email"] == b["email"]:
                    score += 0.6
                elif a["elocal"] == b["elocal"]:
                    score += 0.35
                if a["nkey"] == b["nkey"]:
                    score += 0.4
                if a["jurisdiction"] == b["jurisdiction"]:
                    score += 0.05
                score = round(min(score, 1.0), 2)
                band = "auto-link" if score >= 0.85 else ("non-match" if score < 0.68 else "steward-review")
                pairs.append({
                    "mpi_a": int(a["mpi_id"]), "name_a": a["full_name"], "email_a": a["email"],
                    "phone_a": a["phone"], "jurisdiction_a": a["jurisdiction"], "enrolled_a": str(a["enrolled_ts"])[:10],
                    "mpi_b": int(b["mpi_id"]), "name_b": b["full_name"], "email_b": b["email"],
                    "phone_b": b["phone"], "jurisdiction_b": b["jurisdiction"], "enrolled_b": str(b["enrolled_ts"])[:10],
                    "score": score, "band": band,
                })
    pdf = pd.DataFrame(pairs).sort_values(["score", "mpi_a", "mpi_b"], ascending=[False, True, True]).reset_index(drop=True)
    queue = pdf[pdf["band"] == "steward-review"].reset_index(drop=True)
    return MpiMatchResult(candidates=pdf, steward_queue=queue)


def adjudicate_mpi_matches(
    match: MpiMatchResult,
    decisions: dict[int, str],
    survivor: str = "lowest_mpi_id",
) -> dict:
    queue = match.steward_queue
    merged = []
    rule_label = (
        "lowest mpi_id survives (Master Patient Index SoR)"
        if "lowest" in survivor.lower()
        else "earliest enrolled_ts survives"
    )
    for idx, dec in decisions.items():
        if dec != "accept":
            continue
        row = queue.loc[idx]
        keep, retire = sorted([int(row["mpi_a"]), int(row["mpi_b"])])
        merged.append({"golden_mpi_id": keep, "retired_mpi_id": retire, "survivorship": rule_label})
    return {
        "steward_queue_size": len(queue),
        "accepted_links": len(merged),
        "rejected_homonyms": sum(1 for d in decisions.values() if d == "reject"),
        "survivorship_rule": rule_label,
        "linked_pairs": pd.DataFrame(merged),
    }


# ============================================================================= #
# MP6: Medallion OpenLineage Graph
# ============================================================================= #

@dataclass
class MedallionLineage:
    edges: list[tuple[str, str]]
    jobs: dict[str, dict]

    def datasets(self) -> set[str]:
        ds = set()
        for u, d in self.edges:
            ds.add(u); ds.add(d)
        return ds

    def trace_downstream(self, dataset: str) -> list[str]:
        out, frontier = [], [dataset]
        while frontier:
            cur = frontier.pop()
            for u, d in self.edges:
                if u == cur and d not in out:
                    out.append(d); frontier.append(d)
        return out

    def trace_upstream(self, dataset: str) -> list[str]:
        out, frontier = [], [dataset]
        while frontier:
            cur = frontier.pop()
            for u, d in self.edges:
                if d == cur and u not in out:
                    out.append(u); frontier.append(u)
        return out

    def events(self) -> pd.DataFrame:
        return pd.DataFrame([
            {"job": j, "inputs": ", ".join(io["inputs"]), "outputs": ", ".join(io["outputs"])}
            for j, io in self.jobs.items()
        ])


def build_medallion_lineage() -> MedallionLineage:
    jobs = {
        "ingest_encounter_labs": {
            "inputs": ["silver_clinical_encounter", "silver_lab_result"],
            "outputs": ["gold_encounter_turnaround"],
        },
        "publish_cms_timely_care": {
            "inputs": ["gold_encounter_turnaround"],
            "outputs": ["gold_cms_timely_care"],
        },
        "build_patient_clinical_360": {
            "inputs": ["silver_patient_master", "silver_claim_billing"],
            "outputs": ["gold_patient_clinical_360"],
        },
        "export_research_cohort": {
            "inputs": ["gold_patient_clinical_360", "silver_clinical_encounter"],
            "outputs": ["gold_deidentified_research_cohort"],
        },
    }
    edges = [(i, o) for io in jobs.values() for i in io["inputs"] for o in io["outputs"]]
    return MedallionLineage(edges=edges, jobs=jobs)


# ============================================================================= #
# MP8: CMS eCQM Timely Diagnostic Care Reporting Pipeline
# ============================================================================= #

@dataclass
class CmsReportResult:
    quarterly: pd.DataFrame
    per_encounter: pd.DataFrame
    reconciliation: pd.DataFrame


def run_cms_quality_report(query_fn: Callable[[str], pd.DataFrame]) -> CmsReportResult:
    per_enc = query_fn("""
        SELECT e.encounter_id, e.encounter_ts, e.acuity_level,
               l.result_id, l.loinc_code, l.panel_name, l.turnaround_min, l.completed_ts
        FROM silver_clinical_encounter e
        JOIN silver_lab_result l ON l.encounter_id = e.encounter_id""")
    per_enc["quarter"] = pd.to_datetime(per_enc["encounter_ts"]).dt.to_period("Q").astype(str)

    quarterly = (
        per_enc.groupby("quarter")["turnaround_min"]
        .agg(disclosed_total_min="sum", disclosed_avg_min="mean", lab_panels="count")
        .round(1)
        .reset_index()
    )

    norm = per_enc.copy()
    norm["turnaround_min_norm"] = norm["turnaround_min"].where(
        norm["turnaround_min"] <= 240, norm["turnaround_min"] / 60.0
    )
    recomp = (
        norm.groupby("quarter")["turnaround_min_norm"]
        .agg(recomputed_total_min="sum", recomputed_avg_min="mean")
        .round(1)
        .reset_index()
    )
    recon = quarterly.merge(recomp, on="quarter")
    recon["delta_total_min"] = (recon["disclosed_total_min"] - recon["recomputed_total_min"]).round(1)
    recon["matches"] = recon["delta_total_min"].abs() < 0.1
    return CmsReportResult(quarterly=quarterly, per_encounter=per_enc, reconciliation=recon)


# ============================================================================= #
# MP9: Unified Medallion Governance Audit
# ============================================================================= #

def medallion_governance_audit(lh: MedallionLakehouse, contracts_valid: bool = True) -> pd.DataFrame:
    findings = []

    audit = lh.audit_lakehouse_catalog()
    for _, r in audit.iterrows():
        sev = "high" if r["gap_type"] == "untagged_column" else "medium"
        findings.append({
            "signal": "missing_metadata",
            "zone": r["zone"],
            "object": f"{r['table']}.{r['detail']}",
            "severity": sev,
            "source": "audit_lakehouse_catalog (MP2)",
        })

    covered = lh.lineage.datasets()
    for t in lh.tables():
        tm = lh.catalog.table(t)
        if t not in covered:
            findings.append({
                "signal": "missing_lineage",
                "zone": tm.zone,
                "object": t,
                "severity": "medium",
                "source": "medallion_lineage (MP6)",
            })

    q = lh.run_medallion_quality()
    for _, r in q[~q["success"]].iterrows():
        findings.append({
            "signal": "quality_violation",
            "zone": r["zone"],
            "object": f"{r['table']}.{r['column']} [{r['dimension']}]",
            "severity": "high" if r["unexpected_percent"] > 5 else "low",
            "source": "run_medallion_quality (MP4)",
        })

    if not contracts_valid:
        findings.append({
            "signal": "contract_invalid",
            "zone": "silver",
            "object": "silver_clinical_encounter contract",
            "severity": "high",
            "source": "validate_medallion_contract (MP3)",
        })

    findings.append({
        "signal": "authorization_conflict",
        "zone": "silver",
        "object": "silver_patient_master.hipaa_research_auth vs silver_clinical_encounter.session_research_opt_in",
        "severity": "high",
        "source": "semantic_conflicts (MP2)",
    })

    for t in lh.tables():
        tm = lh.catalog.table(t)
        is_phi = (tm.sensitivity == "PHI") or any(c.sensitivity == "PHI" for c in tm.columns)
        if is_phi and not lh._phi_table_governed(t):
            findings.append({
                "signal": "phi_access_gap",
                "zone": tm.zone,
                "object": f"{t} (PHI table, no Lake Formation restriction)",
                "severity": "high",
                "source": "lake_formation (MP7)",
            })

    return pd.DataFrame(findings)


def _table_in_from(sql: str) -> str | None:
    m = re.search(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)", sql, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\b(?:DESCRIBE|table_info)\s*\(?\s*([A-Za-z_][A-Za-z0-9_]*)", sql, flags=re.IGNORECASE)
    return m.group(1) if m else None


def _is_describe(sql: str) -> bool:
    s = sql.strip().lower()
    return s.startswith("describe") or s.startswith("show columns")
