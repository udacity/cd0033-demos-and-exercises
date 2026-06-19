# Solution — Verify Reporting Traceability

## Summary

The skill is **auditing a regulated number to source** and distinguishing traceability (can you
find the rows?) from integrity (are the rows right?).

## Key steps

```python
q0 = rep.quarterly.iloc[0]["quarter"]
detail = rep.per_order[rep.per_order["quarter"] == q0]
suspect = detail[detail["carbon_kg"] > 100]    # the grams-not-kg slice
```

The disclosed figure is inflated every quarter (reconciliation `delta_kg` is large) because a
slice of `shipment.carbon_kg` is stored in grams. Traceability holds (rows are findable) but
integrity breaks at the unit boundary. Fix: downstream unit normalization (MP4) + a `carbon_kg > 100`
monitor (MP6).

## Common Mistakes to Avoid

- **Concluding "traceable, therefore fine"** — the number is traceable to a *wrong* source value.
- **Not quantifying the defect** from the reconciliation table.
- **Proposing only a one-time fix** without the monitor that prevents recurrence.
- **Treating the metric definition as a domain choice** — it must be central for one auditable number.
