# Demo beats — Auditing a regulated number to source (record in your voice)

Keep it light — this reconciles the report and inspects the `rep.per_order` distribution; the exercise isolates the anomalous rows in a single quarter.

- Open on the premise: a CSRD sustainability disclosure is only as trustworthy as its traceability
  to source. If an auditor challenges a quarterly carbon number, we must be able to walk it back to
  individual orders and shipments.
- Connect with `GovernedCatalog("trailhead.db")` and run `rep = gc.run_sustainability_report()`.
  Display `rep.quarterly` and `rep.reconciliation`.
- Read `rep.reconciliation`: point out that **every quarter fails reconciliation** (`matches == False`),
  with `disclosed_carbon_kg` 8x to 65x larger than `recomputed_carbon_kg`.
- Show how to drill down to source records using `rep.per_order`: inspect `.head()` (`order_id`,
  `shipment_id`, `quarter`, `carbon_kg`) and run `.describe(percentiles=[0.25, 0.5, 0.75, 0.95, 0.99])`
  — up to the 95th percentile (`~9.4 kg`), shipments are normal single-digit kilograms, but the top tail
  jumps into the thousands (`max ~9484`), poisoning the sum.
- Hand off: "in the exercise you'll filter `rep.per_order` to a single quarter, isolate the exact
  anomalous rows that break reconciliation, diagnose the unit defect, and write the traceability
  assessment."
