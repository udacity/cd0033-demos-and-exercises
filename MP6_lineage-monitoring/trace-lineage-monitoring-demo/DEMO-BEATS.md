# Demo beats — Lineage as a blast-radius map (record in your voice)

Keep it light — this traces the shipment/carbon path and defines one monitoring signal; the exercise traces customer PII and the full CSRD report.

- Open on the premise: lineage answers two operational questions — "if this source breaks, what
  downstream is contaminated?" (`trace_downstream`) and "for a regulated number, what sources feed
  it?" (`trace_upstream`).
- Connect with `GovernedCatalog("trailhead.db")`; display `gc.lineage.events()` (OpenLineage-shaped
  job inputs and outputs) and the Mermaid DAG from `gc.lineage.to_mermaid()`.
- Run `gc.lineage.trace_downstream("shipment")`, `gc.lineage.trace_upstream("order_carbon")`, and
  `gc.lineage.simulate_breach("shipment")` -> point out that a defect at `shipment` reaches
  `order_carbon` and `quarterly_sustainability` with no gate in between.
- Show how lineage drives monitoring placement: add one sample monitoring row (`shipment_carbon_range`
  on `shipment` -> `build_order_carbon`, threshold `carbon_kg <= 100`, owned by Inventory, tied to
  CSRD accuracy).
- Hand off: "in the exercise you'll trace a `customer` breach downstream, trace all upstream
  sources of `quarterly_sustainability`, and specify the monitoring table that protects both."
