# Solution — Run Governance as an Operation

## Summary

This exercise practices **operating** governance against **live AWS Glue, Lake Formation, and Amazon
Athena** (no local fallback): running a platform-wide audit (`AwsGovernedCatalog` reads live Glue
table/column classifications and live Lake Formation tags/permissions), driving the AWS-fixable
control-plane findings to zero (catalog in Glue, access in Lake Formation), and managing the
remaining signals (`quality_violation`, `consent_conflict`, `missing_lineage`) with both
current-instance remediation and recurring operational SLO monitoring.

## Key steps

Close catalog gaps using domain owners and proper sensitivity classifications, then close Lake Formation access gaps on all PII tables, then re-audit:

```python
# Step 2 — Glue: domain-specific table metadata + column classifications (PII / SENSITIVE / PUBLIC)
TABLE_REMEDIATION = {
    "orders":              {"owner": "orders-team@trailhead.example"},
    "supplier":            {"retention": "P5Y"},
    "product":             {"retention": "P5Y"},
    "shipment":            {"classification": "PUBLIC"},
    "campaign":            {"owner": "marketing@trailhead.example"},
    "campaign_membership": {"owner": "marketing@trailhead.example", "classification": "PII", "retention": "P3Y"},
}
for tbl, meta in TABLE_REMEDIATION.items():
    gc.set_table_metadata(tbl, **meta)

PII_COLS = {"email", "phone", "cust_ref", "full_name"}
SENSITIVE_COLS = {"unit_cost", "amount", "marketing_consent", "mkt_consent"}
for tbl in gc.tables():
    tm = gc.catalog.table(tbl)
    for col in tm.columns:
        if col.classification is None:
            cls = "PII" if col.name in PII_COLS else ("SENSITIVE" if col.name in SENSITIVE_COLS else "PUBLIC")
            gc.tag_column(tbl, col.name, cls)

mid_findings = gc.governance_audit(contracts_valid=True)
# missing_metadata: 10 -> 0
# access_control_gap: 1 -> 2 (customer was already 1; tagging campaign_membership.cust_ref as PII surfaced a 2nd!)

# Step 3 — Lake Formation: every PII-bearing table (customer, campaign_membership) must be governed
for tbl in gc.tables():
    tm = gc.catalog.table(tbl)
    if tm.classification == "PII" or any(c.classification == "PII" for c in tm.columns):
        gc.assign_tag(tbl, "governed", "true")
gc.grant_by_tag("co_data_steward", "governed", "true")
display(gc.grants_summary())

# Step 4 — Re-audit
re_findings = gc.governance_audit(contracts_valid=True)   # missing_metadata == 0, access_control_gap == 0
```

## Remaining Signals & Concrete SLO Targets

After clearing `missing_metadata` (`10 -> 0`) and `access_control_gap` (`1 -> 2 -> 0`), 11 findings
remain across three recurring operational signals. For each category, separate **current instance
remediation** from **recurring operational SLO monitoring**:

- **`quality_violation` (8 findings — 6 high, 2 low)**:
  - *Concrete SLO targets*: completeness `>= 99.0%` non-null (`product.category`, `product.sustainability_class`),
    validity `>= 99.5%` valid format (`customer.email`, `customer.phone`), accuracy `>= 99.9%` non-negative
    (`orders.amount`) and `100%` in kg (`0 < carbon_kg <= 100` on `shipment.carbon_kg`), timeliness `>= 98.0%`
    within 1,095 days (`customer.created_ts`).
  - *Current instance remediation vs. recurring SLO*: Ticket domain stewards to clean current defective batches
    (e.g., normalizing the grams slice in `shipment.carbon_kg`), and monitor quality SLOs on every ingestion
    load because upstream vendor feeds and schema changes continuously introduce new defects.
- **`consent_conflict` (1 finding — high)**:
  - *Concrete SLO target*: cross-domain consent mismatch rate `< 1.0%` (`>= 99.0%` consistency between
    `campaign_membership.mkt_consent` and the loyalty system of record `customer.marketing_consent`).
  - *Current instance remediation vs. recurring SLO*: Reconcile the current ~20% opt-in disagreement by
    syncing marketing's table from loyalty's authoritative consent store, and monitor the `< 1.0%` mismatch
    SLO continuously because new campaign imports and partner lists can re-introduce un-synced consent flags.
- **`missing_lineage` (2 findings — medium)**:
  - *Concrete SLO target*: `100%` of production Glue catalog tables covered by OpenLineage job events
    (`0` un-instrumented tables).
  - *Current instance remediation vs. recurring SLO*: Ticket Platform Engineering to emit OpenLineage events
    for the two currently un-instrumented tables (`order_returns` and `campaign`), and monitor the `100%`
    lineage coverage SLO on every weekly audit because new domain tables and pipelines are onboarded every quarter.

## Common Mistakes to Avoid

- **Tagging every non-PII column as `PUBLIC`** — commercially sensitive columns like `product.unit_cost` must be tagged `SENSITIVE`, and domain tables must be assigned to their domain owners (`orders-team@`, `marketing@`), not central governance.
- **Claiming `customer` had no access-control gap before Step 2** — `customer` was already flagged as an `access_control_gap` in the initial Step 1 audit (`1` finding); classifying `campaign_membership.cust_ref` as `PII` in Step 2 added `campaign_membership` as a second finding (`1 -> 2`), before Step 3 governed both (`2 -> 0`).
- **Trying to "fix" quality/consent/lineage in the catalog or conflating one-time tickets with SLOs** — separate fixing today's instances (e.g., instrumenting `order_returns` and `campaign`) from monitoring the recurring SLOs on every scheduled audit run.
- **Closing catalog gaps but not the access gaps they create** — classifying PII columns makes their tables subject to access governance; you must then govern them in Lake Formation and verify with `gc.grants_summary()` and `gc.governance_audit()`.
