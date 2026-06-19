# Encode Governance Obligations in a Data Contract

**Trailhead Provisions** has an ungoverned `orders` data contract — columns but no policy. Extend
it with a governance block so it validates, then explain how a policy change propagates.

## Your task

In `exercise.ipynb`, add a `governance` block to the provided contract and explain propagation.

## Requirements

- Add `pii_tags`, `retention` (e.g. `P7Y`), and `quality_slos` (`{dimension, threshold}` list),
  and mark PII columns, so the provided `validate_contract()` passes.
- Write a **propagation write-up**: how the change affects producers, how it affects
  consumers/downstream (PII inheritance via the `customer_id` join), and the propagation
  mechanism (version-bump + upstream-first remediation).

## Provided files

- `exercise.ipynb`; `governance_toolkit.py` (provides `validate_contract`), `seed_data.py`. Do
  not edit the provided files.

## Running it

```
pip install pandas jsonschema jupyterlab
jupyter lab exercise.ipynb
```
