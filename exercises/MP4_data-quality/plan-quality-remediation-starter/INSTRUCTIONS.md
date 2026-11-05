# Interpret Quality Results & Plan Remediation

**Trailhead Provisions**' quality suite reports expectation failures across six dimensions. Each
failure needs a decision, not just a number.

## Your task

In `exercise.ipynb`, run **Step 0: Connect to your Cloud Lab** first to seed and connect to your
live AWS Glue Data Catalog and Amazon Athena (`trailhead`), then run the provided quality suite,
inspect the platform's target contract SLOs (`gc.contract_slos()`), classify each failure, and
write a prioritized remediation plan.

## Requirements

- Map every failing `table.column` to a strategy: **source** / **downstream** / **quarantine**.
- Write a **prioritized plan**:
  - Identify which failures cause active GDPR or CSRD regulatory harm and must be **quarantined** first (`Priority 1`).
  - Tie every remediation tier to the target contract SLOs from `gc.contract_slos()`.
  - Flag recurring drift (`campaign_membership.mkt_consent` consistency and `shipment.carbon_kg` unit accuracy) as ongoing SLOs.

## Provided files

- `exercise.ipynb` — your working notebook.
- `governance_toolkit.py` (provides `make_catalog`, `run_quality_suite`, `contract_slos`), `aws_backend.py`, `setup_aws.py`, `seed_data.py` — provided; do not edit.

## Running it

1. Open `exercise.ipynb` in your Cloud Lab JupyterLab workspace.
2. Run **Step 0: Connect to your Cloud Lab** at the top of the notebook to verify your AWS credentials and seed the live AWS Glue Data Catalog (`trailhead`) if needed.
3. Run the notebook top-to-bottom (`lf_backend()` reports `live` -> `AwsGovernedCatalog`).
