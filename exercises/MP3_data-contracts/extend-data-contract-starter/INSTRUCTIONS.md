# Encode Governance Obligations in a Data Contract

**Trailhead Provisions** has an ungoverned `orders` data contract — columns, but no policy. Extend
it with a governance block so it passes both structural schema validation and semantic governance
checks, then explain how a policy change propagates across producers and downstream consumers.

## Your task

In `exercise.ipynb`, add a `governance` block to the provided `orders` contract, mark its PII
column(s), verify with `validate_contract()`, and explain how the contract's PII and retention
policies propagate downstream.

## Requirements

- Add `governance` containing:
  - `pii_tags`: list of PII column name(s) in `orders`
  - `retention`: an ISO-8601 duration (`^P\d+[YMD]$`) matching the `orders` catalog retention (look it up from the catalog metadata or specify an appropriate multi-year financial/audit retention period)
  - `quality_slos`: list of `{dimension, threshold}` objects where every `threshold` is a proportion in `(0, 1]`
- Mark the corresponding column(s) in `contract["columns"]` with `col["pii"] = True` so `validate_contract()` passes both **JSON Schema validation** and **semantic cross-checks** (`col["pii"] == True` must match `governance["pii_tags"]`, and every SLO `threshold` must be in `(0, 1]`).
- Write a **propagation write-up** based on the true downstream consumers of `orders` (`build_lineage().trace_downstream("orders")`):
  - How the change affects **producers** (what the E-commerce Orders pipeline must enforce).
  - How it affects **downstream consumers** (`marketing_audience` joining `orders.customer_id` with `customer_360` vs. `order_carbon` and `quarterly_sustainability` reading `orders` for CSRD carbon reporting).
  - The **propagation mechanism** (contract version-bump + publish gate + upstream-first remediation).

## Provided files

- `exercise.ipynb` — your working notebook.
- `governance_toolkit.py` (provides `validate_contract`, `build_lineage`, `contract_slos`), `seed_data.py` — provided; do not edit.

## Running it

1. Open `exercise.ipynb` in your Cloud Lab JupyterLab workspace.
2. Run the notebook top-to-bottom and complete sections `1` and `2`.
