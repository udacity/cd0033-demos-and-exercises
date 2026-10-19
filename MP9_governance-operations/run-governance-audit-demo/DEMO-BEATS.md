# Demo beats — Running governance as an ongoing operation (record in your voice)

Keep it light — this runs `governance_audit()`, closes one Glue gap and one LF gap, and previews the operational artifacts; the exercise remediates the whole platform.

- Open on the premise: governance is an ongoing operation, not a one-time clean-up. `governance_audit()`
  rolls up every discipline (catalog, contracts, quality, lineage, consent, and Lake Formation access)
  into a single operational surface.
- Connect with `make_catalog("trailhead.db")` and run `gc.governance_audit(contracts_valid=True)`.
  Group by `signal` and `severity` to show the 22 initial findings across 5 signals.
- Distinguish between **control-plane gaps** you can close immediately in AWS (`missing_metadata`
  in Glue and `access_control_gap` in Lake Formation) versus **ongoing data SLOs** (`quality_violation`,
  `consent_conflict`, `missing_lineage`) that require producer fixes and continuous monitoring.
- Close one of each live:
  1. `gc.set_table_metadata("orders", owner="orders-team@trailhead.example")` -> `missing_metadata` drops `10 -> 9`.
  2. `gc.assign_tag("customer", "governed", "true")` + `gc.grant_by_tag("co_data_steward", "governed", "true")` ->
     `access_control_gap` drops `1 -> 0`.
- Call out the cross-discipline interaction learners will hit in the exercise: once they tag
  `campaign_membership.cust_ref` as `PII` in Glue, `campaign_membership` becomes a PII table and
  will trigger a new `access_control_gap` until governed in Lake Formation!
- Preview one row of the **Governance Dashboard Spec** and one step of the **New-Domain Onboarding
  Checklist**, then hand off to the exercise (full remediation, operational artifacts, and Mini
  Architect's Brief).
