# Run Governance as an Operation

**Trailhead Provisions** treats governance as ongoing operations. A single audit rolls up every
signal across the platform — missing catalog metadata, data-quality failures, lineage gaps, a
cross-domain consent conflict, and **access-control gaps** on PII tables. As the governance lead,
run the audit, **remediate what is fixable in AWS, and re-run until the platform is compliant.**

## Your task

In `exercise.ipynb`, run the provided `governance_audit()`, then:

- **Remediate the catalog gaps in AWS Glue** (`set_table_metadata`, `tag_column`) so every
  `missing_metadata` finding is closed.
- **Remediate the access-control gaps in AWS Lake Formation** — bring every PII table under
  governance so every `access_control_gap` finding is closed.
- **Re-run the audit** and show `missing_metadata` and `access_control_gap` are both zero.
- Write an operations write-up covering what you fixed and what remains as ongoing SLOs.

## Requirements

Your completed `exercise.ipynb` must:

- Show the initial audit and its signal breakdown.
- Drive `missing_metadata` and `access_control_gap` to **zero**, verified by a re-audit.
- Correctly identify the remaining findings (quality, consent, lineage) as **recurring SLOs**,
  not one-time fixes, and describe how you'd operate the audit continuously.

## Provided files

- `exercise.ipynb` — your working notebook (complete the `TODO`s and write the write-up).
- `governance_toolkit.py`, `aws_backend.py`, `seed_data.py` — provided tooling, live AWS
  backend, and the Trailhead dataset. Do not edit these.

## Running it

```
pip install pandas jsonschema boto3 awswrangler jupyterlab
export CARDINAL_LF_LIVE=1        # in the lab; uses live Glue + Lake Formation (else local fallback)
jupyter lab exercise.ipynb
```
