"""
governance_toolkit.py — the provided governance engine for the Cardinal Outfitters
capstone.

PROVIDED FILE. Students call into this from the notebook; they do not edit it.

It is a small, dependency-light stand-in for the AWS governance stack:

    Glue Data Catalog  -> the Catalog metadata + catalog_audit()
    Lake Formation     -> grant_columns / create_row_filter / grant_rows /
                          assign_tag / grant_by_tag / grant_describe_only
    Athena (query-as)  -> query_as(persona, sql), which ENFORCES the persona's grants
    Great Expectations -> run_quality_suite()  (GE-shaped validation results)
    OpenLineage        -> Lineage events + trace_downstream / simulate_breach
    Reporting pipeline -> run_sustainability_report()

Access enforcement is real, not cosmetic: column grants drop columns, row filters add
WHERE clauses, tag grants gate whole tables, and metadata-only denies SELECT — all
implemented as scoped SQLite views so students see genuine SQL behavior.

HYBRID BACKEND
--------------
query_as() will use *live* Lake Formation + Athena (assume-role per persona) when the
environment provides it (set CARDINAL_LF_LIVE=1 and supply persona role ARNs + working
boto3 credentials). Otherwise it transparently falls back to the local enforcement
engine below, so the notebook always completes regardless of what the platform team
provisioned. See lf_backend().
"""
from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

import seed_data
from seed_data import Catalog, TableMeta

EPOCH = seed_data.EPOCH


# ============================================================================= #
# Exceptions
# ============================================================================= #

class AccessDenied(Exception):
    """Raised when a persona's Lake Formation grants do not permit a query.

    Mirrors what Athena returns when Lake Formation refuses access.
    """


# ============================================================================= #
# Personas (the four capstone roles). ARNs are placeholders for the local engine;
# under a live backend they are the pre-provisioned persona role ARNs.
# ============================================================================= #

PERSONAS = {
    "co_marketing_analyst": "arn:aws:iam::ACCOUNT:role/co_marketing_analyst",
    "co_cs_rep":            "arn:aws:iam::ACCOUNT:role/co_cs_rep",
    "co_data_steward":      "arn:aws:iam::ACCOUNT:role/co_data_steward",
    "co_auditor":           "arn:aws:iam::ACCOUNT:role/co_auditor",
}


def lf_backend() -> str:
    """Return 'live' if a real Lake Formation/Athena path is available, else 'local'.

    Live requires CARDINAL_LF_LIVE=1, importable awswrangler, and AWS credentials. Under
    'presume the worst' none of these are guaranteed, so this normally returns 'local'.
    """
    if os.environ.get("CARDINAL_LF_LIVE") != "1":
        return "local"
    try:
        import awswrangler  # noqa: F401
        import boto3
        boto3.client("sts").get_caller_identity()
        return "live"
    except Exception:
        return "local"


def make_catalog(db_path: str = "cardinal.db"):
    """Return the governance engine for the active backend (Step 0 uses this).

    - Live AWS (CARDINAL_LF_LIVE=1 + awswrangler + credentials) -> AwsGovernedCatalog,
      which performs real AWS Glue / Lake Formation / Athena operations for MP2, MP7, MP9.
    - Otherwise -> the local GovernedCatalog (SQLite engine) so the notebook always runs;
      this is the authoring/offline fallback, not the graded learner path.

    The two share one method surface, so the notebook cells are identical either way.
    """
    if lf_backend() == "live":
        try:
            from aws_backend import AwsGovernedCatalog
            return AwsGovernedCatalog(db_path)
        except Exception as e:   # pragma: no cover - live-only
            print(f"[make_catalog] live AWS backend unavailable ({e}); "
                  f"falling back to the local engine.")
    return GovernedCatalog(db_path)


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
    """The lake + catalog + Lake Formation enforcement engine."""

    def __init__(self, db_path: str = ":memory:"):
        self.conn, self.catalog = seed_data.build(db_path)
        self.conn.row_factory = sqlite3.Row
        self._grants: dict[str, RoleGrants] = {r: RoleGrants() for r in PERSONAS}
        self._row_filters: dict[str, dict] = {}   # name -> {table, expr}
        self.lineage = build_lineage()

    # ---- read helpers ------------------------------------------------------- #

    def query(self, sql: str) -> pd.DataFrame:
        """Unrestricted query (admin context). Used by setup/teaching cells."""
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

    # ---- Step 2: metadata reconciliation ------------------------------------ #

    def catalog_audit(self) -> pd.DataFrame:
        """Return one row per governance gap found in the catalog.

        Gap kinds: missing table-level owner / classification / retention, and any
        column whose classification is unset (an untagged column — a PII risk when the
        column actually holds personal data).
        """
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
        """Write table-level governance metadata to the catalog (Step 2 remediation).

        Only the arguments you pass are updated; the rest are left as-is. Under the AWS
        backend this calls Glue UpdateTable (table Parameters); locally it updates the
        in-memory Glue-analog catalog. Either way, a follow-up catalog_audit() reflects it.
        """
        tm = self.catalog.table(table)
        if owner is not None:
            tm.owner = owner
        if classification is not None:
            tm.classification = classification
        if retention is not None:
            tm.retention = retention

    def tag_column(self, table: str, column: str, classification: str) -> None:
        """Set a column's classification in the catalog (Step 2 PII tagging).

        Under the AWS backend this writes the column's Glue parameter; locally it updates
        the in-memory catalog. Used to tag an untagged PII column (e.g. customer.phone).
        """
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
        g = self._grants[role].table_grants.setdefault(table, TableGrant())
        g.columns = allowed

    def create_row_filter(self, name: str, table: str, expr: str) -> None:
        """Define a named data-cell filter (a row predicate) on a table."""
        self._row_filters[name] = {"table": table, "expr": expr}

    def grant_rows(self, role: str, table: str, filter_name: str) -> None:
        """Grant a role SELECT on a table through a previously defined row filter."""
        self._check_role(role)
        rf = self._row_filters[filter_name]
        if rf["table"] != table:
            raise ValueError(f"filter {filter_name!r} is defined on {rf['table']}, not {table}")
        g = self._grants[role].table_grants.setdefault(table, TableGrant())
        g.row_filter = rf["expr"]
        if g.columns is None:
            g.columns = self._cols(table)   # full columns unless a column grant narrows it

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
        """Human-readable view of what every persona can currently see."""
        rows = []
        for role, g in self._grants.items():
            if g.describe_only:
                rows.append({"role": role, "table": "(all)", "access": "DESCRIBE only (no rows)"})
                continue
            tagged = self._tables_for_tags(g.tag_grants)
            seen = set()
            for table, tg in g.table_grants.items():
                seen.add(table)
                cols = "all" if tg.columns is None or len(tg.columns) == len(self._cols(table)) \
                    else f"{len(tg.columns)} of {len(self._cols(table))}"
                rows.append({"role": role, "table": table,
                             "access": f"cols={cols}; rows={tg.row_filter or 'all'}"})
            for table in tagged - seen:
                rows.append({"role": role, "table": table, "access": "via LF-Tag (all cols/rows)"})
            if not g.table_grants and not tagged:
                rows.append({"role": role, "table": "(none)", "access": "no grants"})
        return pd.DataFrame(rows)

    # ---- query-as-persona (hybrid live/local) ------------------------------- #

    def query_as(self, role: str, sql: str) -> pd.DataFrame:
        """Run `sql` as `role`, enforcing that role's Lake Formation grants.

        Hybrid: tries the live assume-role + Athena path when the backend is live,
        otherwise enforces locally. Raises AccessDenied when grants forbid the query.
        """
        self._check_role(role)
        if lf_backend() == "live":
            try:
                return self._query_as_live(role, sql)
            except AccessDenied:
                raise
            except Exception:
                pass  # any live-path failure -> fall back to local enforcement
        return self._query_as_local(role, sql)

    def _query_as_live(self, role: str, sql: str) -> pd.DataFrame:  # pragma: no cover
        import awswrangler as wr
        import boto3
        creds = boto3.client("sts").assume_role(
            RoleArn=PERSONAS[role], RoleSessionName=f"capstone-{role}")["Credentials"]
        sess = boto3.Session(aws_access_key_id=creds["AccessKeyId"],
                             aws_secret_access_key=creds["SecretAccessKey"],
                             aws_session_token=creds["SessionToken"])
        return wr.athena.read_sql_query(sql, database=self.catalog.database, boto3_session=sess)

    def _query_as_local(self, role: str, sql: str) -> pd.DataFrame:
        g = self._grants[role]
        table = _table_in_from(sql)
        if _is_describe(sql):
            if table is None:
                raise AccessDenied("metadata query did not name a table")
            return self.describe(table)
        if table is None:
            raise AccessDenied("could not determine target table; the local engine "
                               "supports single-table SELECT/ DESCRIBE queries")
        if g.describe_only:
            raise AccessDenied(f"{role} has metadata-only access; SELECT on '{table}' denied")

        tg = g.table_grants.get(table)
        via_tag = self._table_has_tag(table, g.tag_grants)
        if tg is None and not via_tag:
            raise AccessDenied(f"{role} has no Lake Formation grant on '{table}'")

        if via_tag and tg is None:
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
        """True if some Lake Formation grant or LF-Tag governs access to `table`.

        A PII-bearing table with neither is effectively wide open — the access-control
        gap the Step 9 governance audit flags. Works on the in-memory grant mirror, which
        the AWS backend keeps in sync as it applies real Lake Formation grants.
        """
        if any(table in g.table_grants for g in self._grants.values()):
            return True
        if self.catalog.table(table).lf_tags:
            return True
        return False

    # ---- Step 4: quality ---------------------------------------------------- #

    def run_quality_suite(self) -> pd.DataFrame:
        return run_quality_suite(self.conn)

    # ---- Step 5: master data / stewardship ---------------------------------- #

    def resolve_customers(self) -> "MatchResult":
        return resolve_customers(self.conn)

    # ---- Step 8: cross-domain reporting ------------------------------------- #

    def run_sustainability_report(self) -> "ReportResult":
        return run_sustainability_report(self.conn)

    # ---- Step 9: governance audit ------------------------------------------- #

    def governance_audit(self, contracts_valid: bool | None = None) -> pd.DataFrame:
        return governance_audit(self, contracts_valid=contracts_valid)


# ============================================================================= #
# SQL parsing helpers (single-table subset the local engine supports)
# ============================================================================= #

def _table_in_from(sql: str) -> str | None:
    # FROM <table> (SELECT, SHOW COLUMNS FROM ...) or a bare metadata form:
    # DESCRIBE <table> / PRAGMA table_info(<table>).
    m = re.search(r"\bFROM\s+([A-Za-z_][A-Za-z0-9_]*)", sql, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\b(?:DESCRIBE|table_info)\s*\(?\s*([A-Za-z_][A-Za-z0-9_]*)",
                  sql, flags=re.IGNORECASE)
    return m.group(1) if m else None


def _is_describe(sql: str) -> bool:
    s = sql.strip().lower()
    return s.startswith("describe") or s.startswith("pragma") or s.startswith("show columns")


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


def run_quality_suite(conn: sqlite3.Connection) -> pd.DataFrame:
    """Run expectation-style checks across the six data-quality dimensions.

    Output schema matches a Great Expectations validation result (one row per
    expectation) so the interpretation skill transfers directly to real GE output.
    """
    df = lambda q: pd.read_sql_query(q, conn)
    results = []

    # completeness
    prod = df("SELECT category, sustainability_class FROM product")
    results.append(_expectation("product", "category", "expect_column_values_to_not_be_null",
                                "completeness", len(prod), int(prod["category"].isna().sum())))
    results.append(_expectation("product", "sustainability_class",
                                "expect_column_values_to_not_be_null", "completeness",
                                len(prod), int(prod["sustainability_class"].isna().sum())))

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
    consent = df("""
        SELECT c.marketing_consent AS loyalty, m.mkt_consent AS marketing
        FROM customer c JOIN campaign_membership m ON m.cust_ref = c.email""")
    mism = int((consent["loyalty"] != consent["marketing"]).sum())
    results.append(_expectation("campaign_membership", "mkt_consent",
                                "expect_consent_to_match_system_of_record", "consistency",
                                len(consent), mism))

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


def resolve_customers(conn: sqlite3.Connection) -> MatchResult:
    """Block + score candidate duplicate customers; flag the ambiguous band for stewards."""
    cust = pd.read_sql_query(
        "SELECT customer_id, full_name, email, region FROM customer", conn)
    # Only records with a well-formed email are joinable on the email signal; records
    # with missing/invalid email (n/a) are not matched here — you cannot dedup on a key
    # that isn't there. With unique names in the base population, that leaves only the
    # deliberately seeded near-duplicates as candidates.
    cust = cust[cust["email"].fillna("").str.contains("@")].copy()
    cust["nkey"] = cust["full_name"].map(_name_key)
    cust["elocal"] = cust["email"].str.split("@").str[0].str.replace(r"\d+$", "", regex=True)

    pairs = []
    by_local = cust.groupby("elocal")
    for local, grp in by_local:
        if not local or len(grp) < 2:
            continue
        recs = grp.to_dict("records")
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
                pairs.append({"id_a": a["customer_id"], "name_a": a["full_name"],
                              "email_a": a["email"], "id_b": b["customer_id"],
                              "name_b": b["full_name"], "email_b": b["email"],
                              "score": score, "band": band})
    pdf = pd.DataFrame(pairs).sort_values("score", ascending=False).reset_index(drop=True)
    amb = pdf[pdf["band"] == "ambiguous"].reset_index(drop=True)
    return MatchResult(pairs=pdf, ambiguous=amb)


def apply_adjudications(match: MatchResult, decisions: dict[int, str]) -> dict:
    """Apply steward accept/reject decisions to the ambiguous pairs.

    decisions: {row_index_in_match.ambiguous: 'accept'|'reject'}. Returns before/after
    golden-record counts and the survivorship outcome per accepted merge.
    """
    amb = match.ambiguous
    merged = []
    for idx, decision in decisions.items():
        if decision != "accept":
            continue
        row = amb.loc[idx]
        # survivorship: keep the lower customer_id as the golden record (system of record)
        keep, drop = sorted([row["id_a"], row["id_b"]])
        merged.append({"golden_id": keep, "merged_id": drop,
                       "survivorship": "lowest customer_id wins (loyalty system of record)"})
    accepted = len(merged)
    return {"ambiguous_pairs": len(amb), "accepted_merges": accepted,
            "rejected": sum(1 for d in decisions.values() if d == "reject"),
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
    """The pre-instrumented pipeline lineage for Cardinal Outfitters."""
    jobs = {
        "build_order_carbon": {"inputs": ["orders", "shipment"],
                               "outputs": ["order_carbon"]},
        "build_quarterly_sustainability": {
            "inputs": ["order_carbon", "product", "supplier"],
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


def run_sustainability_report(conn: sqlite3.Connection) -> ReportResult:
    """Compute the CSRD quarterly carbon disclosure from orders + shipments.

    Includes the seeded grams-vs-kg unit defect so the reconciliation step has a real
    discrepancy to trace back to source.
    """
    per_order = pd.read_sql_query("""
        SELECT o.order_id, o.order_ts, s.shipment_id, s.carbon_kg
        FROM orders o JOIN shipment s ON s.order_id = o.order_id
        WHERE o.status != 'cancelled'""", conn)
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

    # 1. catalog tag gaps (from MP2 surface)
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

    # 6. access-control gaps: any PII-bearing table with no Lake Formation restriction.
    # After MP7 governs `customer`, this surfaces the *other* PII table (campaign_membership,
    # which holds cust_ref = email) so MP9 has a real access remediation to perform in AWS.
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

    Returns a per-persona pass/fail table the student includes as evidence. Works under
    either backend (live assume-role or local enforcement) because it goes through
    gc.query_as().
    """
    rows = []

    def record(persona, check, passed, detail):
        rows.append({"persona": persona, "check": check,
                     "result": "PASS" if passed else "FAIL", "detail": detail})

    # marketing analyst: succeeds, PII columns absent
    try:
        df = gc.query_as("co_marketing_analyst", f"SELECT * FROM {table} LIMIT 20")
        masked = not ({"email", "phone"} & set(df.columns))
        record("co_marketing_analyst", "PII columns masked", masked,
               f"columns={list(df.columns)}")
    except AccessDenied as e:
        record("co_marketing_analyst", "PII columns masked", False, f"denied: {e}")

    # cs_rep: succeeds, every row region='EU'
    try:
        df = gc.query_as("co_cs_rep", f"SELECT region FROM {table} LIMIT 1000")
        eu_only = len(df) > 0 and (df["region"] == "EU").all()
        record("co_cs_rep", "row filter region=EU", eu_only,
               f"regions={sorted(df['region'].unique())}, rows={len(df)}")
    except AccessDenied as e:
        record("co_cs_rep", "row filter region=EU", False, f"denied: {e}")

    # steward: full columns and full rows
    try:
        df = gc.query_as("co_data_steward", f"SELECT * FROM {table} LIMIT 20")
        full = {"email", "phone"}.issubset(df.columns)
        record("co_data_steward", "tag grant = full access", full,
               f"columns={len(df.columns)} (incl. PII={full})")
    except AccessDenied as e:
        record("co_data_steward", "tag grant = full access", False, f"denied: {e}")

    # auditor: DESCRIBE works, SELECT denied
    try:
        meta = gc.query_as("co_auditor", f"DESCRIBE {table}")
        describe_ok = len(meta) > 0
    except AccessDenied:
        describe_ok = False
    try:
        gc.query_as("co_auditor", f"SELECT * FROM {table} LIMIT 1")
        select_denied = False
    except AccessDenied:
        select_denied = True
    record("co_auditor", "metadata-only (DESCRIBE ok, SELECT denied)",
           describe_ok and select_denied,
           f"describe_ok={describe_ok}, select_denied={select_denied}")

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
                "pii_tags": {"type": "array", "items": {"type": "string"}},
                "retention": {"type": "string", "pattern": r"^P\d+[YMD]$"},
                "quality_slos": {
                    "type": "array", "minItems": 1,
                    "items": {"type": "object", "required": ["dimension", "threshold"],
                              "properties": {"dimension": {"type": "string"},
                                             "threshold": {"type": "number"}}}}}},
    },
}


def validate_contract(contract: dict) -> tuple[bool, list[str]]:
    """Validate a data contract against the governance schema. Returns (ok, [errors])."""
    import jsonschema
    validator = jsonschema.Draft202012Validator(CONTRACT_SCHEMA)
    errors = [f"{'/'.join(map(str, e.path)) or '(root)'}: {e.message}"
              for e in sorted(validator.iter_errors(contract), key=lambda e: list(e.path))]
    return (len(errors) == 0, errors)


def base_contract() -> dict:
    """A minimal, NON-governed contract for the orders data product (the starting point)."""
    return {
        "name": "orders",
        "domain": "E-commerce Orders",
        "owner": "orders-team@cardinal.example",
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
    print("QUALITY failing:", int((~gc.run_quality_suite()["success"]).sum()), "of",
          len(gc.run_quality_suite()))
    print("LINEAGE downstream of shipment:", gc.lineage.trace_downstream("shipment"))
    m = gc.resolve_customers()
    print("MDM ambiguous pairs:", len(m.ambiguous))
    rep = gc.run_sustainability_report()
    print("REPORT quarters:", len(rep.quarterly),
          "| reconciliation mismatches:", int((~rep.reconciliation["matches"]).sum()))
    ok, errs = validate_contract(base_contract())
    print("CONTRACT base valid?", ok, "| errors:", len(errs))
    print("GOV AUDIT findings:", len(gc.governance_audit(contracts_valid=False)))
