# Audit & Remediate Catalog Metadata for the Customer & Marketing Domains

**Trailhead Provisions** is a federated retail platform — four domain teams, one shared **AWS
Glue Data Catalog**, no enforced metadata standards. A **GDPR audit notice** has arrived. As the
governance lead, use the catalog as a control surface: find where required governance metadata is
missing for the two domains that hold personal data, **fix the gaps directly in the catalog**,
verify with a re-audit, and note where those domains disagree with others about shared concepts.

## Your task

Using the provided tooling in `exercise.ipynb`, audit the **Customer Identity & Loyalty** and
**Marketing & Campaigns** domains in AWS Glue, **remediate every gap**, re-audit to confirm, then
write a reconciliation memo.

## Requirements

Your completed `exercise.ipynb` must:

- Run the provided `catalog_audit()` and narrow the results to the two domains above.
- **Remediate every gap** in those domains by writing metadata back to the Glue catalog with
  `set_table_metadata(...)` and `tag_column(...)`, then **re-run the audit** to show the two
  domains are clean (0 remaining gaps).
- In your memo, identify every **untagged PII column** you fixed and explain why an untagged
  personal-data column is the top GDPR risk.
- Identify the **table-level gaps** (missing `owner`, `classification`, or `retention`) you
  remediated and state what each missing control meant operationally.
- Identify the **cross-domain semantic conflict(s)** that involve these domains.
- Recommend the **metadata standards** the platform should enforce so the gaps don't recur.

## Provided files

- `exercise.ipynb` — your working notebook (complete the `TODO`s and write the memo).
- `governance_toolkit.py`, `aws_backend.py`, `seed_data.py` — provided tooling, the live AWS
  backend, and the Trailhead dataset. Do not edit these.

## Running it

```
pip install pandas jsonschema boto3 awswrangler jupyterlab
export CARDINAL_LF_LIVE=1        # in the lab; uses live AWS Glue (else a local fallback)
jupyter lab exercise.ipynb
```

Run the notebook top-to-bottom. `lf_backend()` reports whether you are on live AWS or the local
fallback; the technique and outputs are identical either way.
