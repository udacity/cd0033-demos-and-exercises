# Run Governance as an Operation

**Trailhead Provisions** treats governance as ongoing operations. A single audit rolls up every
signal across the platform — missing catalog metadata, data-quality failures, lineage gaps, a
cross-domain consent conflict, and **access-control gaps** on PII tables. As the governance lead,
run the audit, **remediate what is fixable in AWS, and re-run until the platform is compliant.**

> This exercise runs against **live AWS Glue, Lake Formation, and Amazon Athena** (no local fallback).

## Your task

In `exercise.ipynb`, first run **Step 0: Connect to your Cloud Lab** to authenticate and seed the
Glue Data Catalog, S3 tables, and Lake Formation enforcement. Then run the provided `governance_audit()`
and complete each section:

- **Remediate the catalog gaps in AWS Glue** (`set_table_metadata`, `tag_column`) using the
  appropriate domain owners (`orders-team@trailhead.example`, `marketing@trailhead.example`),
  retention periods, and column classifications (`PII`, `SENSITIVE`, `PUBLIC`) so every
  `missing_metadata` finding is closed.
- **Remediate the access-control gaps in AWS Lake Formation** — bring every PII-bearing table
  (`customer` and `campaign_membership`) under governance (`assign_tag(..., 'governed', 'true')`
  and `grant_by_tag('co_data_steward', 'governed', 'true')`) so every `access_control_gap`
  finding is closed, and display `gc.grants_summary()`.
- **Re-run the audit** and show `missing_metadata` and `access_control_gap` are both zero.
- Write an **operations write-up** (Section 5), a **Governance Dashboard Specification** (Section 6),
  a **New-Domain Onboarding Checklist** (Section 7), and a **Mini Architect's Brief** (Section 8).

## Requirements

Your completed `exercise.ipynb` must:

- Run **Step 0: Connect to your Cloud Lab** and verify `lf_backend()` reports `live` (`AwsGovernedCatalog`).
- Show the initial audit, its signal breakdown, and the initial `access_control_gap` objects (`['customer (PII table, no Lake Formation restriction)']`).
- Drive `missing_metadata` and `access_control_gap` to **zero**, verified by a re-audit and `gc.grants_summary()`.
- Explain why classifying untagged PII columns in Step 2 surfaced a new access-control gap on `campaign_membership` (taking `access_control_gap` from `1` to `2` before Step 3 cleared both to `0`).
- Correctly identify the remaining findings (`quality_violation`, `consent_conflict`, `missing_lineage`) as **recurring SLOs**, state **one concrete SLO target per remaining signal category**, clearly separate **current instance remediation** (e.g., ticketing `order_returns` and `campaign` to Platform Engineering, or syncing the consent store) from **recurring operational SLO monitoring**, and describe how you'd operate the audit continuously.
- Complete the **Governance Dashboard Specification** (Section 6), **New-Domain Onboarding Checklist** (Section 7), and **Cross-Module Synthesis — Mini Architect's Brief** (Section 8).

## Provided files

- `exercise.ipynb` — your working notebook (complete the `TODO`s and written sections).
- `governance_toolkit.py`, `aws_backend.py`, `seed_data.py`, `setup_aws.py` — provided tooling, live AWS
  backend, Cloud Lab bootstrapper, and the Trailhead dataset. Do not edit these.
- `SUPPLEMENT-exceeds-automation.md` — optional stretch prompt on governance pipeline automation.

## Running it

1. Open `exercise.ipynb` in JupyterLab:
   ```bash
   pip install pandas jsonschema boto3 awswrangler jupyterlab
   jupyter lab exercise.ipynb
   ```
2. Run **Step 0: Connect to your Cloud Lab** at the top of the notebook. This sets `CARDINAL_LF_LIVE=1`
   and runs `setup_aws.main()` if the `trailhead` Glue database is not yet seeded (also revoking
   default `IAMAllowedPrincipals` grants so Lake Formation enforces fine-grained permissions).
