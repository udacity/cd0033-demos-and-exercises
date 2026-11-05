# Adjudicate Master-Data Matches & Set Survivorship

**Trailhead Provisions** has duplicate customers because marketing keys on email and loyalty on
`customer_id`. Resolution auto-merges the obvious (`score >= 0.85`, exact email + name) and rejects
the obvious (`score < 0.66`); the **ambiguous** band (`0.66–0.84` — *pairs that share a name and an
email that differs only by mail provider or a trailing digit*) needs your judgment.

## Your task

In `exercise.ipynb`, connect to your live AWS Cloud Lab (**Step 0: Connect to your Cloud Lab**),
run the resolution workflow against the Glue/Athena `trailhead` catalog (`gc = make_catalog()`),
adjudicate all **8** ambiguous pairs, and document your survivorship rule.

## Requirements

- Run **Step 0: Connect to your Cloud Lab** to verify your AWS credentials and seed the live Glue
  Data Catalog and S3 tables if not already present.
- Inspect `m.ambiguous` across all signal columns (`id_a`, `name_a`, `email_a`, `phone_a`,
  `country_a`, `created_a`, `id_b`, `name_b`, `email_b`, `phone_b`, `country_b`, `created_b`,
  `score` — or query full records via `gc.query(...)`).
- Decide **accept/reject** for each of the **8** ambiguous pairs (`0..7`), choose a survivorship
  rule (`survivor="lowest_id"` or `"earliest_created"`), and apply your decisions with
  `apply_adjudications(m, decisions, survivor=survivor)`.
- Write a **stewardship log**: a per-pair decision table (`0..7`) with the signal per decision; your
  survivorship rule and the system of record; the false-positive vs false-negative tradeoff (why
  over-merging homonyms is worse under GDPR); and the structural shared-key fix.

## Provided files

- `exercise.ipynb`; `governance_toolkit.py` (provides `make_catalog`, `lf_backend`,
  `resolve_customers`, `apply_adjudications`), `aws_backend.py`, `setup_aws.py`, `seed_data.py`.
  Do not edit the provided `.py` files.

## Running it

```bash
pip install boto3 awswrangler pandas jupyterlab
jupyter lab exercise.ipynb
```
