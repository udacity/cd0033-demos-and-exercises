# Configure Governed Access in Lake Formation

**Trailhead Provisions** stores customer PII in a shared lake. Different roles need different
slices of the `customer` table, and "just trust people" is not a control. Using **AWS Lake
Formation**, configure fine-grained access for four personas, then **prove enforcement by
querying as each persona in Amazon Athena**.

> This exercise runs against **live AWS Glue, Lake Formation, and Amazon Athena**.

## Your task

In `exercise.ipynb`, first run **Step 0: Connect to your Cloud Lab** to authenticate and seed the
Glue Data Catalog, S3 tables, and Lake Formation enforcement. Then apply the Lake Formation grants
so each persona ends up with exactly this access on `customer`, and run the provided verification:

| Persona | Intended access | LF mode |
|---|---|---|
| `co_marketing_analyst` | Customer minus `full_name`, `email`, `phone` | column-level |
| `co_cs_rep` | All columns, rows where `region='EU'` only | row-level |
| `co_data_steward` | Everything tagged `governed=true` | tag-based (LF-TBAC) |
| `co_auditor` | Schema + tags only; no row data | metadata-only |

## Requirements

Your completed `exercise.ipynb` must:

- Run **Step 0: Connect to your Cloud Lab** and verify `lf_backend()` reports `live` (`AwsGovernedCatalog`).
- Apply the four Lake Formation grants using the provided helpers:
  1. **Column-level (`co_marketing_analyst`)**: grant access to `customer` excluding all three PII columns: `exclude=["full_name", "email", "phone"]`.
  2. **Row-level (`co_cs_rep`)**: create a row filter (`region = 'EU'`) on `customer` and grant row-filtered access.
  3. **Tag-based (`co_data_steward`)**: First tag `customer` as `governed=true` with `gc.assign_tag('customer', 'governed', 'true')` (the governed table in this exercise), then grant `co_data_steward` access by tag with `gc.grant_by_tag('co_data_steward', 'governed', 'true')`.
  4. **Metadata-only (`co_auditor`)**: grant `DESCRIBE`-only access with `gc.grant_describe_only('co_auditor')`.
- Run the provided `verify_step7(gc)` and show **every check reads PASS** (the verification
  assumes each persona role via STS and queries via live Glue / Athena).
- Write a short **policy spec** justifying each grant in least-privilege terms.
- Answer the 4 **Infrastructure as Code (Terraform)** reading-comprehension questions in Section 5.

## Provided files

- `exercise.ipynb` — your working notebook (complete the `TODO` cells, policy spec, and Terraform questions).
- `governance_toolkit.py`, `aws_backend.py`, `seed_data.py`, `setup_aws.py` — provided tooling, live AWS
  backend, Cloud Lab bootstrapper, and the Trailhead dataset. Do not edit these.
- `terraform/governed-data-product/main.tf` — provided read-only Terraform module inspected in Section 5.

## Running it

1. Open `exercise.ipynb` in JupyterLab:
   ```bash
   pip install pandas jsonschema boto3 awswrangler jupyterlab
   jupyter lab exercise.ipynb
   ```
2. Run **Step 0: Connect to your Cloud Lab** at the top of the notebook. This sets `CARDINAL_LF_LIVE=1`
   and runs `setup_aws.main()` if the `trailhead` Glue database is not yet seeded (also revoking
   default `IAMAllowedPrincipals` grants so Lake Formation enforces fine-grained permissions).

## Section 5: Infrastructure as Code (Terraform Reading)

After completing the hands-on grants, open `terraform/governed-data-product/main.tf`. This
is a **read-only** Terraform module that packages a governed data product declaratively.

Answer the 4 questions in the notebook:
1. Identify the governance chain (S3 → Glue → Lake Formation → IAM)
2. Explain why the consumer has no direct S3 data access
3. Connect the Terraform `excluded_column_names` to your hands-on column grant
4. Compose a module call for a new data product with PII

**Key insight**: The Terraform module does what you configured by hand — but repeatably,
version-controlled, and auditable. The capstone project will ask you to read and explain
an identical module.
