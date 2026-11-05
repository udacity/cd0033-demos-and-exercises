# Trace Lineage & Specify Monitoring

**Trailhead Provisions** is pre-instrumented with OpenLineage-shaped pipeline lineage. Use it to
answer two independent governance questions — (1) what is the blast radius of a customer PII breach,
and (2) what upstream sources feed the CSRD quarterly sustainability report — and specify the
monitoring table that protects both paths.

## Your task

In `exercise.ipynb`, connect to your live AWS Cloud Lab (**Step 0: Connect to your Cloud Lab**),
initialize the live catalog (`gc = make_catalog()`), trace both lineage paths, and specify your
platform monitoring table.

## Requirements

- Run **Step 0: Connect to your Cloud Lab** to verify your AWS credentials and seed the live Glue
  Data Catalog and S3 tables if not already present.
- Answer the **two separate lineage questions**:
  1. **Customer PII breach blast radius (downstream):** Trace everything **downstream of `customer`**
     (`gc.lineage.trace_downstream("customer")`) to confirm that a `customer` PII breach impacts
     `customer_360` and `marketing_audience`, and **does not** reach `quarterly_sustainability`.
  2. **CSRD report provenance (upstream):** Trace the **upstream sources** of
     `quarterly_sustainability` (`gc.lineage.trace_upstream("quarterly_sustainability")`) to confirm
     the CSRD report's actual upstream sources (`order_carbon`, `orders`, `shipment`).
- Specify a **monitoring table**: each signal with source/where, threshold, owner, and the
  SLA/regulation it maps to (including a PII breach / anomalous access signal mapped to GDPR Art. 33);
  and flag at least one gap the current signals would miss.

## Provided files

- `exercise.ipynb`; `governance_toolkit.py` (provides `make_catalog`, `lf_backend`, and the lineage
  graph), `aws_backend.py`, `setup_aws.py`, `seed_data.py`. Do not edit the provided `.py` files.

## Running it

```bash
pip install boto3 awswrangler pandas jupyterlab
jupyter lab exercise.ipynb
```
