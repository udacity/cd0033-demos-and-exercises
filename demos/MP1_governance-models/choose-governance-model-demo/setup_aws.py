"""
setup_aws.py — Self-contained AWS seeder for Veridian Health's Medallion Lakehouse (`veridian_lakehouse`).

Works in BOTH a personal AWS account and a pre-provisioned Cloud Lab. Running
`python3 setup_aws.py` (or running the Step 0 cell in any demo notebook) provisions and seeds:

    1. S3 Medallion data bucket (`<account>-veridian-lakehouse`) and S3 Athena results
       bucket (`<account>-veridian-athena-results`),
    2. Amazon Athena workgroup `veridian` configured with the results bucket output location,
    3. AWS Lake Formation Data Lake Administrator registration for your caller IAM user/role
       and disabling of `IAMAllowedPrincipals` default grants,
    4. The four Veridian Health persona IAM roles (`vh_clinical_researcher`,
       `vh_eu_care_coordinator`, `vh_him_steward`, `vh_hipaa_compliance_auditor`) with
       Athena + Glue + Lake Formation data-access permissions and STS assume-role trust,
    5. AWS Glue database `veridian_lakehouse` + Bronze/Silver tables written as Parquet in S3,
       stamped with the deliberate governance gaps from `veridian_seed._build_catalog()`,
    6. Lake Formation registration of the S3 data bucket and admin SELECT/ALL grants for
       the caller principal so admin Athena queries (`lh.query(...)`) succeed immediately.
"""
from __future__ import annotations  # pragma: no cover

import json
import os
import time

import veridian_seed

PERSONA_ROLES = [
    "vh_clinical_researcher",
    "vh_eu_care_coordinator",
    "vh_him_steward",
    "vh_hipaa_compliance_auditor",
]


def _cfg(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _caller_lf_principal_arn(caller_arn: str) -> str:
    """Convert an STS assumed-role ARN (`arn:aws:sts::ACCT:assumed-role/ROLE/SESSION`) into
    the IAM role ARN (`arn:aws:iam::ACCT:role/ROLE`) required by Lake Formation."""
    if ":assumed-role/" in caller_arn:
        parts = caller_arn.split(":assumed-role/", 1)
        acct = parts[0].split(":")[-1]
        role_and_session = parts[1].split("/")
        # Preserve AWS SSO reserved path if present, else standard role path
        if role_and_session[0].startswith("AWSReservedSSO_"):
            return f"arn:aws:iam::{acct}:role/aws-reserved/sso.amazonaws.com/{role_and_session[0]}"
        return f"arn:aws:iam::{acct}:role/{role_and_session[0]}"
    return caller_arn


def _ensure_bucket(s3, bucket_name: str, region: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket_name)
    except Exception:
        create_kw = {"Bucket": bucket_name}
        if region != "us-east-1":
            create_kw["CreateBucketConfiguration"] = {"LocationConstraint": region}
        s3.create_bucket(**create_kw)
        print(f"created S3 bucket {bucket_name!r} in {region}")


def _detect_s3_lakehouse_bucket(s3, account_id: str, database: str, region: str) -> str:
    explicit = os.environ.get("VERIDIAN_S3_DATA")
    if explicit:
        return explicit.rstrip("/")

    target_bucket = f"{account_id}-veridian-lakehouse"
    _ensure_bucket(s3, target_bucket, region)
    return f"s3://{target_bucket}"


def _ensure_athena_workgroup_and_results(athena, s3, account_id: str, region: str) -> tuple[str, str]:
    """Ensure `<account>-veridian-athena-results` S3 bucket and `veridian` Athena workgroup exist."""
    results_bucket = f"{account_id}-veridian-athena-results"
    _ensure_bucket(s3, results_bucket, region)
    results_s3 = f"s3://{results_bucket}/"

    wg_name = os.environ.get("VERIDIAN_ATHENA_WORKGROUP", "veridian")
    try:
        athena.get_work_group(WorkGroup=wg_name)
    except Exception:
        try:
            athena.create_work_group(
                Name=wg_name,
                Configuration={
                    "ResultConfiguration": {"OutputLocation": results_s3},
                    "EnforceWorkGroupConfiguration": False,
                },
                Description="Veridian Health Medallion Lakehouse demo workgroup",
            )
            print(f"created Athena workgroup {wg_name!r} -> {results_s3}")
        except Exception:
            wg_name = "primary"
    return wg_name, results_s3


def _ensure_persona_iam_roles(iam, account_id: str, results_bucket: str) -> None:
    """Ensure the 4 `vh_*` IAM roles exist with Athena, Glue read, Lake Formation, and S3 results access."""
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Sid": "AllowAccountAssumeRole",
            "Effect": "Allow",
            "Principal": {"AWS": f"arn:aws:iam::{account_id}:root"},
            "Action": "sts:AssumeRole",
        }],
    }
    inline_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "AthenaQueryAccess",
                "Effect": "Allow",
                "Action": [
                    "athena:StartQueryExecution",
                    "athena:GetQueryResults",
                    "athena:GetQueryExecution",
                    "athena:GetWorkGroup",
                ],
                "Resource": "*",
            },
            {
                "Sid": "GlueCatalogReadAccess",
                "Effect": "Allow",
                "Action": ["glue:Get*"],
                "Resource": "*",
            },
            {
                "Sid": "LakeFormationDataAccess",
                "Effect": "Allow",
                "Action": ["lakeformation:GetDataAccess"],
                "Resource": "*",
            },
            {
                "Sid": "AthenaResultsBucketAccess",
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:GetBucketLocation",
                    "s3:ListBucket",
                ],
                "Resource": [
                    f"arn:aws:s3:::{results_bucket}",
                    f"arn:aws:s3:::{results_bucket}/*",
                ],
            },
        ],
    }
    created_any = False
    for role_name in PERSONA_ROLES:
        try:
            iam.get_role(RoleName=role_name)
        except iam.exceptions.NoSuchEntityException:
            try:
                iam.create_role(
                    RoleName=role_name,
                    AssumeRolePolicyDocument=json.dumps(trust_policy),
                    Description=f"Veridian Health Medallion persona role ({role_name})",
                )
                created_any = True
                print(f"created IAM persona role {role_name!r}")
            except Exception as e:
                print(f"note: could not create IAM role {role_name!r} ({e})")
                continue
        except Exception:
            continue

        try:
            iam.put_role_policy(
                RoleName=role_name,
                PolicyName="VeridianPersonaAccess",
                PolicyDocument=json.dumps(inline_policy),
            )
        except Exception:
            pass

    if created_any:
        # Brief pause so newly created IAM roles propagate for Lake Formation & STS
        time.sleep(5)


def _configure_lake_formation_admin_and_revoke_defaults(
    lf, account_id: str, caller_principal_arn: str, database: str, tables: list[str]
) -> None:
    """Register the caller as a Lake Formation Data Lake Admin and remove IAMAllowedPrincipals defaults."""
    iam_allowed = {"DataLakePrincipalIdentifier": "IAM_ALLOWED_PRINCIPALS"}
    try:
        settings = lf.get_data_lake_settings()["DataLakeSettings"]
        admins = settings.get("DataLakeAdmins", [])
        admin_ids = {a.get("DataLakePrincipalIdentifier") for a in admins}
        if caller_principal_arn not in admin_ids:
            admins.append({"DataLakePrincipalIdentifier": caller_principal_arn})
        settings["DataLakeAdmins"] = admins
        settings["CreateDatabaseDefaultPermissions"] = []
        settings["CreateTableDefaultPermissions"] = []
        lf.put_data_lake_settings(DataLakeSettings=settings)
    except Exception:
        pass

    try:
        lf.revoke_permissions(
            Principal=iam_allowed,
            Resource={"Database": {"CatalogId": account_id, "Name": database}},
            Permissions=["ALL"],
        )
    except Exception:
        pass

    for t in tables:
        for perms in (["ALL"], ["SELECT", "DESCRIBE", "ALTER", "DROP", "INSERT", "DELETE"]):
            try:
                lf.revoke_permissions(
                    Principal=iam_allowed,
                    Resource={"Table": {"CatalogId": account_id, "DatabaseName": database, "Name": t}},
                    Permissions=perms,
                )
            except Exception:
                pass


def _grant_caller_admin_table_access(
    lf, account_id: str, caller_principal_arn: str, database: str, tables: list[str]
) -> None:
    """Grant the caller principal Lake Formation permissions on the database and tables so
    admin Athena queries (`lh.query(...)`) work seamlessly after IAMAllowedPrincipals is removed."""
    principal = {"DataLakePrincipalIdentifier": caller_principal_arn}
    try:
        lf.grant_permissions(
            Principal=principal,
            Resource={"Database": {"CatalogId": account_id, "Name": database}},
            Permissions=["ALL"],
        )
    except Exception:
        pass

    for t in tables:
        try:
            lf.grant_permissions(
                Principal=principal,
                Resource={"Table": {"CatalogId": account_id, "DatabaseName": database, "Name": t}},
                Permissions=["ALL"],
            )
        except Exception:
            pass


def main() -> None:
    import awswrangler as wr
    import boto3

    region = _cfg("VERIDIAN_AWS_REGION", _cfg("CARDINAL_AWS_REGION", "us-east-1"))
    session = boto3.Session(region_name=region)
    glue = session.client("glue")
    lf = session.client("lakeformation")
    s3 = session.client("s3")
    athena = session.client("athena")
    iam = session.client("iam")
    sts_id = session.client("sts").get_caller_identity()
    account_id = sts_id["Account"]
    caller_principal_arn = _caller_lf_principal_arn(sts_id["Arn"])

    tables_dfs, catalog = veridian_seed.build()
    database = _cfg("VERIDIAN_GLUE_DATABASE", catalog.database)

    # 1. Ensure S3 data bucket, S3 Athena results bucket, and Athena workgroup exist
    s3_root = _detect_s3_lakehouse_bucket(s3, account_id, database, region)
    bucket_name = s3_root.split("://", 1)[1].split("/")[0]
    results_bucket = f"{account_id}-veridian-athena-results"
    _ensure_athena_workgroup_and_results(athena, s3, account_id, region)

    # 2. Ensure the 4 healthcare persona IAM roles exist (for MP7 / MP9 live STS & LF grants)
    _ensure_persona_iam_roles(iam, account_id, results_bucket)

    # 3. Register caller as Lake Formation Admin and disable IAMAllowedPrincipals defaults
    _configure_lake_formation_admin_and_revoke_defaults(
        lf, account_id, caller_principal_arn, database, []
    )

    # 4. Create Glue database
    try:
        glue.create_database(DatabaseInput={
            "Name": database,
            "Description": f"{veridian_seed.COMPANY} Medallion Lakehouse (Bronze / Silver / Gold)",
        })
        print(f"created Glue database {database!r}")
    except glue.exceptions.AlreadyExistsException:
        print(f"Glue database {database!r} already exists")

    # 5. Register the S3 data bucket with Lake Formation
    try:
        lf.register_resource(ResourceArn=f"arn:aws:s3:::{bucket_name}", UseServiceLinkedRole=True)
        print(f"registered s3://{bucket_name} with Lake Formation")
    except Exception:
        pass

    # 6. Write Bronze/Silver tables to zone-partitioned S3 prefixes and stamp Glue metadata
    for name, tm in catalog.tables.items():
        df = tables_dfs[name]
        path = f"{s3_root}/{tm.zone}/{name}/"
        wr.s3.to_parquet(df=df, path=path, dataset=True, mode="overwrite",
                         database=database, table=name, boto3_session=session)
        _apply_catalog_metadata(glue, database, name, tm)
        gaps = [a for a in ("steward", "sensitivity", "retention_policy") if getattr(tm, a) is None]
        untagged = [c.name for c in tm.columns if c.sensitivity is None]
        print(f"  [{tm.zone:6}] {name:30} rows={len(df):4d}  table-gaps={gaps}  untagged-cols={untagged}")

    # 7. Revoke IAMAllowedPrincipals on newly created tables & grant caller admin access
    _configure_lake_formation_admin_and_revoke_defaults(
        lf, account_id, caller_principal_arn, database, list(catalog.tables)
    )
    _grant_caller_admin_table_access(
        lf, account_id, caller_principal_arn, database, list(catalog.tables)
    )
    print(f"\nDone. Medallion Lakehouse {database!r} seeded in {s3_root} with Lake Formation enforcement.")


def _apply_catalog_metadata(glue, database: str, name: str, tm) -> None:
    """Stamp Medallion zone, domain, and non-gap stewardship/sensitivity/retention parameters in Glue."""
    resp = glue.get_table(DatabaseName=database, Name=name)
    ti = {k: resp["Table"][k] for k in
          ("Name", "Description", "StorageDescriptor", "PartitionKeys", "TableType", "Parameters")
          if k in resp["Table"]}
    params = ti.setdefault("Parameters", {})
    for k in ("steward", "sensitivity", "retention_policy"):
        params.pop(k, None)
    params["medallion_zone"] = tm.zone
    params["domain"] = tm.domain
    for attr in ("steward", "sensitivity", "retention_policy"):
        val = getattr(tm, attr)
        if val is not None:
            params[attr] = val
    for col in ti.get("StorageDescriptor", {}).get("Columns", []):
        col_params = col.setdefault("Parameters", {})
        col_params.pop("sensitivity", None)
        meta = tm.column(col["Name"])
        if meta is not None and meta.sensitivity is not None:
            col_params["sensitivity"] = meta.sensitivity
    glue.update_table(DatabaseName=database, TableInput=ti)


if __name__ == "__main__":
    main()
