# Data Governance Demos & Exercises (cd0033)

This repository is organized into two top-level directories across all nine modules (`MP1`–`MP9`) of **Data Governance (cd0033)** so that instructor demonstrations use a completely separate company, domain model, and architecture from the learner exercises and capstone:

- **`demos/` — Veridian Health (Medallion Lakehouse on AWS)**
  - **Use Case**: Digital telehealth & clinical diagnostics governed under **HIPAA (45 CFR §164)**, **GDPR Art. 9**, and **CMS eCQM (Electronic Clinical Quality Measures)**.
  - **Architecture**: Bronze / Silver / Gold Medallion Lakehouse in AWS Glue (`veridian_lakehouse`), S3 Parquet zone prefixes, AWS Lake Formation (`phi_governed=true`, `vh_*` healthcare personas), and Amazon Athena via `demo_toolkit.py` and `veridian_seed.py`.
- **`exercises/` — Trailhead Provisions (Federated Retail Platform on AWS)**
  - **Use Case**: Multi-domain e-commerce, loyalty, inventory, and marketing governed under **GDPR** and **CSRD Scope 3** sustainability reporting.
  - **Architecture**: AWS Glue Data Catalog (`trailhead`), AWS Lake Formation (`governed=true`, `co_*` personas), and Amazon Athena via `governance_toolkit.py` and `seed_data.py`.

## Modules (`MP1` – `MP9`)

1. **`MP1_governance-models`** — Federated Operating Model, RACI & Topology
2. **`MP2_metadata-governance`** — Audit & Remediate Catalog Metadata in AWS Glue
3. **`MP3_data-contracts`** — Encode & Validate Governance Obligations in a Data Contract
4. **`MP4_data-quality`** — Six-Dimension Quality Suite & Remediation Planning
5. **`MP5_master-data`** — Entity Resolution, Steward Adjudication & Survivorship
6. **`MP6_lineage-monitoring`** — OpenLineage Blast-Radius & Provenance Monitoring
7. **`MP7_access-control`** — Fine-Grained Access Control in AWS Lake Formation & Terraform IaC
8. **`MP8_regulatory-reporting`** — Regulatory Disclosure Traceability & Unit Reconciliation
9. **`MP9_governance-operations`** — Unified Platform Governance Audit & Operations
