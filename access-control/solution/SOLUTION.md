# Solution — Configure Governed Access in Lake Formation

## Summary

This exercise practices **fine-grained access as a governance control**: implementing column-,
row-, tag-, and metadata-level access in AWS Lake Formation and **verifying** it by querying as
each persona in Athena — not describing access in a doc. Runs live when provisioned, else local.

## Key steps

```python
gc.grant_columns("co_marketing_analyst", "customer", exclude=["email", "phone"])  # column
gc.create_row_filter("eu_only", "customer", "region = 'EU'")                       # row
gc.grant_rows("co_cs_rep", "customer", "eu_only")
gc.assign_tag("customer", "governed", "true")                                      # tag-based
gc.grant_by_tag("co_data_steward", "governed", "true")
gc.grant_describe_only("co_auditor")                                               # metadata-only
results = verify_step7(gc)        # every row PASS
```

Expected verification:

| Persona | Check | Result |
|---|---|---|
| `co_marketing_analyst` | `email`, `phone` absent from result | PASS |
| `co_cs_rep` | every row `region == 'EU'` | PASS |
| `co_data_steward` | full columns + rows (via tag) | PASS |
| `co_auditor` | DESCRIBE works, SELECT denied | PASS |

## Common Mistakes to Avoid

- **Granting the steward per-table instead of by tag** — tag-based grant is what makes new
  governed tables inherit access automatically.
- **Giving the auditor SELECT "just to be safe"** — the point is metadata-only; SELECT must be denied.
- **Forgetting the row filter is row-level, not a column grant** — cs_rep keeps all columns but
  only EU rows.
- **Declaring access without verifying** — the graded skill is the passing verification, which
  proves Lake Formation actually enforces the policy.
