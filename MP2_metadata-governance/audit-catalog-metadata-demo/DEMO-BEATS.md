# Demo beats — Metadata as a Governance Control on AWS Glue (record in your voice)

Keep it light — this demonstrates the *technique* on the Orders & Inventory slice; the exercise is the full practice on Customer & Marketing.

- Open on the premise: in a federation, the Glue catalog is the one place you can SEE governance —
  or its absence. We'll read it as a control surface, not documentation.
- `make_catalog("trailhead.db")`; call out `lf_backend()` -> `live` (real AWS Glue). Show the
  eight Trailhead tables across four domains.
- Run `catalog_audit()` — narrate that each row is a *control that doesn't exist yet*, read live
  from Glue table/column parameters.
- Show TWO findings from the Orders & Inventory slice AND fix them live:
  1. `orders` has no owner -> `set_table_metadata("orders", owner="orders-team@trailhead.example")` ->
     re-audit, gap gone (Glue UpdateTable just ran).
  2. `product.unit_cost` is an untagged column -> `tag_column("product", "unit_cost", "SENSITIVE")` ->
     re-audit. Point out the remaining untagged columns on `customer` and `campaign_membership` —
     untagged personal-data (`PII`) columns are the highest-severity findings, which learners will
     fix in the exercise.
- Run `semantic_conflicts()`; land on the consent conflict — two systems of record disagree, a
  GDPR risk found purely from metadata.
- Close by handing off: "that's the technique — connect, audit, fix in Glue, re-audit. In the
  exercise you'll do it for the Customer and Marketing domains and write the memo."
