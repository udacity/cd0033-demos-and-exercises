"""
aws_backend.py — the LIVE AWS backend for the Cardinal Outfitters capstone.

PROVIDED FILE. Students do not edit it; they call into it from the notebook exactly as
they call the local engine. `make_catalog()` in governance_toolkit returns this class
instead of the local `GovernedCatalog` when the environment is live
(CARDINAL_LF_LIVE=1 + awswrangler + working AWS credentials).

WHAT IS REAL HERE
-----------------
This backend performs *actual* AWS operations for the three hands-on steps:

    MP2  catalog_audit / set_table_metadata / tag_column  -> AWS Glue (GetTables, UpdateTable)
    MP7  assign_tag / grant_* / create_row_filter / reset -> AWS Lake Formation
    MP7  query_as(persona, sql)                           -> STS assume-role + Amazon Athena
    MP9  governance_audit                                 -> rolls up the real Glue + LF state

Everything else (quality MP4, MDM MP5, lineage MP6, reporting MP8) is inherited unchanged
from the local engine and runs against the in-process synthetic dataset — those steps are
intentionally not part of the live-AWS scope for this course.

DESIGN: AwsGovernedCatalog subclasses GovernedCatalog. Each overridden method makes the
real AWS call AND keeps the in-memory grant/catalog mirror in sync (via super().<method>),
so grants_summary(), the local query fallback, and the MP9 access-control check all stay
coherent without extra AWS round-trips.

NOTE: this file is verified against the environment-provisioning-request.md spec but has
not been executed end-to-end outside a provisioned account — `# pragma: no cover` marks the
live-only paths. The platform team seeds the Glue database + S3 data with setup_aws.py.
"""
from __future__ import annotations  # pragma: no cover

import os

import pandas as pd

from governance_toolkit import GovernedCatalog, PERSONAS, AccessDenied


# Catalog id default is the account id; resources live in one region (see provisioning §Region).
def _cfg(key: str, default: str) -> str:
    return os.environ.get(key, default)


class AwsGovernedCatalog(GovernedCatalog):  # pragma: no cover - live AWS only
    """Live AWS implementation of the governance engine (Glue + Lake Formation + Athena)."""

    def __init__(self, db_path: str = "cardinal.db"):
        # Build the local seed too: it powers the inherited as-is steps (MP4/5/6/8) and
        # serves as the in-memory mirror the access-control audit reads.
        super().__init__(db_path)

        import boto3
        self.region = _cfg("CARDINAL_AWS_REGION", "us-east-1")
        self._session = boto3.Session(region_name=self.region)
        self.glue = self._session.client("glue")
        self.lf = self._session.client("lakeformation")
        self.sts = self._session.client("sts")

        self.account_id = self.sts.get_caller_identity()["Account"]
        # The Glue database that holds the governed tables (provisioned by setup_aws.py).
        # Derived from the seed (cardinal capstone or trailhead exercises) unless overridden.
        self.database = _cfg("CARDINAL_GLUE_DATABASE", self.catalog.database)
        self.athena_workgroup = _cfg("CARDINAL_ATHENA_WORKGROUP", self.database)
        self.results_bucket = _cfg("CARDINAL_S3_RESULTS",
                                   f"s3://{self.account_id}-{self.database}-athena-results/")

        # Resolve persona role ARNs (placeholder ACCOUNT -> real account; override per-role
        # via CARDINAL_ROLE_<NAME> if the provisioner used different names).
        self.personas = {
            role: os.environ.get(f"CARDINAL_ROLE_{role.upper()}",
                                 arn.replace("ACCOUNT", self.account_id))
            for role, arn in PERSONAS.items()
        }
        self.bootstrap_aws()

    # ----------------------------------------------------------------------- #
    # Setup / verification
    # ----------------------------------------------------------------------- #

    def bootstrap_aws(self) -> None:
        """Verify the provisioned Glue database is reachable (data is seeded by setup_aws.py)."""
        try:
            self.glue.get_database(Name=self.database)
        except Exception as e:
            raise RuntimeError(
                f"Glue database {self.database!r} not found in {self.region}. "
                f"Ask the platform team to run setup_aws.py (see environment-provisioning-request.md)."
            ) from e

    # ----------------------------------------------------------------------- #
    # MP2 — metadata reconciliation against the real Glue Data Catalog
    # ----------------------------------------------------------------------- #

    def _glue_tables(self) -> list[dict]:
        tables, token = [], None
        while True:
            kw = {"DatabaseName": self.database}
            if token:
                kw["NextToken"] = token
            resp = self.glue.get_tables(**kw)
            tables.extend(resp.get("TableList", []))
            token = resp.get("NextToken")
            if not token:
                break
        return tables

    def catalog_audit(self) -> pd.DataFrame:
        """One row per governance gap, read live from Glue table & column Parameters."""
        rows = []
        domain_of = {t: tm.domain for t, tm in self.catalog.tables.items()}
        for tbl in self._glue_tables():
            name = tbl["Name"]
            params = tbl.get("Parameters", {})
            domain = params.get("domain", domain_of.get(name, "(unknown)"))
            for attr in ("owner", "classification", "retention"):
                if not params.get(attr):
                    rows.append({"table": name, "domain": domain,
                                 "gap_type": f"missing_{attr}", "detail": attr})
            for col in tbl.get("StorageDescriptor", {}).get("Columns", []):
                if not col.get("Parameters", {}).get("classification"):
                    rows.append({"table": name, "domain": domain,
                                 "gap_type": "untagged_column",
                                 "detail": f"{col['Name']} (type {col.get('Type','')})"})
        return pd.DataFrame(rows)

    def set_table_metadata(self, table, owner=None, classification=None, retention=None) -> None:
        super().set_table_metadata(table, owner, classification, retention)  # mirror
        resp = self.glue.get_table(DatabaseName=self.database, Name=table)
        ti = _strip_table_input(resp["Table"])
        params = ti.setdefault("Parameters", {})
        for k, v in (("owner", owner), ("classification", classification), ("retention", retention)):
            if v is not None:
                params[k] = v
        self.glue.update_table(DatabaseName=self.database, TableInput=ti)

    def tag_column(self, table, column, classification) -> None:
        super().tag_column(table, column, classification)  # mirror
        resp = self.glue.get_table(DatabaseName=self.database, Name=table)
        ti = _strip_table_input(resp["Table"])
        for col in ti.get("StorageDescriptor", {}).get("Columns", []):
            if col["Name"] == column:
                col.setdefault("Parameters", {})["classification"] = classification
        self.glue.update_table(DatabaseName=self.database, TableInput=ti)

    # ----------------------------------------------------------------------- #
    # MP7 — Lake Formation grants (real), mirrored locally
    # ----------------------------------------------------------------------- #

    def _principal(self, role: str) -> dict:
        return {"DataLakePrincipalIdentifier": self.personas[role]}

    def _table_resource(self, table: str) -> dict:
        return {"Table": {"CatalogId": self.account_id,
                          "DatabaseName": self.database, "Name": table}}

    def grant_columns(self, role, table, exclude=None, include=None) -> None:
        super().grant_columns(role, table, exclude=exclude, include=include)  # mirror
        allowed = self._grants[role].table_grants[table].columns
        self.lf.grant_permissions(
            Principal=self._principal(role),
            Resource={"TableWithColumns": {"CatalogId": self.account_id,
                                           "DatabaseName": self.database, "Name": table,
                                           "ColumnNames": allowed}},
            Permissions=["SELECT"])

    def create_row_filter(self, name, table, expr) -> None:
        super().create_row_filter(name, table, expr)  # mirror
        all_cols = self._cols(table)
        try:
            self.lf.create_data_cells_filter(TableData={
                "TableCatalogId": self.account_id, "DatabaseName": self.database,
                "TableName": table, "Name": name,
                "RowFilter": {"FilterExpression": expr},
                "ColumnNames": all_cols})
        except (self.lf.exceptions.AlreadyExistsException,
                self.lf.exceptions.InvalidInputException):
            pass

    def grant_rows(self, role, table, filter_name) -> None:
        super().grant_rows(role, table, filter_name)  # mirror
        self.lf.grant_permissions(
            Principal=self._principal(role),
            Resource={"DataCellsFilter": {"TableCatalogId": self.account_id,
                                          "DatabaseName": self.database,
                                          "TableName": table, "Name": filter_name}},
            Permissions=["SELECT"])

    def assign_tag(self, table, key, value) -> None:
        super().assign_tag(table, key, value)  # mirror (catalog.lf_tags)
        try:
            self.lf.create_lf_tag(TagKey=key, TagValues=[value])
        except (self.lf.exceptions.AlreadyExistsException,
                self.lf.exceptions.InvalidInputException):
            pass
        self.lf.add_lf_tags_to_resource(
            Resource=self._table_resource(table),
            LFTags=[{"CatalogId": self.account_id, "TagKey": key, "TagValues": [value]}])

    def grant_by_tag(self, role, key, value) -> None:
        super().grant_by_tag(role, key, value)  # mirror
        self.lf.grant_permissions(
            Principal=self._principal(role),
            Resource={"LFTagPolicy": {"CatalogId": self.account_id, "ResourceType": "TABLE",
                                      "Expression": [{"TagKey": key, "TagValues": [value]}]}},
            Permissions=["SELECT", "DESCRIBE"])

    def grant_describe_only(self, role) -> None:
        super().grant_describe_only(role)  # mirror
        for t in self.tables():
            self.lf.grant_permissions(
                Principal=self._principal(role),
                Resource=self._table_resource(t),
                Permissions=["DESCRIBE"])

    def revoke_all(self, role) -> None:
        self._revoke_role_in_lf(role)
        super().revoke_all(role)  # clear mirror

    def reset(self) -> None:
        """Re-baseline real Lake Formation: revoke every persona grant, drop filters/tags."""
        for role in list(self.personas):
            self._revoke_role_in_lf(role)
        # delete data-cells filters we created
        for name, rf in list(self._row_filters.items()):
            try:
                self.lf.delete_data_cells_filter(
                    TableCatalogId=self.account_id, DatabaseName=self.database,
                    TableName=rf["table"], Name=name)
            except Exception:
                pass
        # remove LF-Tags from tables that carry them
        for t, tm in self.catalog.tables.items():
            for key, value in list(tm.lf_tags.items()):
                try:
                    self.lf.remove_lf_tags_from_resource(
                        Resource=self._table_resource(t),
                        LFTags=[{"CatalogId": self.account_id, "TagKey": key, "TagValues": [value]}])
                except Exception:
                    pass
        super().reset()  # clear mirror

    def _revoke_role_in_lf(self, role: str) -> None:
        """Best-effort revoke of whatever this role currently holds (per the mirror)."""
        g = self._grants[role]
        p = self._principal(role)
        for table, tg in g.table_grants.items():
            res = ({"TableWithColumns": {"CatalogId": self.account_id, "DatabaseName": self.database,
                                         "Name": table, "ColumnNames": tg.columns}}
                   if tg.columns is not None else self._table_resource(table))
            _safe(lambda: self.lf.revoke_permissions(Principal=p, Resource=res, Permissions=["SELECT"]))
        for key, value in g.tag_grants:
            _safe(lambda: self.lf.revoke_permissions(
                Principal=p,
                Resource={"LFTagPolicy": {"CatalogId": self.account_id, "ResourceType": "TABLE",
                                          "Expression": [{"TagKey": key, "TagValues": [value]}]}},
                Permissions=["SELECT", "DESCRIBE"]))
        if g.describe_only:
            for t in self.tables():
                _safe(lambda: self.lf.revoke_permissions(
                    Principal=p, Resource=self._table_resource(t), Permissions=["DESCRIBE"]))

    # ----------------------------------------------------------------------- #
    # MP7 verification — assume each persona role and query via real Athena
    # ----------------------------------------------------------------------- #

    def _query_as_live(self, role: str, sql: str) -> pd.DataFrame:
        import awswrangler as wr
        import boto3
        creds = self.sts.assume_role(
            RoleArn=self.personas[role], RoleSessionName=f"capstone-{role}")["Credentials"]
        sess = boto3.Session(region_name=self.region,
                             aws_access_key_id=creds["AccessKeyId"],
                             aws_secret_access_key=creds["SecretAccessKey"],
                             aws_session_token=creds["SessionToken"])
        try:
            return wr.athena.read_sql_query(
                sql, database=self.database, workgroup=self.athena_workgroup,
                s3_output=self.results_bucket, boto3_session=sess,
                ctas_approach=False)
        except Exception as e:
            # Lake Formation / Athena denials surface as a query error -> AccessDenied,
            # so verify_step7's auditor SELECT-denied check works against real enforcement.
            if "AccessDenied" in str(e) or "not authorized" in str(e).lower():
                raise AccessDenied(f"{role}: {e}") from None
            raise


def _strip_table_input(table: dict) -> dict:
    """Turn a GetTable response into a valid UpdateTable TableInput (drop read-only keys)."""
    keep = ("Name", "Description", "Owner", "Retention", "StorageDescriptor", "PartitionKeys",
            "ViewOriginalText", "ViewExpandedText", "TableType", "Parameters", "TargetTable")
    return {k: table[k] for k in keep if k in table}


def _safe(fn):
    try:
        fn()
    except Exception:
        pass
