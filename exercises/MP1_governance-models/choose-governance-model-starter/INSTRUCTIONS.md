# Choose a Governance Model for Trailhead Provisions

**Trailhead Provisions** grew by acquisition into four domain teams sharing an AWS data platform:
- **E-commerce Orders** (led by the **E-commerce Orders Lead**)
- **Customer Identity & Loyalty** (led by the **Customer Identity Lead**)
- **Inventory & Fulfillment** (led by the **Inventory & Fulfillment Lead**)
- **Marketing & Campaigns** (led by the **Marketing & Campaigns Lead**)

Alongside the four domain leads, the organization has three cross-cutting roles:
- A **Central Governance Lead** (owns enterprise data policy, classification taxonomy, and access-control baselines)
- A shared **Platform Engineering** team (manages pipeline infrastructure and OpenLineage instrumentation)
- A Finance-appointed **CSRD Reporting Owner** (owns sustainability disclosure definitions and audit readiness)

Each domain team owns its pipelines and definitions, but a **GDPR audit** and a **CSRD sustainability mandate** create obligations that cross every domain. Decide how to govern.

## Your task

In `exercise.ipynb`, run **Step 0: Connect to your Cloud Lab** first to seed and connect to your live AWS Glue Data Catalog, then decide a governance model and produce the three deliverables below.

## Requirements

- A **governance-model decision** (centralized / decentralized / federated), justified from
  Trailhead's domain autonomy AND its GDPR/CSRD exposure, naming which decisions stay central and
  which side each role sits on (central/platform vs. domain).
- A **RACI** across the four domains and cross-cutting roles with **exactly one single Accountable (`A`) individual** per governance function, plus the enforcement authority and an escalation path.
- A **Mermaid topology** showing the central governance core, the four domains, and the key cross-domain flows (consent routed through the central consent standard, and order → carbon → CSRD report).

## Provided files

- `exercise.ipynb` — your working notebook.
- `governance_toolkit.py`, `aws_backend.py`, `setup_aws.py`, `seed_data.py` — provided live AWS governance toolkit and dataset seeder; do not edit.

## Running it

1. Open `exercise.ipynb` in your Cloud Lab JupyterLab workspace.
2. Run **Step 0: Connect to your Cloud Lab** at the top of the notebook to verify your AWS credentials and seed the live AWS Glue Data Catalog (`trailhead`) if needed.
3. Run the remaining cells top-to-bottom and complete sections `1a`, `1b`, and `1c`.
