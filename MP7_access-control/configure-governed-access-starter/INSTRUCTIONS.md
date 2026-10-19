# Configure Governed Access in Lake Formation

**Trailhead Provisions** stores customer PII in a shared lake. Different roles need different
slices of the `customer` table, and "just trust people" is not a control. Using **AWS Lake
Formation**, configure fine-grained access for four personas, then **prove enforcement by
querying as each persona in Amazon Athena**.

## Your task

In `exercise.ipynb`, apply the Lake Formation grants so each persona ends up with exactly this
access on `customer`, then run the provided verification:

| Persona | Intended access | LF mode |
|---|---|---|
| `co_marketing_analyst` | Customer minus `email`, `phone` | column-level |
| `co_cs_rep` | All columns, rows where `region='EU'` only | row-level |
| `co_data_steward` | Everything tagged `governed=true` | tag-based (LF-TBAC) |
| `co_auditor` | Schema + tags only; no row data | metadata-only |

## Requirements

Your completed `exercise.ipynb` must:

- Apply a **column-level** grant (analyst), a **row-level** filter (cs_rep), a **tag-based**
  grant (steward), and a **metadata-only** grant (auditor), using the provided helpers.
- Run the provided `verify_step7(gc)` and show **every check reads PASS** (the verification
  assumes each persona role and queries via Athena).
- Write a short **policy spec** justifying each grant in least-privilege terms.

## Provided files

- `exercise.ipynb` — your working notebook (complete the `TODO` and write the policy spec).
- `governance_toolkit.py`, `aws_backend.py`, `seed_data.py` — provided tooling, live AWS
  backend, and the Trailhead dataset. Do not edit these.

## Running it

```
pip install pandas jsonschema boto3 awswrangler jupyterlab
export CARDINAL_LF_LIVE=1        # in the lab; uses live Lake Formation + Athena (else local fallback)
jupyter lab exercise.ipynb
```

## Section 5: Infrastructure as Code (Terraform Reading)

After completing the hands-on grants, open `terraform/governed-data-product/main.tf`. This
is a **read-only** Terraform module that packages a governed data product declaratively.

Answer the 4 questions in the notebook:
1. Identify the governance chain (S3 → Glue → Lake Formation → IAM)
2. Explain why the consumer has no direct S3 data access
3. Connect the Terraform `excluded_column_names` to your hands-on column grant
4. Compose a module call for a new data product with PII

**Key insight**: The Terraform module does exactly what you did by hand — but repeatably,
version-controlled, and auditable. The capstone project will ask you to read and explain
an identical module.
