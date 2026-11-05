"""
setup_aws.py — Cloud Lab seeder for Veridian Health's Medallion Lakehouse (`veridian_lakehouse`).

Seeds the live AWS resources used by the instructor demo notebooks (`demo_toolkit.py` + `aws_backend.py`):

    1. S3 Medallion prefixes (`s3://<bucket>/<zone>/<table>/`) written as Parquet,
    2. AWS Glue database `veridian_lakehouse` + Bronze/Silver tables whose Parameters
       reproduce the deliberate governance gaps in `veridian_seed._build_catalog()`,
    3. Registration of the S3 bucket with AWS Lake Formation,
    4. Revoking `IAMAllowedPrincipals` default grants on the database and tables so
       Lake Formation enforces all access policies.
"""
from __future__ import annotations  # pragma: no cover

import os

import veridian_seed


def _cfg(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _detect_s3_lakehouse_bucket(s3, account_id: str, database: str, region: str) -> str:
    """Resolve the S3 Medallion root: honour VERIDIAN_S3_DATA, else reuse an existing lab
    bucket, else create `<account>-veridian-lakehouse`."""
    explicit = os.environ.get("VERIDIAN_S3_DATA")
    if explicit:
        return explicit.rstrip("/")

    candidates = [
        f"{account_id}-veridian-lakehouse",
        f"{account_id}-{database}-data",
        f"{account_id}-cardinal-data",
        f"{account_id}-trailhead-data",
    ]
    for b in dict.fromkeys(candidates):
        try:
            s3.head_bucket(Bucket=b)
            prefix = f"/{database}" if not b.endswith("-veridian-lakehouse") else ""
            return f"s3://{b}{prefix}"
        except Exception:
            continue

    target_bucket = f"{account_id}-veridian-lakehouse"
    create_kw = {"Bucket": target_bucket}
    if region != "us-east-1":
        create_kw["CreateBucketConfiguration"] = {"LocationConstraint": region}
    s3.create_bucket(**create_kw)
    print(f"created S3 Medallion bucket {target_bucket!r} in {region}")
    return f"s3://{target_bucket}"


def _revoke_iam_allowed_principals(lf, account_id: str, database: str, tables: list[str]) -> None:
    """Remove IAMAllowedPrincipals default grants on `veridian_lakehouse` so Lake Formation enforces access."""
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
                    Resource={"Table": {"CatalogId": account_id, "DatabaseName": database, "Name": t}},
                    Permissions=perms,
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
    account_id = session.client("sts").get_caller_identity()["Account"]

    tables_dfs, catalog = veridian_seed.build()
    database = _cfg("VERIDIAN_GLUE_DATABASE", catalog.database)
    s3_root = _detect_s3_lakehouse_bucket(s3, account_id, database, region)
    bucket_name = s3_root.split("://", 1)[1].split("/")[0]

    # 0. Disable Lake Formation default IAMAllowedPrincipals grants
    _revoke_iam_allowed_principals(lf, account_id, database, [])

    # 1. Glue database
    try:
        glue.create_database(DatabaseInput={
            "Name": database,
            "Description": f"{veridian_seed.COMPANY} Medallion Lakehouse (Bronze / Silver / Gold)",
        })
        print(f"created Glue database {database!r}")
    except glue.exceptions.AlreadyExistsException:
        print(f"Glue database {database!r} already exists")

    # 2. Register the S3 bucket with Lake Formation
    try:
        lf.register_resource(ResourceArn=f"arn:aws:s3:::{bucket_name}", UseServiceLinkedRole=True)
        print(f"registered s3://{bucket_name} with Lake Formation")
    except Exception:
        pass

    # 3. Write Bronze/Silver tables to zone-partitioned S3 prefixes and stamp Glue metadata
    for name, tm in catalog.tables.items():
        df = tables_dfs[name]
        path = f"{s3_root}/{tm.zone}/{name}/"
        wr.s3.to_parquet(df=df, path=path, dataset=True, mode="overwrite",
                         database=database, table=name, boto3_session=session)
        _apply_catalog_metadata(glue, database, name, tm)
        gaps = [a for a in ("steward", "sensitivity", "retention_policy") if getattr(tm, a) is None]
        untagged = [c.name for c in tm.columns if c.sensitivity is None]
        print(f"  [{tm.zone:6}] {name:30} rows={len(df):4d}  table-gaps={gaps}  untagged-cols={untagged}")

    # 4. Revoke IAMAllowedPrincipals on newly created tables
    _revoke_iam_allowed_principals(lf, account_id, database, list(catalog.tables))
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
