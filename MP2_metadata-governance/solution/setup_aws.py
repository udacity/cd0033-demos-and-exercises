"""
setup_aws.py — PROVISIONER-SIDE seeder for the live Cardinal Outfitters platform.

Run ONCE per Vocareum/AWS account by the platform team (NOT by learners) to stand up the
real resources the live backend (aws_backend.py) expects:

    1. an S3 data location with one prefix per table (parquet),
    2. an AWS Glue database + tables whose metadata reproduces the SAME deliberate
       governance gaps as the local seed (so MP2 has real gaps to find and fix),
    3. registration of the S3 location with Lake Formation.

It does NOT create the four persona IAM roles or assign the Lake Formation Data Lake
Administrator — those are provisioned by Vocareum per environment-provisioning-request.md.

The gap structure is canonical in seed_data._build_catalog(); this script mirrors it into
Glue so local and live backends audit identically.

    python3 setup_aws.py            # uses env config below
    CARDINAL_GLUE_DATABASE=cardinal CARDINAL_S3_DATA=s3://<bucket>/cardinal python3 setup_aws.py

NOTE: build-to-spec; not executed outside a provisioned account (# pragma: no cover).
"""
from __future__ import annotations  # pragma: no cover

import os

import pandas as pd

import seed_data


def _cfg(key: str, default: str) -> str:
    return os.environ.get(key, default)


def main() -> None:
    import awswrangler as wr
    import boto3

    region = _cfg("CARDINAL_AWS_REGION", "us-east-1")
    session = boto3.Session(region_name=region)
    glue = session.client("glue")
    lf = session.client("lakeformation")
    account_id = session.client("sts").get_caller_identity()["Account"]

    conn, catalog = seed_data.build(":memory:")
    # Derive the database name from whichever seed is present (cardinal capstone or
    # trailhead exercises), so this one script seeds either environment unchanged.
    database = _cfg("CARDINAL_GLUE_DATABASE", catalog.database)
    s3_data = _cfg("CARDINAL_S3_DATA", f"s3://{account_id}-{database}-data").rstrip("/")

    # 1a. S3 bucket (create if it doesn't exist)
    s3 = session.client("s3")
    bucket_name = s3_data.split("://", 1)[1].split("/")[0]
    try:
        s3.head_bucket(Bucket=bucket_name)
        print(f"S3 bucket {bucket_name!r} already exists")
    except s3.exceptions.ClientError:
        create_kw = {"Bucket": bucket_name}
        if region != "us-east-1":
            create_kw["CreateBucketConfiguration"] = {"LocationConstraint": region}
        s3.create_bucket(**create_kw)
        print(f"created S3 bucket {bucket_name!r} in {region}")

    # 1b. database
    try:
        glue.create_database(DatabaseInput={"Name": database,
                                            "Description": "Cardinal Outfitters governed platform"})
        print(f"created Glue database {database!r}")
    except glue.exceptions.AlreadyExistsException:
        print(f"Glue database {database!r} already exists")

    # 2. tables: write parquet + register, then stamp the deliberate-gap metadata
    for name, tm in catalog.tables.items():
        df = pd.read_sql_query(f"SELECT * FROM {name}", conn)
        path = f"{s3_data}/{name}/"
        wr.s3.to_parquet(df=df, path=path, dataset=True, mode="overwrite",
                         database=database, table=name, boto3_session=session)
        _apply_catalog_metadata(glue, database, name, tm)
        gaps = [a for a in ("owner", "classification", "retention") if getattr(tm, a) is None]
        untagged = [c.name for c in tm.columns if c.classification is None]
        print(f"  {name:22} rows={len(df):5d}  table-gaps={gaps}  untagged-cols={untagged}")

    # 3. register the S3 location with Lake Formation (so LF, not raw S3/IAM, mediates reads)
    try:
        lf.register_resource(ResourceArn=f"arn:aws:s3:::{s3_data.split('://',1)[1]}",
                             UseServiceLinkedRole=True)
        print(f"registered {s3_data} with Lake Formation")
    except lf.exceptions.AlreadyExistsException:
        print(f"{s3_data} already registered with Lake Formation")

    print("\nDone. Confirm: IAMAllowedPrincipals default grants are OFF on this database "
          "(provisioning-request §7), persona roles exist, and the notebook role is LF admin.")


def _apply_catalog_metadata(glue, database: str, name: str, tm) -> None:
    """Set ONLY the non-gap parameters, preserving seed_data's deliberate gaps in Glue."""
    resp = glue.get_table(DatabaseName=database, Name=name)
    ti = {k: resp["Table"][k] for k in
          ("Name", "Description", "StorageDescriptor", "PartitionKeys", "TableType", "Parameters")
          if k in resp["Table"]}
    params = ti.setdefault("Parameters", {})
    params["domain"] = tm.domain
    for attr in ("owner", "classification", "retention"):
        val = getattr(tm, attr)
        if val is not None:                       # leave gaps unset on purpose
            params[attr] = val
    for col in ti.get("StorageDescriptor", {}).get("Columns", []):
        meta = tm.column(col["Name"])
        if meta is not None and meta.classification is not None:
            col.setdefault("Parameters", {})["classification"] = meta.classification
    glue.update_table(DatabaseName=database, TableInput=ti)


if __name__ == "__main__":
    main()
