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
