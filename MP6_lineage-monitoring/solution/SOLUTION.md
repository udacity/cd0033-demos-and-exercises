# Solution — Trace Lineage & Specify Monitoring

## Summary

The skill is reading lineage as a **blast-radius map** and turning it into monitoring with
thresholds and owners.

## Key traces

```python
gc.lineage.trace_downstream("customer")            # -> ['customer_360', 'marketing_audience']
gc.lineage.trace_upstream("quarterly_sustainability")  # -> order_carbon, product, supplier, orders, shipment
```

Monitoring covers carbon-unit range, consent-mismatch rate, report freshness, mandatory-attr
nulls, and missing lineage events — each with a source, threshold, and owner. The gap the current
signals miss: no monitor on `customer_id`↔`cust_ref` match quality.

## Common Mistakes to Avoid

- **Confusing downstream and upstream** — blast radius is downstream; report provenance is upstream.
- **Thresholds with no owner** — a signal nobody owns is not monitoring.
- **No gap analysis** — the strongest answer names what the current signals would miss.
