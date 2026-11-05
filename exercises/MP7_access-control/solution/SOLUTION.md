# Solution — Configure Governed Access in Lake Formation

## Summary

This exercise practices **fine-grained access as a governance control**: implementing column-,
row-, tag-, and metadata-level access in **live AWS Lake Formation** and **verifying** it by
assuming each persona role via STS and querying in **Amazon Athena** and **AWS Glue** (no local
fallback). You also analyze how the `S3 -> Glue -> Lake Formation -> IAM` governance chain is
declared in Terraform.

## Key steps

```python
gc.reset()
gc.grant_columns("co_marketing_analyst", "customer", exclude=["full_name", "email", "phone"])  # column-level
gc.create_row_filter("eu_only", "customer", "region = 'EU'")                                   # row-level
gc.grant_rows("co_cs_rep", "customer", "eu_only")
gc.assign_tag("customer", "governed", "true")                                                  # tag-based (LF-TBAC)
gc.grant_by_tag("co_data_steward", "governed", "true")
gc.grant_describe_only("co_auditor")                                                           # metadata-only
results = verify_step7(gc)        # every row PASS on live (AWS Lake Formation + Athena)
```

Expected verification:

| Persona | Check | Result | Backend |
|---|---|---|---|
| `co_marketing_analyst` | `PII columns masked (full_name, email, phone)` | PASS | `live (AWS Lake Formation + Athena)` |
| `co_cs_rep` | `row filter region='EU' (all cols, 62 EU rows)` | PASS | `live (AWS Lake Formation + Athena)` |
| `co_data_steward` | `tag grant (governed=true) = full access` | PASS | `live (AWS Lake Formation + Athena)` |
| `co_auditor` | `metadata-only (DESCRIBE ok, SELECT denied)` | PASS | `live (AWS Lake Formation + Athena)` |

## Common Mistakes to Avoid

- **Excluding only `email` and `phone` for `co_marketing_analyst`** — `full_name` is also a PII
  column on `customer`; all three (`["full_name", "email", "phone"]`) must be excluded.
- **Granting the steward per-table instead of by tag** — first tag `customer` with
  `gc.assign_tag("customer", "governed", "true")`, then grant by tag with
  `gc.grant_by_tag("co_data_steward", "governed", "true")` so new governed tables inherit access
  automatically.
- **Giving the auditor SELECT "just to be safe"** — the point is metadata-only (`DESCRIBE` via Glue);
  `SELECT` in Athena must be denied.
- **Forgetting the row filter is row-level, not a column grant** — `co_cs_rep` keeps all 9 columns
  on `customer`, filtered to the 62 rows where `region = 'EU'`.
- **Declaring access without verifying** — the graded skill is the passing `verify_step7(gc)` output,
  which proves live Lake Formation and Athena enforce the policy.
