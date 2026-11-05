# Solution — Extend a Data Contract

## Summary

The skill is making policy **machine-checkable**: a contract without a governance block fails
validation; adding `pii_tags`, `retention`, and `quality_slos` — and keeping `col["pii"] = True`
consistent with `governance["pii_tags"]` — makes it a publishable, gated artifact.

## Key steps

```python
for col in contract["columns"]:
    col["pii"] = col["name"] in ("customer_id",)
contract["governance"] = {
    "pii_tags": ["customer_id"],
    "retention": "P7Y",
    "quality_slos": [{"dimension": "completeness", "threshold": 0.99},
                     {"dimension": "validity", "threshold": 0.98},
                     {"dimension": "accuracy", "threshold": 0.999}],
}
assert validate_contract(contract)[0]
```

What `validate_contract()` enforces:
1. **JSON Schema structure (`CONTRACT_SCHEMA`):** requires `governance` with `pii_tags` (non-empty array), `retention` matching `^P\d+[YMD]$`, and `quality_slos` (non-empty array of `{dimension, threshold}`).
2. **Semantic cross-checks:** `col["pii"] = True` on `contract["columns"]` must match `governance["pii_tags"]` (`["customer_id"]`), and every SLO `threshold` must be in `(0, 1]`.

Downstream propagation across the true consumers of `orders` (`trace_downstream("orders")` -> `['order_carbon', 'quarterly_sustainability', 'marketing_audience']`):
- **Producers (E-commerce Orders pipeline):** must validate quality SLOs (e.g., `amount >= 0` accuracy `>= 99.9%`) before publishing and enforce the 7-year (`P7Y`) retention/purge lifecycle.
- **`marketing_audience` (PII inheritance):** `build_marketing_audience` joins `orders.customer_id` with `customer_360`. Because `orders.customer_id` is tagged `PII`, `marketing_audience` inherits the PII obligation and must classify, mask, and apply GDPR erasure/consent rules to `customer_id`.
- **`order_carbon` and `quarterly_sustainability` (CSRD retention dependency):** `build_order_carbon` joins `orders` (`order_id`, `order_ts`, `status`) with `shipment` without reading `customer_id`, so neither `order_carbon` nor `quarterly_sustainability` inherits PII. However, `orders`'s `P7Y` retention governs how many years of historical quarters remain auditable for CSRD sustainability disclosures — purging `orders` early would break historical traceability for `quarterly_sustainability`.
- **Propagation mechanism:** the change **version-bumps** the `orders` contract (`1.0.0` -> `1.1.0`). The central publish gate flags downstream contracts referencing the older version and blocks publication until remediation proceeds **upstream-first** (`orders` -> `order_carbon` -> `quarterly_sustainability`, and `orders` -> `marketing_audience`).

## Common Mistakes to Avoid

- **An invalid `retention`** — it must match `^P\d+[YMD]$` (e.g., `P7Y`), not `"7 years"`.
- **Mismatch between `col["pii"]` and `governance["pii_tags"]`** — `validate_contract()` checks that every column listed in `pii_tags` is also marked `col["pii"] = True` in `columns` (and vice versa).
- **Supplying percentage integers (`99.5`) instead of proportions (`0.995`) for SLO `threshold`** — thresholds must be in `(0, 1]`.
- **Claiming `customer_360` is downstream of `orders`** — inspecting `trace_downstream("orders")` shows `customer_360` is built from `customer` + `campaign_membership`; `orders` joins with `customer_360` downstream in `marketing_audience`, and feeds `order_carbon` -> `quarterly_sustainability`.
- **Describing propagation without the mechanism** (contract version-bump + publish gate + upstream-first topological order).
