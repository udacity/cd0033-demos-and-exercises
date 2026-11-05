"""
aws_backend.py — Live AWS Medallion Lakehouse backend for Veridian Health (`veridian_lakehouse`).

PROVIDED FILE for instructor demos. Executes catalog, access-control, and analytical queries
against live AWS Glue Data Catalog, AWS Lake Formation, and Amazon Athena.
"""
from __future__ import annotations  # pragma: no cover

import os

import pandas as pd

from demo_toolkit import (
    AccessDenied,
    HEALTHCARE_PERSONAS,
    MedallionLakehouse,
    RoleGrants,
    TableGrant,
    _is_describe,
    _table_in_from,
)


def _cfg(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _detect_workgroup_and_results(athena, s3, account_id: str, database: str) -> tuple[str, str]:
    explicit_wg = os.environ.get("VERIDIAN_ATHENA_WORKGROUP") or os.environ.get("CARDINAL_ATHENA_WORKGROUP")
    explicit_res = os.environ.get("VERIDIAN_S3_RESULTS") or os.environ.get("CARDINAL_S3_RESULTS")

    candidates = ([explicit_wg] if explicit_wg else []) + [database, "veridian", "cardinal", "trailhead", "primary"]
    chosen_wg = "primary"
    chosen_res = explicit_res or ""

    for wg in dict.fromkeys(c for c in candidates if c):
        try:
            resp = athena.get_work_group(WorkGroup=wg)
            chosen_wg = wg
            if not chosen_res:
                loc = (resp.get("WorkGroup", {})
                       .get("Configuration", {})
                       .get("ResultConfiguration", {})
                       .get("OutputLocation", ""))
                if loc:
                    chosen_res = loc
            break
        except Exception:
            continue

    if not chosen_res:
        for b in dict.fromkeys([
            f"{account_id}-veridian-athena-results",
            f"{account_id}-{database}-athena-results",
            f"{account_id}-cardinal-athena-results",
        ]):
            try:
                s3.head_bucket(Bucket=b)
                chosen_res = f"s3://{b}/"
                break
            except Exception:
                continue

    if not chosen_res:
        chosen_res = f"s3://{account_id}-veridian-athena-results/"

    return chosen_wg, chosen_res


class AwsMedallionLakehouse(MedallionLakehouse):  # pragma: no cover - live AWS
    """Live AWS implementation of Veridian Health's Medallion Lakehouse (Glue + Lake Formation + Athena)."""

    def __init__(self):
        super().__init__()

        import boto3
        self.region = _cfg("VERIDIAN_AWS_REGION", _cfg("CARDINAL_AWS_REGION", "us-east-1"))
        self._session = boto3.Session(region_name=self.region)
        self.glue = self._session.client("glue")
        self.lf = self._session.client("lakeformation")
        self.sts = self._session.client("sts")
        self.athena = self._session.client("athena")
        self.s3 = self._session.client("s3")

        self.account_id = self.sts.get_caller_identity()["Account"]
        self.database = _cfg("VERIDIAN_GLUE_DATABASE", self.catalog.database)
        self.athena_workgroup, self.results_bucket = _detect_workgroup_and_results(
            self.athena, self.s3, self.account_id, self.database
        )

        self.personas = {
            role: os.environ.get(f"VERIDIAN_ROLE_{role.upper()}", arn.replace("ACCOUNT", self.account_id))
            for role, arn in HEALTHCARE_PERSONAS.items()
        }
        self._verify_glue_database()
        self._sync_from_aws()

    def _verify_glue_database(self) -> None:
        try:
            self.glue.get_database(Name=self.database)
        except Exception as e:
            raise RuntimeError(
                f"Glue database {self.database!r} not found in {self.region}. "
                f"Run the 'Step 0: Connect to your Cloud Lab' cell (`setup_aws.main()`) first."
            ) from e

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

    def _sync_from_aws(self) -> None:
        try:
            for tbl in self._glue_tables():
                name = tbl["Name"]
                if name not in self.catalog.tables:
                    continue
                tm = self.catalog.table(name)
                params = tbl.get("Parameters", {})
                tm.steward = params.get("steward") or None
                tm.sensitivity = params.get("sensitivity") or None
                tm.retention_policy = params.get("retention_policy") or None
                for col in tbl.get("StorageDescriptor", {}).get("Columns", []):
                    cmeta = tm.column(col["Name"])
                    if cmeta is not None:
                        cmeta.sensitivity = col.get("Parameters", {}).get("sensitivity") or None
        except Exception:
            pass

        for name, tm in self.catalog.tables.items():
            try:
                resp = self.lf.get_resource_lf_tags(
                    CatalogId=self.account_id,
                    Resource=self._table_resource(name),
                    ShowAssignedLFTags=True,
                )
                tags = {}
                for tag in resp.get("LFTagsOnTable", []):
                    vals = tag.get("TagValues", [])
                    if tag.get("TagKey") and vals:
                        tags[tag["TagKey"]] = vals[0]
                tm.lf_tags = tags
            except Exception:
                pass

    def query(self, sql: str) -> pd.DataFrame:
        import awswrangler as wr
        return wr.athena.read_sql_query(
            sql,
            database=self.database,
            workgroup=self.athena_workgroup,
            s3_output=self.results_bucket,
            boto3_session=self._session,
            ctas_approach=False,
        )

    def describe_table(self, table: str) -> pd.DataFrame:
        resp = self.glue.get_table(DatabaseName=self.database, Name=table)
        tm = self.catalog.table(table) if table in self.catalog.tables else None
        rows = []
        for col in resp["Table"].get("StorageDescriptor", {}).get("Columns", []):
            cname = col["Name"]
            cmeta = tm.column(cname) if tm else None
            rows.append({
                "column": cname,
                "type": col.get("Type", ""),
                "zone": tm.zone if tm else "silver",
                "sensitivity": col.get("Parameters", {}).get("sensitivity") or "(untagged)",
                "description": col.get("Comment") or (cmeta.description if cmeta else ""),
            })
        return pd.DataFrame(rows)

    def audit_lakehouse_catalog(self) -> pd.DataFrame:
        self._sync_from_aws()
        rows = []
        for tbl in self._glue_tables():
            name = tbl["Name"]
            tm = self.catalog.table(name) if name in self.catalog.tables else None
            params = tbl.get("Parameters", {})
            zone = params.get("medallion_zone", tm.zone if tm else "silver")
            domain = params.get("domain", tm.domain if tm else "(unknown)")
            for attr in ("steward", "sensitivity", "retention_policy"):
                if not params.get(attr):
                    rows.append({
                        "table": name, "zone": zone, "domain": domain,
                        "gap_type": f"missing_{attr}", "detail": attr,
                    })
            for col in tbl.get("StorageDescriptor", {}).get("Columns", []):
                if not col.get("Parameters", {}).get("sensitivity"):
                    rows.append({
                        "table": name, "zone": zone, "domain": domain,
                        "gap_type": "untagged_column",
                        "detail": f"{col['Name']} (type {col.get('Type', '')})",
                    })
        return pd.DataFrame(rows)

    def set_table_governance(self, table, steward=None, sensitivity=None, retention_policy=None) -> None:
        super().set_table_governance(table, steward, sensitivity, retention_policy)
        resp = self.glue.get_table(DatabaseName=self.database, Name=table)
        ti = _strip_table_input(resp["Table"])
        params = ti.setdefault("Parameters", {})
        for k, v in (("steward", steward), ("sensitivity", sensitivity), ("retention_policy", retention_policy)):
            if v is not None:
                params[k] = v
        self.glue.update_table(DatabaseName=self.database, TableInput=ti)

    def classify_column(self, table, column, sensitivity) -> None:
        super().classify_column(table, column, sensitivity)
        resp = self.glue.get_table(DatabaseName=self.database, Name=table)
        ti = _strip_table_input(resp["Table"])
        for col in ti.get("StorageDescriptor", {}).get("Columns", []):
            if col["Name"] == column:
                col.setdefault("Parameters", {})["sensitivity"] = sensitivity
        self.glue.update_table(DatabaseName=self.database, TableInput=ti)

    def _principal(self, role: str) -> dict:
        return {"DataLakePrincipalIdentifier": self.personas[role]}

    def _table_resource(self, table: str) -> dict:
        return {"Table": {"CatalogId": self.account_id, "DatabaseName": self.database, "Name": table}}

    def grant_column_subset(self, role, table, exclude=None, include=None) -> None:
        super().grant_column_subset(role, table, exclude=exclude, include=include)
        allowed = self._grants[role].table_grants[table].columns
        self.lf.grant_permissions(
            Principal=self._principal(role),
            Resource={"TableWithColumns": {
                "CatalogId": self.account_id, "DatabaseName": self.database,
                "Name": table, "ColumnNames": allowed,
            }},
            Permissions=["SELECT"],
        )

    def define_jurisdiction_filter(self, name, table, expr) -> None:
        super().define_jurisdiction_filter(name, table, expr)
        all_cols = self._cols(table)
        try:
            self.lf.create_data_cells_filter(TableData={
                "TableCatalogId": self.account_id, "DatabaseName": self.database,
                "TableName": table, "Name": name,
                "RowFilter": {"FilterExpression": expr}, "ColumnNames": all_cols,
            })
        except Exception:
            pass

    def grant_filtered_rows(self, role, table, filter_name) -> None:
        super().grant_filtered_rows(role, table, filter_name)
        self.lf.grant_permissions(
            Principal=self._principal(role),
            Resource={"DataCellsFilter": {
                "TableCatalogId": self.account_id, "DatabaseName": self.database,
                "TableName": table, "Name": filter_name,
            }},
            Permissions=["SELECT"],
        )

    def tag_medallion_table(self, table, key, value) -> None:
        super().tag_medallion_table(table, key, value)
        try:
            self.lf.create_lf_tag(TagKey=key, TagValues=[value])
        except Exception:
            try:
                self.lf.update_lf_tag(TagKey=key, TagValuesToAdd=[value])
            except Exception:
                pass
        self.lf.add_lf_tags_to_resource(
            Resource=self._table_resource(table),
            LFTags=[{"CatalogId": self.account_id, "TagKey": key, "TagValues": [value]}],
        )

    def grant_lf_tag(self, role, key, value) -> None:
        super().grant_lf_tag(role, key, value)
        try:
            self.lf.create_lf_tag(TagKey=key, TagValues=[value])
        except Exception:
            pass
        self.lf.grant_permissions(
            Principal=self._principal(role),
            Resource={"LFTagPolicy": {
                "CatalogId": self.account_id, "ResourceType": "TABLE",
                "Expression": [{"TagKey": key, "TagValues": [value]}],
            }},
            Permissions=["SELECT", "DESCRIBE"],
        )

    def grant_schema_only(self, role) -> None:
        super().grant_schema_only(role)
        for t in self.tables():
            self.lf.grant_permissions(
                Principal=self._principal(role),
                Resource=self._table_resource(t),
                Permissions=["DESCRIBE"],
            )

    def _query_as_live(self, role: str, sql: str) -> pd.DataFrame:
        import awswrangler as wr
        import boto3
        creds = self.sts.assume_role(
            RoleArn=self.personas[role], RoleSessionName=f"veridian-{role}"
        )["Credentials"]
        sess = boto3.Session(
            region_name=self.region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
        if _is_describe(sql):
            table = _table_in_from(sql)
            if table is None:
                raise AccessDenied("metadata query did not name a table")
            role_glue = sess.client("glue")
            resp = role_glue.get_table(DatabaseName=self.database, Name=table)
            return pd.DataFrame([
                {"column": c["Name"], "type": c.get("Type", ""),
                 "sensitivity": c.get("Parameters", {}).get("sensitivity") or "(untagged)"}
                for c in resp["Table"].get("StorageDescriptor", {}).get("Columns", [])
            ])
        try:
            return wr.athena.read_sql_query(
                sql, database=self.database, workgroup=self.athena_workgroup,
                s3_output=self.results_bucket, boto3_session=sess, ctas_approach=False,
            )
        except Exception as e:
            raise AccessDenied(f"{role}: {e}") from None


def _strip_table_input(table: dict) -> dict:
    keep = ("Name", "Description", "Owner", "Retention", "StorageDescriptor", "PartitionKeys",
            "ViewOriginalText", "ViewExpandedText", "TableType", "Parameters", "TargetTable")
    return {k: table[k] for k in keep if k in table}
