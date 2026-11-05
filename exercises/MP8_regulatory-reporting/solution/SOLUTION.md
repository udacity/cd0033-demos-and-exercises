# Solution — Verify Reporting Traceability

## Summary

The skill is **auditing a regulated cross-domain number to source**, explaining why cross-domain
metric rules (unit of measure and quarter attribution timestamp) must be governed centrally, and
distinguishing **traceability** (can you trace the figure to underlying records?) from **integrity**
(are those source values conformant?).

## Key steps

```python
upstream = gc.lineage.trace_upstream("quarterly_sustainability")
# -> ['order_carbon', 'orders', 'shipment']

q0 = rep.quarterly.iloc[0]["quarter"]          # '2023Q4'
detail = rep.per_order[rep.per_order["quarter"] == q0]
suspect = detail[detail["carbon_kg"] > 100]    # the grams-not-kg slice
```

### Exact reconciliation quantification

- **Traced quarter (`2023Q4`):**
  - Disclosed: **`5,355.6 kg`** vs. Recomputed: **`665.2 kg`** → Gap (`delta_kg`): **`4,690.4 kg`** (**~8.1× inflation**).
  - Caused by **1 shipment** out of 140 non-cancelled shipments in `2023Q4` (`shipment_id=22`, `order_id=23` in deterministic table order; or `shipment_id=855`, `order_id=923` in alternate join orderings) recorded in grams (**`4,695.0 g`** instead of **`4.695 kg`**, inflating the quarter by `4,695.0 - 4.695 = 4,690.305 ≈ 4,690.4 kg`).
- **Five-quarter total (`2023Q4`–`2024Q4`):**
  - Disclosed: **`247,207.3 kg`** vs. Recomputed: **`5,483.0 kg`** → Total delta: **`241,724.3 kg`** (**~45.1× inflation**).
  - Driven by **43 gram-scaled shipments** (`carbon_kg > 100`) out of **1,109** total non-cancelled shipments (~3.9% of rows).

### Two cross-domain metric choices (and why they must be central)

1. **Unit of measure (`kg` vs. `g`):** Inventory's `shipment.carbon_kg` column is defined in
   kilograms (`kg`), but ~3% of fulfillment rows arrive in grams (`g`, scaled 1000×). Without a
   central standard enforced at the domain boundary, summing raw values inflates the CSRD disclosure
   45.1×.
2. **Quarter attribution timestamp (`orders.order_ts` vs. `shipment.ship_ts`):** Orders timestamps
   purchases with `orders.order_ts` while Inventory timestamps fulfillment with `shipment.ship_ts`
   (1–5 days later, which crosses a quarter boundary on 49 shipments in this dataset). The central
   standard attributes emissions to the order quarter via `orders.order_ts` (excluding
   `status == 'cancelled'`) so financial revenue and sustainability disclosures align on the same
   reporting period.

### Traceability vs. integrity & remediation

- **Where traceability holds:** `gc.lineage.trace_upstream("quarterly_sustainability")` cleanly
  traces `quarterly_sustainability` (`rep.quarterly`) ← `order_carbon` (`rep.per_order`) ← `orders` +
  `shipment`. Every quarterly figure decomposes to individual order and shipment IDs.
- **Where integrity breaks:** Traceability holds (the exact rows are findable), but **integrity**
  breaks at the unit boundary because `shipment.carbon_kg` mixes grams and kilograms.
- **Fix:** (1) Enforce unit normalization (`carbon_kg / 1000.0` when `carbon_kg > 100`, or reject/convert
  gram payloads at ingestion — MP4) and (2) place an automated pre-disclosure monitor
  (`expect_column_values_to_be_between(0, 100)` on `shipment.carbon_kg` before `build_order_carbon` —
  MP6) plus a reconciliation gate (`abs(delta_kg) < 0.05`) blocking publication when violated.

## Common Mistakes to Avoid

- **Concluding "traceable, therefore fine"** — the number is traceable to a *wrong* (gram-scaled)
  source value.
- **Not quantifying both the single-quarter and five-quarter discrepancy** (`2023Q4`: `5,355.6` vs
  `665.2 kg`, delta `4,690.4 kg`; five-quarter total: `247,207.3` vs `5,483.0 kg`, delta `241,724.3 kg`
  across 43 of 1,109 shipments).
- **Ignoring the second cross-domain choice (`orders.order_ts` vs `shipment.ship_ts`)** — if Orders
  and Inventory bucket quarters by different timestamps, their quarterly totals will never reconcile
  even after unit normalization.
- **Proposing only a one-time fix** without the automated monitor (`carbon_kg <= 100`) and
  reconciliation gate that prevent recurrence.
