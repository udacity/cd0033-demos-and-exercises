"""
aws_backend.py — the LIVE AWS backend for the Trailhead Provisions & Cardinal Outfitters
governed data platform (Glue Data Catalog + Lake Formation + Amazon Athena).

PROVIDED FILE. Students do not edit it; they call into it from the notebook via
`make_catalog()` in `governance_toolkit.py`.

WHAT IS REAL HERE
-----------------
All catalog, access-control, and analytical operations execute against live AWS services:

    MP2  catalog_audit / set_table_metadata / tag_column  -> AWS Glue (GetTables, UpdateTable)
    MP4  run_quality_suite                                -> Amazon Athena queries via self.query()
    MP5  resolve_customers                                -> Amazon Athena queries via self.query()
    MP7  assign_tag / grant_* / create_row_filter / reset -> AWS Lake Formation
    MP7  query_as(persona, sql)                           -> STS assume-role + Glue / Amazon Athena
    MP8  run_sustainability_report                        -> Amazon Athena queries via self.query()
    MP9  governance_audit                                 -> rolls up live Glue + Lake Formation state
"""
from __future__ import annotations  # pragma: no cover

import os

import pandas as pd

from governance_toolkit import (
    GovernedCatalog,
    PERSONAS,
    AccessDenied,
    RoleGrants,
    TableGrant,
    _is_describe,
    _table_in_from,
)


def _cfg(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _detect_workgroup_and_results(athena, s3, account_id: str, database: str, region: str) -> tuple[str, str]:
    """Auto-detect the Athena workgroup (preferring CARDINAL_ATHENA_WORKGROUP, then
    <database>, 'cardinal', 'trailhead', 'primary') and S3 results bucket."""
    explicit_wg = os.environ.get("CARDINAL_ATHENA_WORKGROUP")
    explicit_res = os.environ.get("CARDINAL_S3_RESULTS")

    candidates = ([explicit_wg] if explicit_wg else []) + [database, "cardinal", "trailhead", "primary"]
    chosen_wg = database
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
            f"{account_id}-{database}-athena-results",
            f"{account_id}-cardinal-athena-results",
            f"{account_id}-trailhead-athena-results",
        ]):
            try:
                s3.head_bucket(Bucket=b)
                chosen_res = f"s3://{b}/"
                break
            except Exception:
                continue

    if not chosen_res:
        chosen_res = f"s3://{account_id}-cardinal-athena-results/"

    return chosen_wg, chosen_res


class AwsGovernedCatalog(GovernedCatalog):  # pragma: no cover - live AWS
    """Live AWS implementation of the governance engine (Glue + Lake Formation + Athena)."""

    def __init__(self, db_path: str = "trailhead.db"):
        super().__init__(db_path)

        import boto3
        self.region = _cfg("CARDINAL_AWS_REGION", "us-east-1")
        self._session = boto3.Session(region_name=self.region)
        self.glue = self._session.client("glue")
        self.lf = self._session.client("lakeformation")
        self.sts = self._session.client("sts")
        self.athena = self._session.client("athena")
        self.s3 = self._session.client("s3")

        self.account_id = self.sts.get_caller_identity()["Account"]
        self.database = _cfg("CARDINAL_GLUE_DATABASE", self.catalog.database)
        self.athena_workgroup, self.results_bucket = _detect_workgroup_and_results(
            self.athena, self.s3, self.account_id, self.database, self.region
        )

        self.personas = {
            role: os.environ.get(f"CARDINAL_ROLE_{role.upper()}",
                                 arn.replace("ACCOUNT", self.account_id))
            for role, arn in PERSONAS.items()
        }
        self.bootstrap_aws()
        self._sync_from_aws()

    # ----------------------------------------------------------------------- #
    # Setup / verification & live state sync
    # ----------------------------------------------------------------------- #

    def bootstrap_aws(self) -> None:
        """Verify the provisioned Glue database is reachable (seeded by Step 0 / setup_aws.py)."""
        try:
            self.glue.get_database(Name=self.database)
        except Exception as e:
            raise RuntimeError(
                f"Glue database {self.database!r} not found in {self.region}. "
                f"Run the 'Step 0: Connect to your Cloud Lab' cell (or `python3 setup_aws.py`) "
                f"to seed the Glue catalog and S3 tables."
            ) from e

    def _sync_from_aws(self) -> None:
        """Sync in-memory catalog metadata, LF-Tags, and persona permissions from live Glue & LF."""
        # 1. Sync table and column classifications/owners/retention from Glue
        try:
            for tbl in self._glue_tables():
                name = tbl["Name"]
                if name not in self.catalog.tables:
                    continue
                tm = self.catalog.table(name)
                params = tbl.get("Parameters", {})
                tm.owner = params.get("owner") or None
                tm.classification = params.get("classification") or None
                tm.retention = params.get("retention") or None
                for col in tbl.get("StorageDescriptor", {}).get("Columns", []):
                    cmeta = tm.column(col["Name"])
                    if cmeta is not None:
                        cmeta.classification = col.get("Parameters", {}).get("classification") or None
        except Exception:
            pass

        # 2. Sync LF-Tags on tables from Lake Formation
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

        # 3. Sync DataCellsFilters from Lake Formation
        for name in self.catalog.tables:
            try:
                resp = self.lf.list_data_cells_filter(
                    Table={"CatalogId": self.account_id, "DatabaseName": self.database, "Name": name}
                )
                for dcf in resp.get("DataCellsFilters", []):
                    expr = dcf.get("RowFilter", {}).get("FilterExpression")
                    if dcf.get("Name") and expr:
                        self._row_filters[dcf["Name"]] = {"table": name, "expr": expr}
            except Exception:
                pass

        # 4. Sync persona permissions from Lake Formation
        self._grants = {r: RoleGrants() for r in PERSONAS}
        arn_to_role = {arn: role for role, arn in self.personas.items()}
        try:
            entries = self._list_all_lf_permissions()
            describe_tables: dict[str, set[str]] = {r: set() for r in PERSONAS}
            select_roles: set[str] = set()
            for entry in entries:
                principal_arn = entry.get("Principal", {}).get("DataLakePrincipalIdentifier", "")
                role = arn_to_role.get(principal_arn)
                if not role:
                    continue
                perms = set(entry.get("Permissions", []))
                res = entry.get("Resource", {})
                g = self._grants[role]

                if "LFTagPolicy" in res and "SELECT" in perms:
                    select_roles.add(role)
                    for expr in res["LFTagPolicy"].get("Expression", []):
                        k = expr.get("TagKey")
                        for v in expr.get("TagValues", []):
                            if k and v:
                                g.tag_grants.add((k, v))

                elif "DataCellsFilter" in res and "SELECT" in perms:
                    select_roles.add(role)
                    dcf = res["DataCellsFilter"]
                    tname = dcf.get("TableName")
                    fname = dcf.get("Name")
                    if tname in self.catalog.tables:
                        tg = g.table_grants.setdefault(tname, TableGrant())
                        rf = self._row_filters.get(fname, {})
                        tg.row_filter = rf.get("expr", f"filter:{fname}")
                        if tg.columns is None:
                            tg.columns = self._cols(tname)

                elif "TableWithColumns" in res and "SELECT" in perms:
                    select_roles.add(role)
                    twc = res["TableWithColumns"]
                    tname = twc.get("Name")
                    if tname in self.catalog.tables:
                        tg = g.table_grants.setdefault(tname, TableGrant())
                        cols = twc.get("ColumnNames")
                        if cols:
                            existing = set(tg.columns or [])
                            tg.columns = [c for c in self._cols(tname) if c in (existing | set(cols))]
                        elif twc.get("ColumnWildcard") is not None:
                            excluded = set(twc["ColumnWildcard"].get("ExcludedColumnNames", []))
                            tg.columns = [c for c in self._cols(tname) if c not in excluded]

                elif "Table" in res:
                    tname = res["Table"].get("Name")
                    if "SELECT" in perms and tname in self.catalog.tables:
                        select_roles.add(role)
                        tg = g.table_grants.setdefault(tname, TableGrant())
                        tg.columns = self._cols(tname)
                        tg.row_filter = None
                    elif "DESCRIBE" in perms and "SELECT" not in perms and tname:
                        describe_tables[role].add(tname)

            for role, dtables in describe_tables.items():
                if dtables and role not in select_roles:
                    self._grants[role].describe_only = True
        except Exception:
            pass

    def _list_all_lf_permissions(self) -> list[dict]:
        """Return all Lake Formation permission entries in the account."""
        out, token = [], None
        while True:
            kw = {"CatalogId": self.account_id}
            if token:
                kw["NextToken"] = token
            resp = self.lf.list_permissions(**kw)
            out.extend(resp.get("PrincipalResourcePermissions", []))
            token = resp.get("NextToken")
            if not token:
                break
        return out

    # ----------------------------------------------------------------------- #
    # Admin query & describe against live Athena & Glue
    # ----------------------------------------------------------------------- #

    def query(self, sql: str) -> pd.DataFrame:
        """Execute an admin query against live Amazon Athena."""
        import awswrangler as wr
        return wr.athena.read_sql_query(
            sql,
            database=self.database,
            workgroup=self.athena_workgroup,
            s3_output=self.results_bucket,
            boto3_session=self._session,
            ctas_approach=False,
        )

    def describe(self, table: str) -> pd.DataFrame:
        """Read schema + classification for `table` live from the AWS Glue Data Catalog."""
        resp = self.glue.get_table(DatabaseName=self.database, Name=table)
        tm = self.catalog.table(table) if table in self.catalog.tables else None
        rows = []
        for col in resp["Table"].get("StorageDescriptor", {}).get("Columns", []):
            cname = col["Name"]
            cmeta = tm.column(cname) if tm else None
            cls = col.get("Parameters", {}).get("classification") or "(untagged)"
            desc = col.get("Comment") or (cmeta.description if cmeta else "")
            rows.append({
                "column": cname,
                "type": col.get("Type", ""),
                "classification": cls,
                "description": desc,
            })
        return pd.DataFrame(rows)

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
        self._sync_from_aws()
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
            try:
                self.lf.update_data_cells_filter(TableData={
                    "TableCatalogId": self.account_id, "DatabaseName": self.database,
                    "TableName": table, "Name": name,
                    "RowFilter": {"FilterExpression": expr},
                    "ColumnNames": all_cols})
            except Exception:
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
            try:
                self.lf.update_lf_tag(TagKey=key, TagValuesToAdd=[value])
            except Exception:
                pass
        self.lf.add_lf_tags_to_resource(
            Resource=self._table_resource(table),
            LFTags=[{"CatalogId": self.account_id, "TagKey": key, "TagValues": [value]}])

    def grant_by_tag(self, role, key, value) -> None:
        super().grant_by_tag(role, key, value)  # mirror
        try:
            self.lf.create_lf_tag(TagKey=key, TagValues=[value])
        except (self.lf.exceptions.AlreadyExistsException,
                self.lf.exceptions.InvalidInputException):
            try:
                self.lf.update_lf_tag(TagKey=key, TagValuesToAdd=[value])
            except Exception:
                pass
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
        """Re-baseline real Lake Formation: query live permissions/filters/tags and revoke them all."""
        for role in list(self.personas):
            self._revoke_role_in_lf(role)

        # Delete any DataCellsFilters on our tables in Lake Formation
        for t in self.catalog.tables:
            try:
                resp = self.lf.list_data_cells_filter(
                    Table={"CatalogId": self.account_id, "DatabaseName": self.database, "Name": t}
                )
                for dcf in resp.get("DataCellsFilters", []):
                    _safe(lambda dcf=dcf, t=t: self.lf.delete_data_cells_filter(
                        TableCatalogId=self.account_id, DatabaseName=self.database,
                        TableName=t, Name=dcf["Name"]))
            except Exception:
                pass

        # Remove any LF-Tags attached to our tables in Lake Formation
        for t in self.catalog.tables:
            try:
                resp = self.lf.get_resource_lf_tags(
                    CatalogId=self.account_id,
                    Resource=self._table_resource(t),
                    ShowAssignedLFTags=True,
                )
                tags = resp.get("LFTagsOnTable", [])
                if tags:
                    _safe(lambda t=t, tags=tags: self.lf.remove_lf_tags_from_resource(
                        Resource=self._table_resource(t),
                        LFTags=[{"CatalogId": self.account_id,
                                 "TagKey": tg["TagKey"], "TagValues": tg["TagValues"]}
                                for tg in tags]))
            except Exception:
                pass

        super().reset()  # clear mirror

    def _revoke_role_in_lf(self, role: str) -> None:
        """Query live Lake Formation permissions for `role` and revoke every entry."""
        target_arn = self.personas[role]
        try:
            for entry in self._list_all_lf_permissions():
                principal = entry.get("Principal", {})
                if principal.get("DataLakePrincipalIdentifier") != target_arn:
                    continue
                res = entry.get("Resource", {})
                perms = entry.get("Permissions", [])
                if res and perms:
                    _safe(lambda p=principal, r=res, pm=perms: self.lf.revoke_permissions(
                        Principal=p, Resource=r, Permissions=pm))
        except Exception:
            pass

    def grants_summary(self) -> pd.DataFrame:
        """Sync from live Lake Formation before summarizing persona grants."""
        self._sync_from_aws()
        return super().grants_summary()

    def governance_audit(self, contracts_valid: bool | None = None) -> pd.DataFrame:
        """Sync live Glue & Lake Formation state before running the platform governance audit."""
        self._sync_from_aws()
        return super().governance_audit(contracts_valid=contracts_valid)

    # ----------------------------------------------------------------------- #
    # MP7 verification — assume each persona role and query via Glue / Athena
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

        # Metadata-only DESCRIBE queries check Glue GetTable under the assumed persona role,
        # because Lake Formation DESCRIBE governs Glue catalog metadata access rather than S3/Athena rows.
        if _is_describe(sql):
            table = _table_in_from(sql)
            if table is None:
                raise AccessDenied("metadata query did not name a table")
            # Ensure Lake Formation has granted at least DESCRIBE, SELECT, or a tag grant on `table`
            self._sync_from_aws()
            g = self._grants[role]
            if not (g.describe_only or table in g.table_grants or self._table_has_tag(table, g.tag_grants)):
                raise AccessDenied(f"{role} has no Lake Formation DESCRIBE/SELECT grant on '{table}'")
            try:
                role_glue = sess.client("glue")
                resp = role_glue.get_table(DatabaseName=self.database, Name=table)
                cols = resp["Table"].get("StorageDescriptor", {}).get("Columns", [])
                return pd.DataFrame([
                    {"column": c["Name"], "type": c.get("Type", ""),
                     "classification": c.get("Parameters", {}).get("classification") or "(untagged)",
                     "description": c.get("Comment", "")}
                    for c in cols
                ])
            except Exception as e:
                raise AccessDenied(f"{role}: {e}") from None

        try:
            return wr.athena.read_sql_query(
                sql, database=self.database, workgroup=self.athena_workgroup,
                s3_output=self.results_bucket, boto3_session=sess,
                ctas_approach=False)
        except Exception as e:
            msg = str(e).lower()
            if any(tok in msg for tok in (
                "accessdenied",
                "not authorized",
                "insufficient lake formation permission",
                "permission(s)",
                "column not found",
                "cannot be resolved",
            )):
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
