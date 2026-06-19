# Verify Cross-Domain Reporting Traceability

**Trailhead Provisions**' CSRD quarterly carbon disclosure spans Orders + Inventory. A regulated
number is only as good as its traceability to source.

## Your task

In `exercise.ipynb`, run the reporting pipeline, trace a reported figure to source, and find where
traceability/integrity breaks.

## Requirements

- Trace one disclosed quarter to its source shipments and isolate the rows causing the
  disclosed-vs-recomputed discrepancy.
- Write a **traceability assessment**: the shared metric definition (and why it must be central);
  where traceability holds; where integrity breaks (the unit defect), quantified from the
  reconciliation; and the fix (normalization + monitor).

## Provided files

- `exercise.ipynb`; `governance_toolkit.py` (provides `run_sustainability_report`),
  `seed_data.py`. Do not edit the provided files.

## Running it

```
pip install pandas jupyterlab
jupyter lab exercise.ipynb
```
