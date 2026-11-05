"""
governance_toolkit.py — the provided governance engine for Trailhead Provisions &
Cardinal Outfitters.

PROVIDED FILE. Students call into this from the notebook; they do not edit it.

Maps directly onto the AWS governance stack:

    Glue Data Catalog  -> Catalog metadata + catalog_audit() / set_table_metadata / tag_column
    Lake Formation     -> grant_columns / create_row_filter / grant_rows /
                          assign_tag / grant_by_tag / grant_describe_only / reset
    Athena (query-as)  -> query_as(persona, sql), which ENFORCES the persona's grants
    Great Expectations -> run_quality_suite()  (GE-shaped validation results)
    OpenLineage        -> Lineage events + trace_downstream / trace_upstream / simulate_breach
    Reporting pipeline -> run_sustainability_report()

LIVE AWS ENFORCEMENT
--------------------
`make_catalog()` connects to live AWS (Glue Data Catalog + Lake Formation + Amazon Athena)
via `AwsGovernedCatalog` with no silent local fallback. If the AWS Cloud Lab is not
connected or seeded yet, `make_catalog()` stops with a clear error message instructing
the learner to run the "Step 0: Connect to your Cloud Lab" cell (`setup_aws.py`).
"""
from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

import pandas as pd

import seed_data
from seed_data import Catalog, TableMeta

EPOCH = seed_data.EPOCH


# ============================================================================= #
# Exceptions
# ============================================================================= #

class AccessDenied(Exception):
    """Raised when a persona's Lake Formation grants do not permit a query.

    Mirrors what Athena / Glue returns when Lake Formation refuses access.
    """


# ============================================================================= #
# Personas (the four platform roles). Under live AWS, ACCOUNT is replaced with
# the active AWS account ID.
# ============================================================================= #

PERSONAS = {
    "co_marketing_analyst": "arn:aws:iam::ACCOUNT:role/co_marketing_analyst",
    "co_cs_rep":            "arn:aws:iam::ACCOUNT:role/co_cs_rep",
    "co_data_steward":      "arn:aws:iam::ACCOUNT:role/co_data_steward",
    "co_auditor":           "arn:aws:iam::ACCOUNT:role/co_auditor",
}

PII_COLUMN_NAMES = {"full_name", "email", "phone", "cust_ref"}

CONTRACT_SLOS = [
    {"table": "product",             "dimension": "completeness", "column": "category",             "slo_target": ">= 99.0% non-null",       "owner": "inventory-fulfillment@trailhead.example"},
    {"table": "product",             "dimension": "completeness", "column": "sustainability_class", "slo_target": ">= 99.0% non-null",       "owner": "inventory-fulfillment@trailhead.example"},
    {"table": "customer",            "dimension": "validity",     "column": "email",                "slo_target": ">= 99.5% valid format",   "owner": "customer-identity@trailhead.example"},
    {"table": "customer",            "dimension": "validity",     "column": "phone",                "slo_target": ">= 99.5% E.164 format",   "owner": "customer-identity@trailhead.example"},
    {"table": "orders",              "dimension": "accuracy",     "column": "amount",               "slo_target": ">= 99.9% non-negative",   "owner": "orders-team@trailhead.example"},
    {"table": "shipment",            "dimension": "accuracy",     "column": "carbon_kg",            "slo_target": "100% in kg (0 < kg <= 100)", "owner": "inventory-fulfillment@trailhead.example"},
    {"table": "customer",            "dimension": "uniqueness",   "column": "customer_id",          "slo_target": "100% unique",             "owner": "customer-identity@trailhead.example"},
    {"table": "customer",            "dimension": "timeliness",   "column": "created_ts",           "slo_target": ">= 98.0% within 1095d",   "owner": "customer-identity@trailhead.example"},
    {"table": "campaign_membership", "dimension": "consistency",  "column": "mkt_consent",          "slo_target": ">= 99.0% match loyalty SoR", "owner": "marketing@trailhead.example"},
]


def contract_slos() -> pd.DataFrame:
    """Return the platform's target data-contract quality SLOs per table and dimension."""
    return pd.DataFrame(CONTRACT_SLOS)


def lf_backend() -> str:
    """Return 'live' if a real AWS Glue / Lake Formation / Athena path is connected, else 'local'."""
    if os.environ.get("CARDINAL_LF_LIVE") == "0":
        return "local"
    try:
        import awswrangler  # noqa: F401
        import boto3
        region = os.environ.get("CARDINAL_AWS_REGION", "us-east-1")
        sess = boto3.Session(region_name=region)
        sess.client("sts").get_caller_identity()
        db = os.environ.get("CARDINAL_GLUE_DATABASE", seed_data._build_catalog().database)
        sess.client("glue").get_database(Name=db)
        return "live"
    except Exception:
        return "local"


def make_catalog(db_path: str = "trailhead.db"):
    """Return the live AWS governance engine (`AwsGovernedCatalog`).

    Fails loudly if the AWS Cloud Lab is not connected or the Glue database has not been
    seeded yet, instructing the learner to run the Step 0 setup cell (`setup_aws.py`).
    """
    if os.environ.get("CARDINAL_LF_LIVE") == "0":
        return GovernedCatalog(db_path)

    os.environ.setdefault("CARDINAL_LF_LIVE", "1")
    os.environ.setdefault("CARDINAL_AWS_REGION", "us-east-1")
    try:
        from aws_backend import AwsGovernedCatalog
        return AwsGovernedCatalog(db_path)
    except Exception as e:
        raise RuntimeError(
            "AWS Cloud Lab is not connected or not seeded yet. "
            "Run the 'Step 0: Connect to your Cloud Lab' cell at the top of the notebook "
            "(which sets your Vocareum AWS credentials and runs `setup_aws.main()`) "
            f"before running this cell. Underlying error: {e}"
        ) from e


# ============================================================================= #
# Grant model
# ============================================================================= #

@dataclass
class TableGrant:
    columns: list[str] | None = None     # None == all columns; [] / subset == column-level
    row_filter: str | None = None        # SQL boolean expr applied as WHERE


@dataclass
class RoleGrants:
    table_grants: dict[str, TableGrant] = field(default_factory=dict)
    tag_grants: set[tuple[str, str]] = field(default_factory=set)   # {(key, value)}
    describe_only: bool = False


# ============================================================================= #
# GovernedCatalog
# ============================================================================= #

class GovernedCatalog:
    """Base catalog + Lake Formation model (subclassed by AwsGovernedCatalog for live AWS)."""

    def __init__(self, db_path: str = ":memory:"):
        self.conn, self.catalog = seed_data.build(":memory:")
        self.conn.row_factory = sqlite3.Row
        self._grants: dict[str, RoleGrants] = {r: RoleGrants() for r in PERSONAS}
        self._row_filters: dict[str, dict] = {}   # name -> {table, expr}
        self.lineage = build_lineage()

    # ---- read helpers ------------------------------------------------------- #

    def query(self, sql: str) -> pd.DataFrame:
        """Unrestricted query (admin context). Overridden on AwsGovernedCatalog to query Athena."""
        return pd.read_sql_query(sql, self.conn)

    def tables(self) -> list[str]:
        return list(self.catalog.tables)

    def describe(self, table: str) -> pd.DataFrame:
        """Schema + classification for a table (the 'metadata-only' view)."""
        tm = self.catalog.table(table)
        return pd.DataFrame(
            [{"column": c.name, "type": c.type,
              "classification": c.classification or "(untagged)",
              "description": c.description} for c in tm.columns])

    def contract_slos(self) -> pd.DataFrame:
        """Return the platform's contract quality SLO targets."""
        return contract_slos()

    # ---- Step 2: metadata reconciliation ------------------------------------ #

    def catalog_audit(self) -> pd.DataFrame:
        """Return one row per governance gap found in the catalog."""
        rows = []
        for name, tm in self.catalog.tables.items():
            for attr in ("owner", "classification", "retention"):
                if getattr(tm, attr) is None:
                    rows.append({"table": name, "domain": tm.domain,
                                 "gap_type": f"missing_{attr}", "detail": attr})
            for col in tm.columns:
                if col.classification is None:
                    rows.append({"table": name, "domain": tm.domain,
                                 "gap_type": "untagged_column",
                                 "detail": f"{col.name} (type {col.type})"})
        return pd.DataFrame(rows)

    def semantic_conflicts(self) -> pd.DataFrame:
        return pd.DataFrame(self.catalog.semantic_conflicts)

    def set_table_metadata(self, table: str, owner: str | None = None,
                           classification: str | None = None,
                           retention: str | None = None) -> None:
        """Write table-level governance metadata to the catalog (Step 2 remediation)."""
        tm = self.catalog.table(table)
        if owner is not None:
            tm.owner = owner
        if classification is not None:
            tm.classification = classification
        if retention is not None:
            tm.retention = retention

    def tag_column(self, table: str, column: str, classification: str) -> None:
        """Set a column's classification in the catalog (Step 2 PII tagging)."""
        col = self.catalog.table(table).column(column)
        if col is None:
            raise ValueError(f"table {table!r} has no column {column!r}")
        col.classification = classification

    # ---- Step 7: Lake Formation grants -------------------------------------- #

    def _cols(self, table: str) -> list[str]:
        return [c.name for c in self.catalog.table(table).columns]

    def grant_columns(self, role: str, table: str,
                      exclude: list[str] | None = None,
                      include: list[str] | None = None) -> None:
        """Column-level grant. Specify columns to exclude (deny) or include (allow)."""
        self._check_role(role)
        all_cols = self._cols(table)
        if include is not None:
            allowed = [c for c in all_cols if c in include]
        else:
            allowed = [c for c in all_cols if c not in (exclude or [])]
        g = self._grants[role].table_grants.get(table)
        if g is None:
            self._grants[role].table_grants[table] = TableGrant(columns=allowed, row_filter=None)
        elif g.row_filter is not None:
            # Union semantics: adding an unrestricted column grant alongside a row filter
            # widens columns to the union and lifts the row restriction if all columns are granted
            existing = set(g.columns or [])
            g.columns = [c for c in all_cols if c in (existing | set(allowed))]
            g.row_filter = None
        else:
            existing = set(g.columns or [])
            g.columns = [c for c in all_cols if c in (existing | set(allowed))] if existing else allowed

    def create_row_filter(self, name: str, table: str, expr: str) -> None:
        """Define a named data-cell filter (a row predicate) on a table."""
        self._row_filters[name] = {"table": table, "expr": expr}

    def grant_rows(self, role: str, table: str, filter_name: str) -> None:
        """Grant a role SELECT on a table through a previously defined row filter."""
        self._check_role(role)
        rf = self._row_filters[filter_name]
        if rf["table"] != table:
            raise ValueError(f"filter {filter_name!r} is defined on {rf['table']}, not {table}")
        existing = self._grants[role].table_grants.get(table)
        if existing is not None and existing.row_filter is None and existing.columns == self._cols(table):
            # Full table SELECT grant already exists; union keeps full access
            return
        g = self._grants[role].table_grants.setdefault(table, TableGrant())
        g.row_filter = rf["expr"]
        if g.columns is None:
            g.columns = self._cols(table)

    def assign_tag(self, table: str, key: str, value: str) -> None:
        """Associate an LF-Tag (key=value) with a table."""
        self.catalog.table(table).lf_tags[key] = value

    def grant_by_tag(self, role: str, key: str, value: str) -> None:
        """Tag-based (LF-TBAC) grant: role gets full access to all tables carrying key=value."""
        self._check_role(role)
        self._grants[role].tag_grants.add((key, value))

    def grant_describe_only(self, role: str) -> None:
        """Metadata-only grant: schema/classification visible, SELECT on data denied."""
        self._check_role(role)
        self._grants[role].describe_only = True

    def revoke_all(self, role: str) -> None:
        self._check_role(role)
        self._grants[role] = RoleGrants()

    def reset(self) -> None:
        """Re-baseline Lake Formation: drop all grants, tags, and filters."""
        self._grants = {r: RoleGrants() for r in PERSONAS}
        self._row_filters = {}
        for tm in self.catalog.tables.values():
            tm.lf_tags = {}

    def grants_summary(self) -> pd.DataFrame:
        """Human-readable view of what every persona can currently see (union of grants)."""
        rows = []
        for role, g in self._grants.items():
            tagged = self._tables_for_tags(g.tag_grants)
            seen = set()
            for table, tg in g.table_grants.items():
                seen.add(table)
                if table in tagged:
                    rows.append({"role": role, "table": table, "access": "via LF-Tag (all cols/rows)"})
                else:
                    cols = "all" if tg.columns is None or len(tg.columns) == len(self._cols(table)) \
                        else f"{len(tg.columns)} of {len(self._cols(table))}"
                    rows.append({"role": role, "table": table,
                                 "access": f"cols={cols}; rows={tg.row_filter or 'all'}"})
            for table in sorted(tagged - seen):
                rows.append({"role": role, "table": table, "access": "via LF-Tag (all cols/rows)"})
            if g.tag_grants and not tagged:
                tag_str = ", ".join(f"{k}={v}" for k, v in sorted(g.tag_grants))
                rows.append({"role": role, "table": "(no table carries tag yet)",
                             "access": f"via LF-Tag ({tag_str}) — 0 tables matched"})
            if g.describe_only and not g.table_grants and not g.tag_grants:
                rows.append({"role": role, "table": "(all)", "access": "DESCRIBE only (no rows)"})
            elif g.describe_only:
                rows.append({"role": role, "table": "(all)", "access": "DESCRIBE on all tables"})
            if not g.table_grants and not g.tag_grants and not g.describe_only:
                rows.append({"role": role, "table": "(none)", "access": "no grants"})
        return pd.DataFrame(rows)

    # ---- query-as-persona --------------------------------------------------- #

    def query_as(self, role: str, sql: str) -> pd.DataFrame:
        """Run `sql` as `role`, enforcing that role's Lake Formation grants.

        On `AwsGovernedCatalog` (live AWS), executes strictly against live AWS (STS assume-role
        + Glue/Athena) and NEVER falls back to local SQLite on failure.
        """
        self._check_role(role)
        if type(self).__name__ != "GovernedCatalog" or os.environ.get("CARDINAL_LF_LIVE") == "1":
            if hasattr(self, "_query_as_live") and type(self).__name__ != "GovernedCatalog":
                return self._query_as_live(role, sql)
        return self._query_as_local(role, sql)

    def _query_as_local(self, role: str, sql: str) -> pd.DataFrame:
        g = self._grants[role]
        table = _table_in_from(sql)
        if _is_describe(sql):
            if table is None:
                raise AccessDenied("metadata query did not name a table")
            tg = g.table_grants.get(table)
            via_tag = self._table_has_tag(table, g.tag_grants)
            if not (g.describe_only or tg is not None or via_tag):
                raise AccessDenied(f"{role} has no Lake Formation grant (DESCRIBE or SELECT) on '{table}'")
            return self.describe(table)

        if table is None:
            raise AccessDenied("could not determine target table; single-table SELECT/DESCRIBE required")

        tg = g.table_grants.get(table)
        via_tag = self._table_has_tag(table, g.tag_grants)
        if tg is None and not via_tag:
            if g.describe_only:
                raise AccessDenied(f"{role} has metadata-only access; SELECT on '{table}' denied")
            raise AccessDenied(f"{role} has no Lake Formation SELECT grant on '{table}'")

        # Union semantics: a tag grant (or full table grant) wins over a narrower table grant or describe_only
        if via_tag:
            allowed_cols, row_filter = self._cols(table), None
        else:
            allowed_cols = tg.columns if tg.columns is not None else self._cols(table)
            row_filter = tg.row_filter

        view = f"gv__{role}__{table}"
        col_sql = ", ".join(allowed_cols)
        where = f" WHERE {row_filter}" if row_filter else ""
        self.conn.execute(f"DROP VIEW IF EXISTS {view}")
        self.conn.execute(f"CREATE TEMP VIEW {view} AS SELECT {col_sql} FROM {table}{where}")
        rewritten = re.sub(rf"\bFROM\s+{re.escape(table)}\b", f"FROM {view}", sql,
                           flags=re.IGNORECASE)
        try:
            return pd.read_sql_query(rewritten, self.conn)
        except Exception as e:
            msg = str(e).lower()
            if "no such column" in msg or "no column" in msg:
                raise AccessDenied(f"{role} requested a column not permitted on '{table}' "
                                   f"(column-level deny)") from None
            raise

    # ---- internals ---------------------------------------------------------- #

    def _check_role(self, role: str) -> None:
        if role not in PERSONAS:
            raise ValueError(f"unknown persona {role!r}; expected one of {list(PERSONAS)}")

    def _tables_for_tags(self, tag_grants: set[tuple[str, str]]) -> set[str]:
        return {name for name, tm in self.catalog.tables.items()
                if any((k, v) in tag_grants for k, v in tm.lf_tags.items())}

    def _table_has_tag(self, table: str, tag_grants: set[tuple[str, str]]) -> bool:
        tm = self.catalog.table(table)
        return any((k, v) in tag_grants for k, v in tm.lf_tags.items())

    def _table_access_governed(self, table: str) -> bool:
        """True if `table` is governed in Lake Formation:
        1. The table carries an LF-Tag (e.g. governed=true) that matches a persona's tag grant
           (or has an explicit scoped table grant), AND
        2. No non-steward persona holds an unmasked table grant that exposes PII columns on `table`.
        """
        tm = self.catalog.table(table)
        pii_cols = {c.name for c in tm.columns if c.classification == "PII" or c.name in PII_COLUMN_NAMES}

        # Check that no non-steward persona has a direct table grant exposing PII columns without a row filter
        for role, g in self._grants.items():
            if role == "co_data_steward":
                continue
            tg = g.table_grants.get(table)
            if tg is not None and tg.row_filter is None:
                granted_cols = set(tg.columns if tg.columns is not None else self._cols(table))
                if granted_cols & pii_cols:
                    return False

        # Must have a tag on the table that is actively granted via grant_by_tag to a steward/persona
        all_tag_grants = set().union(*(g.tag_grants for g in self._grants.values()))
        if any((k, v) in all_tag_grants for k, v in tm.lf_tags.items()):
            return True

        # Or have explicit least-privilege table grants configured (with PII masked or row-filtered)
        if any(table in g.table_grants for role, g in self._grants.items() if role != "co_data_steward"):
            return True

        return False

    # ---- Step 4: quality ---------------------------------------------------- #

    def run_quality_suite(self) -> pd.DataFrame:
        return run_quality_suite(self.query)

    # ---- Step 5: master data / stewardship ---------------------------------- #

    def resolve_customers(self) -> "MatchResult":
        return resolve_customers(self.query)

    # ---- Step 8: cross-domain reporting ------------------------------------- #

    def run_sustainability_report(self) -> "ReportResult":
        return run_sustainability_report(self.query)

    # ---- Step 9: governance audit ------------------------------------------- #

    def governance_audit(self, contracts_valid: bool | None = None) -> pd.DataFrame:
        return governance_audit(self, contracts_valid=contracts_valid)


# ============================================================================= #
# SQL parsing helpers
# ============================================================================= #

def _table_in_from(sql: str) -> str | None:
    m = re.search(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)", sql, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\b(?:DESCRIBE|table_info)\s*\(?\s*([A-Za-z_][A-Za-z0-9_]*)",
                  sql, flags=re.IGNORECASE)
    return m.group(1) if m else None


def _is_describe(sql: str) -> bool:
    s = sql.strip().lower()
    return s.startswith("describe") or s.startswith("pragma") or s.startswith("show columns")


def _make_df_runner(conn_or_query) -> Callable[[str], pd.DataFrame]:
    if callable(conn_or_query):
        return conn_or_query
    return lambda q: pd.read_sql_query(q, conn_or_query)


# ============================================================================= #
# Step 4: quality suite (Great-Expectations-shaped results, six dimensions)
# ============================================================================= #

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _expectation(table, column, etype, dimension, total, unexpected, **extra):
    pct = round(100.0 * unexpected / total, 2) if total else 0.0
    return {"table": table, "column": column, "expectation_type": etype,
            "dimension": dimension, "success": unexpected == 0,
            "element_count": total, "unexpected_count": unexpected,
            "unexpected_percent": pct, **extra}


def run_quality_suite(conn_or_query) -> pd.DataFrame:
    """Run expectation-style checks across the six data-quality dimensions.

    Accepts either a callable `gc.query` (Athena / live AWS) or a DB connection.
    """
    df = _make_df_runner(conn_or_query)
    results = []

    # completeness
    prod = df("SELECT category, sustainability_class FROM product")
    cat_null = int((prod["category"].isna() | (prod["category"].fillna("") == "")).sum())
    sus_null = int((prod["sustainability_class"].isna() | (prod["sustainability_class"].fillna("") == "")).sum())
    results.append(_expectation("product", "category", "expect_column_values_to_not_be_null",
                                "completeness", len(prod), cat_null))
    results.append(_expectation("product", "sustainability_class",
                                "expect_column_values_to_not_be_null", "completeness",
                                len(prod), sus_null))

    # validity
    cust = df("SELECT email, phone FROM customer")
    bad_email = int((~cust["email"].fillna("").map(lambda s: bool(_EMAIL_RE.match(s)))).sum())
    results.append(_expectation("customer", "email", "expect_column_values_to_match_regex",
                                "validity", len(cust), bad_email))
    bad_phone = int((~cust["phone"].fillna("").str.startswith("+")).sum())
    results.append(_expectation("customer", "phone", "expect_column_values_to_match_regex",
                                "validity", len(cust), bad_phone))

    # accuracy
    orders = df("SELECT amount FROM orders")
    neg = int((orders["amount"] < 0).sum())
    results.append(_expectation("orders", "amount", "expect_column_values_to_be_between",
                                "accuracy", len(orders), neg, min_value=0))
    ship = df("SELECT carbon_kg FROM shipment")
    implausible = int((ship["carbon_kg"] > 100).sum())   # kg should be small; grams slice >100
    results.append(_expectation("shipment", "carbon_kg", "expect_column_values_to_be_between",
                                "accuracy", len(ship), implausible, max_value=100))

    # uniqueness
    ids = df("SELECT customer_id FROM customer")
    dup_ids = int(len(ids) - ids["customer_id"].nunique())
    results.append(_expectation("customer", "customer_id", "expect_column_values_to_be_unique",
                                "uniqueness", len(ids), dup_ids))

    # timeliness
    created = df("SELECT created_ts FROM customer")
    ages = pd.to_datetime(created["created_ts"]).map(lambda t: (EPOCH - t).days)
    stale = int((ages > 1095).sum())   # older than 3 years
    results.append(_expectation("customer", "created_ts", "expect_recency_within_days",
                                "timeliness", len(created), stale, threshold_days=1095))

    # consistency (cross-domain: loyalty consent vs marketing consent)
    # Filter to valid emails and count per campaign_membership row so 'n/a' emails do not
    # cause a Cartesian join explosion; report unresolvable 'n/a' memberships separately.
    consent = df("""
        SELECT m.membership_id,
               m.mkt_consent AS marketing,
               MIN(c.marketing_consent) AS loyalty
        FROM campaign_membership m
        JOIN customer c ON m.cust_ref = c.email
        WHERE m.cust_ref LIKE '%@%' AND c.email LIKE '%@%'
        GROUP BY m.membership_id, m.mkt_consent""")
    unres_df = df("SELECT COUNT(*) AS n FROM campaign_membership WHERE cust_ref NOT LIKE '%@%'")
    unresolvable = int(unres_df["n"].iloc[0]) if len(unres_df) else 0
    mism = int((consent["loyalty"] != consent["marketing"]).sum())
    results.append(_expectation("campaign_membership", "mkt_consent",
                                "expect_consent_to_match_system_of_record", "consistency",
                                len(consent), mism, unresolvable_count=unresolvable))

    return pd.DataFrame(results)


# ============================================================================= #
# Step 5: master data resolution / stewardship
# ============================================================================= #

@dataclass
class MatchResult:
    pairs: pd.DataFrame          # candidate pairs with score + band (auto/ambiguous/reject)
    ambiguous: pd.DataFrame      # the subset needing steward adjudication


def _name_key(name: str) -> str:
    return " ".join(name.lower().split())


def resolve_customers(conn_or_query) -> MatchResult:
    """Block + score candidate duplicate customers; flag the ambiguous band for stewards."""
    df = _make_df_runner(conn_or_query)
    cust = df(
        "SELECT customer_id, full_name, email, phone, region, country, created_ts FROM customer"
    )
    cust = cust[cust["email"].fillna("").str.contains("@")].copy()
    cust["nkey"] = cust["full_name"].map(_name_key)
    cust["elocal"] = cust["email"].str.split("@").str[0].str.replace(r"\d+$", "", regex=True)

    pairs = []
    by_local = cust.groupby("elocal")
    for local, grp in by_local:
        if not local or len(grp) < 2:
            continue
        recs = grp.sort_values("customer_id").to_dict("records")
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
                elif set(a["nkey"].split()) & set(b["nkey"].split()):
                    score += 0.2
                if a["region"] == b["region"]:
                    score += 0.05
                score = round(min(score, 1.0), 2)
                band = "auto-merge" if score >= 0.85 else ("reject" if score < 0.66 else "ambiguous")
                pairs.append({
                    "id_a": int(a["customer_id"]),
                    "name_a": a["full_name"],
                    "email_a": a["email"],
                    "phone_a": a["phone"],
                    "country_a": a["country"],
                    "created_a": str(a["created_ts"])[:10],
                    "id_b": int(b["customer_id"]),
                    "name_b": b["full_name"],
                    "email_b": b["email"],
                    "phone_b": b["phone"],
                    "country_b": b["country"],
                    "created_b": str(b["created_ts"])[:10],
                    "score": score,
                    "band": band,
                })
    pdf = pd.DataFrame(pairs).sort_values(["score", "id_a", "id_b"], ascending=[False, True, True]).reset_index(drop=True)
    amb = pdf[pdf["band"] == "ambiguous"].reset_index(drop=True)
    return MatchResult(pairs=pdf, ambiguous=amb)


def apply_adjudications(
    match: MatchResult,
    decisions: dict[int, str],
    survivor: str = "lowest_id",
) -> dict:
    """Apply steward accept/reject decisions to the ambiguous pairs using `survivor`.

    decisions: {row_index_in_match.ambiguous: 'accept'|'reject'}.
    survivor: survivorship rule name or description:
      - 'lowest_id' (or string containing 'lowest' / 'loyalty'): lower customer_id wins (loyalty system of record)
      - 'highest_id' (or 'newest_id' / 'most_recent'): higher customer_id wins
      - 'earliest_created': record with the earlier created_ts wins
    """
    amb = match.ambiguous
    merged = []
    rule_lower = (survivor or "lowest_id").strip().lower()
    if rule_lower in ("lowest_id", "lowest", "loyalty"):
        rule_label = "lowest customer_id wins (loyalty system of record)"
    elif rule_lower in ("earliest_created", "oldest_created", "earliest"):
        rule_label = "earliest created_ts wins (loyalty system of record)"
    elif rule_lower in ("highest_id", "newest_id", "most_recent"):
        rule_label = "highest customer_id wins (most recent registration)"
    else:
        rule_label = survivor

    for idx, decision in decisions.items():
        if decision != "accept":
            continue
        row = amb.loc[idx]
        if "highest" in rule_lower or "newest" in rule_lower or "recent" in rule_lower:
            keep, drop = sorted([int(row["id_a"]), int(row["id_b"])], reverse=True)
        elif "earliest" in rule_lower or "oldest" in rule_lower:
            if str(row.get("created_a", "")) <= str(row.get("created_b", "")):
                keep, drop = int(row["id_a"]), int(row["id_b"])
            else:
                keep, drop = int(row["id_b"]), int(row["id_a"])
        else:
            keep, drop = sorted([int(row["id_a"]), int(row["id_b"])])
        merged.append({"golden_id": keep, "merged_id": drop, "survivorship": rule_label})
    accepted = len(merged)
    return {"ambiguous_pairs": len(amb), "accepted_merges": accepted,
            "rejected": sum(1 for d in decisions.values() if d == "reject"),
            "survivorship_rule": rule_label,
            "golden_records_after": "merged " + str(accepted) + " duplicate(s)",
            "merges": pd.DataFrame(merged)}


# ============================================================================= #
# Lineage (OpenLineage-shaped) — Step 6 & Step 8
# ============================================================================= #

@dataclass
class Lineage:
    edges: list[tuple[str, str]]                 # (upstream_dataset, downstream_dataset)
    jobs: dict[str, dict]                        # job -> {inputs, outputs}

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

    def simulate_breach(self, dataset: str) -> dict:
        """A change/incident at `dataset`: report everything downstream that is impacted."""
        impacted = self.trace_downstream(dataset)
        return {"origin": dataset, "impacted_downstream": impacted,
                "impacted_count": len(impacted)}

    def to_mermaid(self) -> str:
        lines = ["graph LR"]
        for u, d in self.edges:
            lines.append(f"    {u.replace('.', '_')}[{u}] --> {d.replace('.', '_')}[{d}]")
        return "\n".join(lines)

    def events(self) -> pd.DataFrame:
        rows = []
        for job, io in self.jobs.items():
            rows.append({"job": job, "inputs": ", ".join(io["inputs"]),
                         "outputs": ", ".join(io["outputs"])})
        return pd.DataFrame(rows)


def build_lineage() -> Lineage:
    """The pre-instrumented pipeline lineage for Trailhead Provisions / Cardinal Outfitters."""
    jobs = {
        "build_order_carbon": {"inputs": ["orders", "shipment"],
                               "outputs": ["order_carbon"]},
        "build_quarterly_sustainability": {
            "inputs": ["order_carbon"],
            "outputs": ["quarterly_sustainability"]},
        "build_customer_360": {"inputs": ["customer", "campaign_membership"],
                               "outputs": ["customer_360"]},
        "build_marketing_audience": {"inputs": ["customer_360", "orders"],
                                     "outputs": ["marketing_audience"]},
    }
    edges = []
    for io in jobs.values():
        for i in io["inputs"]:
            for o in io["outputs"]:
                edges.append((i, o))
    return Lineage(edges=edges, jobs=jobs)


# ============================================================================= #
# Step 8: cross-domain sustainability reporting pipeline
# ============================================================================= #

@dataclass
class ReportResult:
    quarterly: pd.DataFrame        # the disclosed figures
    per_order: pd.DataFrame        # per-order carbon (the traceable detail)
    reconciliation: pd.DataFrame   # disclosed vs recomputed-from-source (finds the unit defect)


def run_sustainability_report(conn_or_query) -> ReportResult:
    """Compute the CSRD quarterly carbon disclosure from orders + shipments."""
    df = _make_df_runner(conn_or_query)
    per_order = df("""
        SELECT o.order_id, o.order_ts, s.shipment_id, s.ship_ts, s.carbon_kg
        FROM orders o JOIN shipment s ON s.order_id = o.order_id
        WHERE o.status != 'cancelled'""")
    per_order["quarter"] = pd.to_datetime(per_order["order_ts"]).dt.to_period("Q").astype(str)

    # "disclosed" figure sums carbon_kg as-is (i.e. trusting the source column blindly)
    quarterly = (per_order.groupby("quarter")["carbon_kg"].sum()
                 .round(1).reset_index().rename(columns={"carbon_kg": "disclosed_carbon_kg"}))

    # recompute defensively: values >100 are the grams-slice; normalize to kg
    norm = per_order.copy()
    norm["carbon_kg_norm"] = norm["carbon_kg"].where(norm["carbon_kg"] <= 100,
                                                     norm["carbon_kg"] / 1000.0)
    recomputed = (norm.groupby("quarter")["carbon_kg_norm"].sum()
                  .round(1).reset_index().rename(columns={"carbon_kg_norm": "recomputed_carbon_kg"}))
    recon = quarterly.merge(recomputed, on="quarter")
    recon["delta_kg"] = (recon["disclosed_carbon_kg"] - recon["recomputed_carbon_kg"]).round(1)
    recon["matches"] = recon["delta_kg"].abs() < 0.05
    return ReportResult(quarterly=quarterly, per_order=per_order, reconciliation=recon)


# ============================================================================= #
# Step 9: governance operations audit
# ============================================================================= #

def governance_audit(gc: GovernedCatalog, contracts_valid: bool | None = None) -> pd.DataFrame:
    """Scan the platform for governance drift; one row per finding with severity + source."""
    findings = []

    # 1. catalog tag gaps (from MP2 surface; on AwsGovernedCatalog this also syncs live Glue & LF)
    audit = gc.catalog_audit()
    for _, r in audit.iterrows():
        sev = "high" if r["gap_type"] == "untagged_column" else "medium"
        findings.append({"signal": "missing_metadata", "object": f"{r['table']}.{r['detail']}",
                         "severity": sev, "source": "catalog_audit (MP2)"})

    # 2. datasets with no lineage coverage (declared catalog tables absent from lineage)
    covered = gc.lineage.datasets()
    for t in gc.tables():
        if t not in covered:
            findings.append({"signal": "missing_lineage", "object": t, "severity": "medium",
                             "source": "lineage (MP6)"})

    # 3. failed quality expectations (from MP4 surface)
    q = gc.run_quality_suite()
    for _, r in q[~q["success"]].iterrows():
        findings.append({"signal": "quality_violation",
                         "object": f"{r['table']}.{r['column']} [{r['dimension']}]",
                         "severity": "high" if r["unexpected_percent"] > 5 else "low",
                         "source": "quality_suite (MP4)"})

    # 4. contract validity (from MP3)
    if contracts_valid is False:
        findings.append({"signal": "contract_invalid", "object": "orders data contract",
                         "severity": "high", "source": "contract validator (MP3)"})

    # 5. consent conflict (the cross-domain semantic conflict, surfaced as a standing risk)
    findings.append({"signal": "consent_conflict",
                     "object": "customer.marketing_consent vs campaign_membership.mkt_consent",
                     "severity": "high", "source": "semantic_conflicts (MP2)"})

    # 6. access-control gaps: any PII-bearing table with no valid Lake Formation governance.
    for t in gc.tables():
        tm = gc.catalog.table(t)
        is_pii = (tm.classification == "PII") or any(c.classification == "PII" for c in tm.columns)
        if is_pii and not gc._table_access_governed(t):
            findings.append({"signal": "access_control_gap",
                             "object": f"{t} (PII table, no Lake Formation restriction)",
                             "severity": "high", "source": "lake formation (MP7)"})

    return pd.DataFrame(findings)


# ============================================================================= #
# Step 7: access-control verification (the provided verification cell)
# ============================================================================= #

def verify_step7(gc: GovernedCatalog, table: str = "customer") -> pd.DataFrame:
    """Query the governed table as each persona and assert the intended end-state.

    On live AWS, errors surface directly as FAIL ('live query failed: ...') rather than
    falling back to a local copy. Includes a `backend` column showing which engine answered.
    """
    if hasattr(gc, "_sync_from_aws"):
        gc._sync_from_aws()

    active_backend = "live (AWS Lake Formation + Athena)" if type(gc).__name__ == "AwsGovernedCatalog" else "local"
    all_cols = set(gc._cols(table))
    pii_cols = {"full_name", "email", "phone"} & all_cols
    expected_analyst_cols = all_cols - pii_cols
    rows = []

    def record(persona, check, passed, detail):
        rows.append({
            "persona": persona,
            "check": check,
            "result": "PASS" if passed else "FAIL",
            "backend": active_backend,
            "detail": detail,
        })

    # 1. marketing analyst: sees all non-PII columns (6 cols), and NO PII columns (full_name, email, phone)
    try:
        df = gc.query_as("co_marketing_analyst", f"SELECT * FROM {table} LIMIT 20")
        got_cols = set(df.columns)
        masked = (got_cols == expected_analyst_cols) and len(df) > 0
        record("co_marketing_analyst", "PII columns masked (full_name, email, phone)", masked,
               f"columns={list(df.columns)}")
    except AccessDenied as e:
        record("co_marketing_analyst", "PII columns masked (full_name, email, phone)", False, f"denied: {e}")
    except Exception as e:
        record("co_marketing_analyst", "PII columns masked (full_name, email, phone)", False, f"live query failed: {e}")

    # 2. cs_rep: all 9 columns visible, and ONLY region='EU' rows (62 in seed)
    try:
        df = gc.query_as("co_cs_rep", f"SELECT * FROM {table} LIMIT 1000")
        got_cols = set(df.columns)
        eu_only = (
            len(df) == 62
            and got_cols == all_cols
            and (df["region"] == "EU").all()
        )
        record("co_cs_rep", "row filter region='EU' (all cols, 62 EU rows)", eu_only,
               f"cols={len(df.columns)}/{len(all_cols)}, regions={sorted(df['region'].unique())}, rows={len(df)}")
    except AccessDenied as e:
        record("co_cs_rep", "row filter region='EU' (all cols, 62 EU rows)", False, f"denied: {e}")
    except Exception as e:
        record("co_cs_rep", "row filter region='EU' (all cols, 62 EU rows)", False, f"live query failed: {e}")

    # 3. steward: granted via LF-Tag (governed=true on customer, NO direct table grant), full cols & rows
    try:
        df = gc.query_as("co_data_steward", f"SELECT * FROM {table} LIMIT 1000")
        g_steward = gc._grants["co_data_steward"]
        tm = gc.catalog.table(table)
        has_tag_on_table = tm.lf_tags.get("governed") == "true"
        has_tag_grant = ("governed", "true") in g_steward.tag_grants
        no_direct_table_grant = table not in g_steward.table_grants
        full_cols = set(df.columns) == all_cols and len(df) > 62
        passed_steward = has_tag_on_table and has_tag_grant and no_direct_table_grant and full_cols
        record(
            "co_data_steward",
            "tag grant (governed=true) = full access",
            passed_steward,
            f"table_tagged={has_tag_on_table}, tag_grant={has_tag_grant}, "
            f"no_direct_grant={no_direct_table_grant}, cols={len(df.columns)}, rows={len(df)}",
        )
    except AccessDenied as e:
        record("co_data_steward", "tag grant (governed=true) = full access", False, f"denied: {e}")
    except Exception as e:
        record("co_data_steward", "tag grant (governed=true) = full access", False, f"live query failed: {e}")

    # 4. auditor: DESCRIBE works (via explicit grant_describe_only), SELECT denied
    describe_ok = False
    select_denied = False
    err_detail = ""
    try:
        meta = gc.query_as("co_auditor", f"DESCRIBE {table}")
        describe_ok = len(meta) > 0 and gc._grants["co_auditor"].describe_only
    except AccessDenied as e:
        describe_ok = False
        err_detail = f"describe denied: {e}"
    except Exception as e:
        describe_ok = False
        err_detail = f"live query failed: {e}"

    try:
        gc.query_as("co_auditor", f"SELECT * FROM {table} LIMIT 1")
        select_denied = False
    except AccessDenied:
        select_denied = True
    except Exception as e:
        select_denied = False
        err_detail = f"{err_detail}; select error: {e}".strip("; ")

    detail_msg = f"describe_ok={describe_ok}, select_denied={select_denied}"
    if err_detail:
        detail_msg += f" ({err_detail})"
    record("co_auditor", "metadata-only (DESCRIBE ok, SELECT denied)",
           describe_ok and select_denied, detail_msg)

    return pd.DataFrame(rows)


# ============================================================================= #
# Contract validation (Step 3)
# ============================================================================= #

CONTRACT_SCHEMA = {
    "type": "object",
    "required": ["name", "domain", "owner", "columns", "governance"],
    "properties": {
        "name": {"type": "string"},
        "domain": {"type": "string"},
        "owner": {"type": "string", "format": "email"},
        "version": {"type": "string"},
        "columns": {
            "type": "array", "minItems": 1,
            "items": {"type": "object", "required": ["name", "type"],
                      "properties": {"name": {"type": "string"}, "type": {"type": "string"},
                                     "pii": {"type": "boolean"}}}},
        "governance": {
            "type": "object",
            "required": ["pii_tags", "retention", "quality_slos"],
            "properties": {
                "pii_tags": {"type": "array", "minItems": 1, "items": {"type": "string"}},
                "retention": {"type": "string", "pattern": r"^P\d+[YMD]$"},
                "quality_slos": {
                    "type": "array", "minItems": 1,
                    "items": {"type": "object", "required": ["dimension", "threshold"],
                              "properties": {"dimension": {"type": "string"},
                                             "threshold": {"type": "number",
                                                           "minimum": 0.0,
                                                           "maximum": 1.0,
                                                           "exclusiveMinimum": 0.0}}}}}},
    },
}


def validate_contract(contract: dict) -> tuple[bool, list[str]]:
    """Validate a data contract against the governance schema and semantic PII/SLO rules."""
    import jsonschema
    validator = jsonschema.Draft202012Validator(CONTRACT_SCHEMA)
    errors = [f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}"
              for e in sorted(validator.iter_errors(contract), key=lambda e: list(e.path))]

    # Semantic cross-checks for columns, pii_tags, and quality_slos thresholds
    cols = contract.get("columns", [])
    gov = contract.get("governance")
    if isinstance(cols, list) and isinstance(gov, dict):
        col_names = {c.get("name") for c in cols if isinstance(c, dict) and c.get("name")}
        marked_pii = {c.get("name") for c in cols if isinstance(c, dict) and c.get("pii") is True}
        pii_tags = gov.get("pii_tags")
        if isinstance(pii_tags, list):
            unknown = [t for t in pii_tags if t not in col_names]
            if unknown:
                errors.append(f"governance/pii_tags: unknown column(s) not in contract: {unknown}")
            if not marked_pii:
                errors.append("columns: at least one PII column must be marked with col['pii'] = True")
            elif set(pii_tags) != marked_pii:
                errors.append(
                    f"governance/pii_tags: pii_tags {sorted(set(pii_tags))} must match columns marked "
                    f"col['pii']=True {sorted(marked_pii)}"
                )
        slos = gov.get("quality_slos")
        if isinstance(slos, list):
            for idx, slo in enumerate(slos):
                if isinstance(slo, dict) and isinstance(slo.get("threshold"), (int, float)):
                    th = float(slo["threshold"])
                    if not (0.0 < th <= 1.0):
                        errors.append(f"governance/quality_slos/{idx}/threshold: {th} must be between 0 and 1 (exclusive of 0)")

    return (len(errors) == 0, errors)


def base_contract() -> dict:
    """A minimal, NON-governed contract for the orders data product (the starting point)."""
    return {
        "name": "orders",
        "domain": "E-commerce Orders",
        "owner": "orders-team@trailhead.example",
        "version": "1.0.0",
        "columns": [
            {"name": "order_id", "type": "integer"},
            {"name": "customer_id", "type": "integer"},
            {"name": "order_ts", "type": "timestamp"},
            {"name": "status", "type": "string"},
            {"name": "amount", "type": "double"},
            {"name": "currency", "type": "string"},
        ],
        # NOTE: no "governance" block yet — the student adds it in Step 3.
    }


if __name__ == "__main__":
    gc = GovernedCatalog(":memory:")
    print("AUDIT gaps:", len(gc.catalog_audit()))
    q = gc.run_quality_suite()
    print("QUALITY failing:", int((~q["success"]).sum()), "of", len(q))
    print("CONSENT mismatch %:", q.loc[q["column"] == "mkt_consent", "unexpected_percent"].iloc[0])
    print("LINEAGE upstream of quarterly_sustainability:", gc.lineage.trace_upstream("quarterly_sustainability"))
    m = gc.resolve_customers()
    print("MDM ambiguous pairs:", len(m.ambiguous))
    rep = gc.run_sustainability_report()
    print("REPORT quarters:", len(rep.quarterly),
          "| reconciliation mismatches:", int((~rep.reconciliation["matches"]).sum()))
    ok, errs = validate_contract(base_contract())
    print("CONTRACT base valid?", ok, "| errors:", len(errs))
    print("GOV AUDIT findings:", len(gc.governance_audit(contracts_valid=False)))
