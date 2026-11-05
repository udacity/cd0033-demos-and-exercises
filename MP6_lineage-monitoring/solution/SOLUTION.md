# Solution — Trace Lineage & Specify Monitoring

## Summary

The skill is reading lineage to answer **two separate operational questions** — (1) downstream
blast radius of a PII breach and (2) upstream provenance of a regulated report — and turning both
into a concrete monitoring specification with thresholds, owners, and regulatory SLAs.

## Key traces

```python
pii_impact = gc.lineage.trace_downstream("customer")
# -> ['customer_360', 'marketing_audience']

report_sources = gc.lineage.trace_upstream("quarterly_sustainability")
# -> ['order_carbon', 'orders', 'shipment']
```

1. **Downstream of `customer` (`['customer_360', 'marketing_audience']`):** Confirms that a
   `customer` PII breach impacts Customer 360 and Marketing Audience, and **does not** reach
   `quarterly_sustainability`.
2. **Upstream of `quarterly_sustainability` (`['order_carbon', 'orders', 'shipment']`):** Confirms
   the CSRD report's actual upstream sources (`order_carbon`, fed by `orders` and `shipment`), with
   no dependency on `customer`.

### Monitoring specification

| Signal | Where (Source dataset / job / log) | Threshold | Owner | SLA / Regulation |
|---|---|---|---|---|
| Anomalous PII read volume / unauthorized access on `customer` or `customer_360` | Lake Formation / CloudTrail data-access logs | `> 3x` 7-day rolling read baseline or any query by a principal without an LF grant | Security & Central Governance Lead (with Customer Identity Lead) | GDPR Art. 33 (72-hour breach notification window) |
| Carbon unit out of range (`carbon_kg`) | `shipment` → `build_order_carbon` | any `carbon_kg > 100` (0 rows above max) | Inventory/Fulfillment Lead | Accuracy SLO; CSRD Art. 29a report integrity |
| Consent mismatch rate | `build_customer_360` (`customer` ⋈ `campaign_membership`) | `> 1%` loyalty ≠ marketing consent | Customer Identity Lead (with Marketing Lead) | Consistency SLO; GDPR Art. 6 / Art. 7 consent |
| Freshness of `quarterly_sustainability` | `build_quarterly_sustainability` job | `> 24h` since last successful run | CSRD Reporting Owner | Report freshness SLA; CSRD filing schedule |
| Null mandatory attributes (`product.category`, `product.sustainability_class`) | `product` producer ingestion check | `> 1%` null rate (`>= 99.0%` non-null SLO) | Inventory/Fulfillment Lead | Completeness SLO; CSRD product classification |
| Lineage event missing | All scheduled ETL jobs (OpenLineage emitter) | Any job run completing with no emitted lineage event | Platform Engineering | Governance audit / observability |

**Gap the current signals miss:** Neither `product` nor `supplier` is wired into
`build_order_carbon` yet, and there is no monitor on the `customer_id` ↔ `cust_ref` identity
resolution match rate in `build_customer_360` (nor on unresolvable `cust_ref = 'n/a'` rows in
`campaign_membership`), so a spike in unmatched or unresolvable marketing records would silently
drop from `customer_360` without alarming.

## Common Mistakes to Avoid

- **Conflating the two lineage paths** (e.g., implying `customer` feeds `quarterly_sustainability`) —
  the customer PII pipeline (`customer` → `customer_360` → `marketing_audience`) and the CSRD carbon
  pipeline (`orders` + `shipment` → `order_carbon` → `quarterly_sustainability`) are separate subgraphs.
- **Omitting a PII breach / access anomaly signal** — tracing a `customer` PII breach requires an
  access-log signal mapped to GDPR Art. 33's 72-hour breach notification SLA, not just data-quality checks.
- **Confusing downstream and upstream** — blast radius is downstream; report provenance is upstream.
- **Thresholds with no owner** — a signal nobody owns is not monitoring.
- **No gap analysis** — the strongest answer names what the current signals would miss.
