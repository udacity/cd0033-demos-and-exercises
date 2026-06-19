# Interpret Quality Results & Plan Remediation

**Trailhead Provisions**' quality suite reports expectation failures across six dimensions. Each
failure needs a decision, not just a number.

## Your task

In `exercise.ipynb`, run the provided quality suite, classify each failure, and write a
prioritized remediation plan.

## Requirements

- Map every failing `table.column` to a strategy: **source** / **downstream** / **quarantine**.
- Write a **prioritized plan**: which failures are GDPR/active-harm and must be quarantined first;
  tie strategies to contract SLOs; flag recurring drift (consent, carbon unit) as ongoing SLOs.

## Provided files

- `exercise.ipynb`; `governance_toolkit.py` (provides `run_quality_suite`), `seed_data.py`. Do
  not edit the provided files.

## Running it

```
pip install pandas jupyterlab
jupyter lab exercise.ipynb
```
