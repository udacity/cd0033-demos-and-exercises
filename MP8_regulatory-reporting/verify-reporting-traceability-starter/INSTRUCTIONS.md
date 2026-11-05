# Verify Cross-Domain Reporting Traceability

**Trailhead Provisions**' CSRD quarterly carbon disclosure (`quarterly_sustainability`) spans
**E-commerce Orders** (`orders`) and **Inventory & Fulfillment** (`shipment`). Because the metric
crosses two domains, two cross-domain choices must be standardized centrally:
1. **Unit of measure:** `shipment.carbon_kg` must be expressed in kilograms (`kg`), yet ~3% of
   fulfillment rows are recorded in grams (`g`, scaled 1000×).
2. **Quarter attribution timestamp:** Orders records `orders.order_ts` while Inventory records
   `shipment.ship_ts` (1–5 days later, which can cross a quarter boundary); the central standard
   attributes emissions to the order quarter via `orders.order_ts` (excluding `status == 'cancelled'`).

A regulated number is only as good as its traceability to source *and* its integrity across domain
boundaries.

## Your task

In `exercise.ipynb`, connect to your live AWS Cloud Lab (**Step 0: Connect to your Cloud Lab**),
initialize the live catalog (`gc = make_catalog()`), trace the report's upstream lineage with
`gc.lineage.trace_upstream("quarterly_sustainability")`, run the reporting pipeline
(`rep = gc.run_sustainability_report()`), drill from `rep.quarterly` (`quarterly_sustainability`) into
`rep.per_order` (`order_carbon`), and find where integrity breaks.

## Requirements

- Run **Step 0: Connect to your Cloud Lab** to verify your AWS credentials and seed the live Glue
  Data Catalog and S3 tables if not already present.
- Verify upstream lineage with `gc.lineage.trace_upstream("quarterly_sustainability")`
  (`['order_carbon', 'orders', 'shipment']`) and trace one disclosed quarter in `rep.quarterly` to
  its underlying order/shipment records in `rep.per_order`, isolating the rows causing the
  disclosed-vs-recomputed discrepancy (`carbon_kg > 100`).
- Write a **traceability assessment**:
  - The **shared metric definition** and why the two cross-domain choices (**unit of measure**: `kg`
    vs `g`; **quarter attribution timestamp**: `orders.order_ts` vs `shipment.ship_ts`, excluding
    cancelled orders) must be standardized centrally.
  - Where **traceability holds** (`rep.quarterly` / `quarterly_sustainability` → `rep.per_order` /
    `order_carbon` → `orders` + `shipment`).
  - Where **integrity breaks** (the unit defect), **quantified** from `rep.reconciliation` for both
    your traced quarter and the five-quarter total (`2023Q4`–`2024Q4`).
  - The **fix** (unit normalization + pre-disclosure monitor).

## Provided files

- `exercise.ipynb`; `governance_toolkit.py` (provides `make_catalog`, `lf_backend`,
  `run_sustainability_report`, and `gc.lineage`), `aws_backend.py`, `setup_aws.py`, `seed_data.py`.
  Do not edit the provided `.py` files.

## Running it

```bash
pip install boto3 awswrangler pandas jupyterlab
jupyter lab exercise.ipynb
```
