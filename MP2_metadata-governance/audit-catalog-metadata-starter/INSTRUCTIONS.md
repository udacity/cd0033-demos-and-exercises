# Audit & Remediate Catalog Metadata for the Customer & Marketing Domains

**Trailhead Provisions** is a federated retail platform — four domain teams, one shared **AWS
Glue Data Catalog**, no enforced metadata standards. A **GDPR audit notice** has arrived. As the
governance lead, use the catalog as a control surface: find where required governance metadata is
missing for the two domains that hold personal data, **fix the gaps directly in the live AWS Glue
Data Catalog**, verify with a re-audit, and note where those domains disagree with others about
shared concepts.

## Your task

In `exercise.ipynb`, run **Step 0: Connect to your Cloud Lab** first to seed and connect to your
live AWS Glue Data Catalog (`trailhead`). Then audit the **Customer Identity & Loyalty** and
**Marketing & Campaigns** domains in AWS Glue, inspect the column descriptions to see what each
column stores, **remediate every gap**, re-audit to confirm, and write a reconciliation memo.

## Requirements

Your completed `exercise.ipynb` must:

- Run the provided `catalog_audit()` and narrow the results to the two domains above.
- Inspect the column schemas and descriptions (`gc.describe("customer")` and
  `gc.describe("campaign_membership")`) so you can see which columns store personal data.
- **Remediate every gap** in those domains by writing metadata back to the live AWS Glue catalog with
  `set_table_metadata(...)` and `tag_column(...)` using the platform's valid classification taxonomy
  (`PII`, `SENSITIVE`, `PUBLIC`), then **re-run the audit** to show the two domains are clean
  (0 remaining gaps and personal-data columns tagged `PII`).
- In your memo, identify every **untagged PII column** you fixed and explain why an untagged
  personal-data column is the top GDPR risk.
- Identify the **table-level gaps** (missing `owner`, `classification`, or `retention`) you
  remediated and state what each missing control meant operationally.
- Identify the **cross-domain semantic conflict(s)** that involve these domains.
- Recommend the **metadata standards** the platform should enforce so the gaps don't recur.

## Provided files

- `exercise.ipynb` — your working notebook (complete the `TODO`s and write the memo).
- `governance_toolkit.py`, `aws_backend.py`, `setup_aws.py`, `seed_data.py` — provided live AWS
  governance toolkit and Trailhead dataset seeder. Do not edit these.

## Running it

1. Open `exercise.ipynb` in your Cloud Lab JupyterLab workspace.
2. Run **Step 0: Connect to your Cloud Lab** at the top of the notebook to verify your AWS credentials and seed the live AWS Glue Data Catalog (`trailhead`) if needed.
3. Run the notebook top-to-bottom (`lf_backend()` reports `live` -> `AwsGovernedCatalog`).
