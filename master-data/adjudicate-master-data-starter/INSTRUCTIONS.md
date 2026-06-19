# Adjudicate Master-Data Matches & Set Survivorship

**Trailhead Provisions** has duplicate customers because marketing keys on email and loyalty on
`customer_id`. Resolution auto-merges the obvious and rejects the obvious; the **ambiguous** band
needs your judgment.

## Your task

In `exercise.ipynb`, run the resolution workflow, adjudicate the ambiguous pairs, and document
survivorship.

## Requirements

- Decide **accept/reject** for each ambiguous pair and apply your decisions.
- Write a **stewardship log**: the signal per decision; your survivorship rule and the system of
  record; the false-positive vs false-negative tradeoff (why over-merging is worse under GDPR);
  and the structural shared-key fix.

## Provided files

- `exercise.ipynb`; `governance_toolkit.py` (provides `resolve_customers`, `apply_adjudications`),
  `seed_data.py`. Do not edit the provided files.

## Running it

```
pip install pandas jupyterlab
jupyter lab exercise.ipynb
```
