# Solution — Audit & Remediate Catalog Metadata (Customer & Marketing)

## Summary

This exercise practices **metadata-as-control on live AWS Glue**: audit the catalog to locate
missing governance metadata and cross-domain conflicts, inspect column descriptions to identify
personal data, **fix the gaps in AWS Glue**, and verify with a re-audit — treating metadata as an
enforceable control surface rather than passive documentation.

## Key steps

Filter the audit to the owned domains, inspect column descriptions, remediate using the platform's
classification taxonomy (`PII`, `SENSITIVE`, `PUBLIC`), and re-audit:

```python
my_domains = ["Customer Identity & Loyalty", "Marketing & Campaigns"]
my_gaps = audit[audit["domain"].isin(my_domains)]

gc.tag_column("customer", "email", "PII")
gc.set_table_metadata("campaign", owner="marketing@trailhead.example")
gc.set_table_metadata("campaign_membership", owner="marketing@trailhead.example",
                      classification="PII", retention="P3Y")
gc.tag_column("campaign_membership", "cust_ref", "PII")

remaining = gc.catalog_audit().pipe(lambda d: d[d["domain"].isin(my_domains)])  # -> 0 rows
```

Expected findings (and fixes):

| Object | Gap | Fix | Why it matters |
|---|---|---|---|
| `customer.email` | untagged PII column | tag `PII` | personal data invisible to PII controls — top GDPR risk |
| `campaign_membership.cust_ref` | untagged PII column | tag `PII` | stores customer email (`"customer EMAIL (marketing's key)"`) — a second ungoverned copy of personal data |
| `campaign` | missing owner | set `owner="marketing@trailhead.example"` | no accountable steward |
| `campaign_membership` | missing owner + retention (+ table classification) | set `owner="marketing@trailhead.example"`, `classification="PII"`, `retention="P3Y"` | ungoverned PII table with no deletion clock |

Cross-domain conflicts involving these domains: the **customer identity key** (loyalty
`customer_id` vs marketing `cust_ref` email) and **marketing consent** (loyalty vs marketing
systems of record disagree).

Recommended standards: publish-time gate on `owner`/`classification`/`retention`; apply the `PII`
tag to personal-data columns at creation; designate one consent system of record.

## Common Mistakes to Avoid

- **Auditing but not remediating** — the skill is closing the gap in AWS Glue and proving it with a
  re-audit, not just listing findings.
- **Tagging personal-data columns as `PUBLIC` or `SENSITIVE` instead of `PII`** — `customer.email`
  and `campaign_membership.cust_ref` hold customer email addresses and must be classified `PII` so
  Lake Formation PII masking and GDPR workflows apply.
- **Listing the untagged column as merely "missing a tag"** without recognizing it holds PII —
  the classification gap on a personal-data column is the headline GDPR finding.
- **Auditing all domains** instead of narrowing to the two owned domains (`Customer Identity & Loyalty` and `Marketing & Campaigns`).
- **Treating the consent disagreement as a data-quality bug** rather than a governance conflict
  requiring a single system of record.
- **Fixing the catalog entries but not naming the standard** (publish-time gate) that prevents recurrence.
