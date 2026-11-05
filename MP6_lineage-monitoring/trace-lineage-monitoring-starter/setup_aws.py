"""
setup_aws.py — Cloud Lab seeder for the live Trailhead / Cardinal governed platform.

Creates / refreshes the real AWS resources the live backend (aws_backend.py) uses:

    1. an S3 data location with one prefix per table (parquet),
    2. an AWS Glue database + tables whose metadata reproduces the deliberate
       governance gaps in seed_data._build_catalog() (so MP2/MP9 have real gaps to fix),
    3. registration of the S3 location with Lake Formation,
    4. disabling Lake Formation IAMAllowedPrincipals default grants on the database
       and tables so Lake Formation mediates all table access.

Can be invoked from the CLI (`python3 setup_aws.py`) or directly from a notebook's
Step 0 cell (`import setup_aws; setup_aws.main()`).
"""
from __future__ import annotations  # pragma: no cover

import os

import pandas as pd

import seed_data


def _cfg(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _detect_s3_data_bucket(s3, account_id: str, database: str, region: str) -> str:
    """Resolve the S3 data location: honour CARDINAL_S3_DATA, else reuse an existing lab
    bucket (<account>-<database>-data or <account>-cardinal-data), else create one."""
    explicit = os.environ.get("CARDINAL_S3_DATA")
    if explicit:
        return explicit.rstrip("/")

    candidates = [
        f"{account_id}-{database}-data",
        f"{account_id}-cardinal-data",
        f"{account_id}-trailhead-data",
    ]
    for b in dict.fromkeys(candidates):
        try:
            s3.head_bucket(Bucket=b)
            # If sharing the cardinal-data bucket for trailhead, namespace by database
            prefix = f"/{database}" if (b.endswith("-cardinal-data") and database != "cardinal") else ""
            return f"s3://{b}{prefix}"
        except Exception:
            continue

    target_bucket = f"{account_id}-{database}-data"
    create_kw = {"Bucket": target_bucket}
    if region != "us-east-1":
        create_kw["CreateBucketConfiguration"] = {"LocationConstraint": region}
    s3.create_bucket(**create_kw)
    print(f"created S3 bucket {target_bucket!r} in {region}")
    return f"s3://{target_bucket}"


def _revoke_iam_allowed_principals(lf, account_id: str, database: str, tables: list[str]) -> None:
    """Ensure IAMAllowedPrincipals has no default or standing grants on the database/tables."""
    iam_allowed = {"DataLakePrincipalIdentifier": "IAM_ALLOWED_PRINCIPALS"}
    try:
        settings = lf.get_data_lake_settings()["DataLakeSettings"]
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
                    Resource={"Table": {"CatalogId": account_id,
                                        "DatabaseName": database, "Name": t}},
                    Permissions=perms,
                )
            except Exception:
                pass


def main() -> None:
    import awswrangler as wr
    import boto3

    region = _cfg("CARDINAL_AWS_REGION", "us-east-1")
    session = boto3.Session(region_name=region)
    glue = session.client("glue")
    lf = session.client("lakeformation")
    s3 = session.client("s3")
    account_id = session.client("sts").get_caller_identity()["Account"]

    conn, catalog = seed_data.build(":memory:")
    database = _cfg("CARDINAL_GLUE_DATABASE", catalog.database)
    s3_data = _detect_s3_data_bucket(s3, account_id, database, region)
    bucket_name = s3_data.split("://", 1)[1].split("/")[0]

    # 0. Disable Lake Formation default IAMAllowedPrincipals grants before creating tables
    _revoke_iam_allowed_principals(lf, account_id, database, [])

    # 1. Glue database
    try:
        glue.create_database(DatabaseInput={
            "Name": database,
            "Description": f"{seed_data.COMPANY if hasattr(seed_data, 'COMPANY') else 'Governed'} retail data platform",
        })
        print(f"created Glue database {database!r}")
    except glue.exceptions.AlreadyExistsException:
        print(f"Glue database {database!r} already exists")

    # 2. Register the S3 bucket with Lake Formation so LF mediates reads
    try:
        lf.register_resource(ResourceArn=f"arn:aws:s3:::{bucket_name}",
                             UseServiceLinkedRole=True)
        print(f"registered s3://{bucket_name} with Lake Formation")
    except Exception:
        pass

    # 3. Tables: write parquet + register in Glue, then stamp deliberate-gap metadata
    for name, tm in catalog.tables.items():
        df = pd.read_sql_query(f"SELECT * FROM {name}", conn)
        path = f"{s3_data}/{name}/"
        wr.s3.to_parquet(df=df, path=path, dataset=True, mode="overwrite",
                         database=database, table=name, boto3_session=session)
        _apply_catalog_metadata(glue, database, name, tm)
        gaps = [a for a in ("owner", "classification", "retention") if getattr(tm, a) is None]
        untagged = [c.name for c in tm.columns if c.classification is None]
        print(f"  {name:22} rows={len(df):5d}  table-gaps={gaps}  untagged-cols={untagged}")

    # 4. Revoke any IAMAllowedPrincipals permissions on the database and newly created tables
    _revoke_iam_allowed_principals(lf, account_id, database, list(catalog.tables))
    print(f"\nDone. Glue database {database!r} seeded in {s3_data} with Lake Formation enforcement enabled.")


def _apply_catalog_metadata(glue, database: str, name: str, tm) -> None:
    """Set ONLY the non-gap parameters, preserving seed_data's deliberate gaps in Glue."""
    resp = glue.get_table(DatabaseName=database, Name=name)
    ti = {k: resp["Table"][k] for k in
          ("Name", "Description", "StorageDescriptor", "PartitionKeys", "TableType", "Parameters")
          if k in resp["Table"]}
    params = ti.setdefault("Parameters", {})
    for k in ("owner", "classification", "retention"):
        params.pop(k, None)
    params["domain"] = tm.domain
    for attr in ("owner", "classification", "retention"):
        val = getattr(tm, attr)
        if val is not None:                       # leave gaps unset on purpose
            params[attr] = val
    for col in ti.get("StorageDescriptor", {}).get("Columns", []):
        col_params = col.setdefault("Parameters", {})
        col_params.pop("classification", None)
        meta = tm.column(col["Name"])
        if meta is not None and meta.classification is not None:
            col_params["classification"] = meta.classification
    glue.update_table(DatabaseName=database, TableInput=ti)


if __name__ == "__main__":
    main()
