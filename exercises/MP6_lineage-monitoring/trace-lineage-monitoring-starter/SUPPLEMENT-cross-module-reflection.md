# Supplemental Exercise: Cross-Module Reflection

> Add this section after your monitoring spec in the exercise notebook.

## Connecting Lineage to Quality (MP4 → MP6)

Now that you've traced lineage and specified monitoring signals, look back at your MP4 quality findings.

### Questions

1. **Which quality failures from MP4 would your monitoring signals catch automatically?**
   List at least 2 quality failures and map each to a specific monitoring signal from your spec.

2. **Which quality failures would NOT be caught by lineage monitoring?**
   Why not? (Hint: lineage tracks data flow, not data content.)

3. **The `carbon_kg > 100` accuracy failure**: Your lineage shows `shipment` → `order_carbon` → `quarterly_sustainability`. At which junction in this pipeline would you place a quality gate to catch the grams-vs-kg defect BEFORE it reaches the sustainability report?

### Your answers

1. TODO
2. TODO
3. TODO

**Key insight**: Lineage monitoring catches *structural* problems (pipeline failures, missing inputs, freshness). Quality monitoring catches *content* problems (invalid values, duplicates). A complete governance posture needs both — and the monitoring spec from this exercise should reference quality thresholds, not just pipeline health.
