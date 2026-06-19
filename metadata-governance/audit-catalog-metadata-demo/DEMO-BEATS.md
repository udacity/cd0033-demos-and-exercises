# Demo beats — Metadata as a Governance Control on AWS Glue (record in your voice)

Keep it light — this demonstrates the *technique*; the exercise is the full practice.

- Open on the premise: in a federation, the Glue catalog is the one place you can SEE governance —
  or its absence. We'll read it as a control surface, not documentation.
- `make_catalog("trailhead.db")`; call out `lf_backend()` -> `live` (real AWS Glue). Show the
  eight Trailhead tables across four domains.
- Run `catalog_audit()` — narrate that each row is a *control that doesn't exist yet*, read live
  from Glue table/column parameters.
- Show TWO findings AND fix them live: (1) `orders` has no owner -> `set_table_metadata(...)` ->
  re-audit, gap gone (Glue UpdateTable just ran); (2) an untagged PII column -> `tag_column(...)`
  -> re-audit. Emphasize: an untagged personal-data column is the highest-severity finding.
- Run `semantic_conflicts()`; land on the consent conflict — two systems of record disagree, a
  GDPR risk found purely from metadata.
- Close by handing off: "that's the technique — connect, audit, fix in Glue, re-audit. In the
  exercise you'll do it for the Customer and Marketing domains and write the memo."
