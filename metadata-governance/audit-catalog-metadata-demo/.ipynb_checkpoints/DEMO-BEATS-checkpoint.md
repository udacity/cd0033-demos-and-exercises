# Demo beats — Metadata as a Governance Control (record in your voice)

Keep it light — this demonstrates the *technique*; the exercise is the full practice.

- Open on the premise: in a federation, the catalog is the one place you can SEE governance —
  or its absence. We'll read it as a control surface, not documentation.
- Build the catalog (`GovernedCatalog`), show the eight Trailhead tables across four domains.
- Run `catalog_audit()` — narrate that each row is a *control that doesn't exist yet*.
- Read just TWO representative findings: (1) a table-level gap — `orders` has no owner, so no
  accountable steward; (2) a column-level gap — an untagged PII column, the highest-severity
  kind because personal data with no classification is invisible to PII controls.
- Run `semantic_conflicts()`; land on the consent conflict — two systems of record disagree,
  a GDPR risk found purely from metadata.
- Close by handing off: "that's the technique — in the exercise you'll run the full audit and
  write the reconciliation memo for the Customer and Marketing domains."
