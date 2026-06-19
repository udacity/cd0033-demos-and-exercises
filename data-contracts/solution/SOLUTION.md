# Solution — Extend a Data Contract

## Summary

The skill is making policy **machine-checkable**: a contract without a governance block fails
validation; adding `pii_tags`, `retention`, and `quality_slos` makes it a publishable, gated
artifact.

## Key steps

```python
for col in contract["columns"]:
    col["pii"] = col["name"] in ("customer_id",)
contract["governance"] = {
    "pii_tags": ["customer_id"],
    "retention": "P7Y",
    "quality_slos": [{"dimension": "completeness", "threshold": 0.99},
                     {"dimension": "validity", "threshold": 0.98},
                     {"dimension": "accuracy", "threshold": 0.995}],
}
assert validate_contract(contract)[0]
```

Propagation: producers must meet the SLOs + enforce retention; consumers joining `customer_id`
inherit the PII obligation; a version-bump flags downstream contracts and the schema gate blocks
publishing against an outdated upstream version (upstream-first remediation).

## Common Mistakes to Avoid

- **An invalid `retention`** — it must match `P<n>[YMD]` (e.g., `P7Y`), not "7 years".
- **Forgetting `quality_slos` needs at least one `{dimension, threshold}`** entry.
- **Treating the change as local** — missing the PII inheritance that flows to downstream products.
- **Describing propagation without the mechanism** (version-bump + publish gate).
