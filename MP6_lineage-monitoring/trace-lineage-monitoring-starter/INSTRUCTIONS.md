# Trace Lineage & Specify Monitoring

**Trailhead Provisions** is pre-instrumented with lineage. Use it to reason about blast radius and
to specify the monitoring that would catch a breach early.

## Your task

In `exercise.ipynb`, trace impact through the lineage and specify a monitoring view.

## Requirements

- Trace everything **downstream of `customer`** (a PII breach blast radius) and the **upstream
  sources** of `quarterly_sustainability` (the CSRD report).
- Specify a **monitoring table**: each signal with source, threshold, owner, and the SLA/regulation
  it maps to; and flag at least one gap the current signals would miss.

## Provided files

- `exercise.ipynb`; `governance_toolkit.py` (provides the lineage graph), `seed_data.py`. Do not
  edit the provided files.

## Running it

```
pip install pandas jupyterlab
jupyter lab exercise.ipynb
```
