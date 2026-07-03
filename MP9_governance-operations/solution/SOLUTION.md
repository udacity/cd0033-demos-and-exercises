# Solution — Run Governance as an Operation

## Summary

This exercise practices **operating** governance: running a platform-wide audit and driving the
AWS-fixable findings to zero (catalog in Glue, access in Lake Formation), then recognizing what
must be managed as ongoing SLOs. Runs live when provisioned, else local with identical behavior.

## Key steps

Close catalog gaps, then access gaps, then re-audit:

```python
# Glue: owner/classification/retention + classify untagged columns (PII where personal)
for tbl in gc.tables():
    tm = gc.catalog.table(tbl)
    gc.set_table_metadata(tbl,
        owner=None if tm.owner else "data-governance@trailhead.example",
        classification=None if tm.classification else "SENSITIVE",
        retention=None if tm.retention else "P5Y")
    for col in tm.columns:
        if col.classification is None:
            gc.tag_column(tbl, col.name, "PII" if col.name in {"email","phone","cust_ref","full_name"} else "PUBLIC")

# Lake Formation: every PII table must be governed
for tbl in gc.tables():
    tm = gc.catalog.table(tbl)
    if tm.classification == "PII" or any(c.classification == "PII" for c in tm.columns):
        gc.assign_tag(tbl, "governed", "true")
gc.grant_by_tag("co_data_steward", "governed", "true")

re_findings = gc.governance_audit(contracts_valid=True)   # missing_metadata == 0, access_control_gap == 0
```

Remaining after remediation: `quality_violation`, `consent_conflict`, `missing_lineage` — the
recurring SLOs that belong on a monitored dashboard, not a one-time cleanup.

## Common Mistakes to Avoid

- **Trying to "fix" quality/consent/lineage to zero** — these are ongoing SLOs; the skill is
  recognizing that and putting them on a dashboard, not deleting the findings.
- **Closing catalog gaps but not the access gaps they create** — classifying PII columns makes
  their tables subject to access governance; you must then govern them in Lake Formation.
- **Remediating without re-auditing** — the proof of an ops loop is the re-run showing zero
  AWS-fixable findings.
- **One-off mindset** — the deliverable should describe running this audit continuously
  (schedule, ownership, trending), not as a single cleanup.
