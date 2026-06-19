# Solution — Audit & Remediate Catalog Metadata (Customer & Marketing)

## Summary

This exercise practices **metadata-as-control on AWS Glue**: audit the catalog to locate missing
governance metadata and cross-domain conflicts, **fix the gaps in Glue**, and verify with a
re-audit — not treating metadata as documentation. Runs on live AWS when provisioned, else a
local fallback with identical behavior.

## Key steps

Filter the audit to the owned domains, remediate, re-audit:

```python
my_domains = ["Customer Identity & Loyalty", "Marketing & Campaigns"]
my_gaps = audit[audit["domain"].isin(my_domains)]

gc.tag_column("customer", "email", "PII")
gc.set_table_metadata("campaign", owner="marketing@trailhead.example")
gc.set_table_metadata("campaign_membership", owner="marketing@trailhead.example", retention="P3Y")
gc.tag_column("campaign_membership", "cust_ref", "PII")

remaining = gc.catalog_audit().pipe(lambda d: d[d["domain"].isin(my_domains)])  # -> 0 rows
```

Expected findings (and fixes):

| Object | Gap | Fix | Why it matters |
|---|---|---|---|
| `customer.email` | untagged PII column | tag `PII` | personal data invisible to PII controls — top GDPR risk |
| `campaign_membership.cust_ref` | untagged PII column | tag `PII` | a second ungoverned copy of customer email |
| `campaign` | missing owner | set owner | no accountable steward |
| `campaign_membership` | missing owner + retention | set owner + `P3Y` | ungoverned PII with no deletion clock |

Cross-domain conflicts involving these domains: the **customer identity key** (loyalty
`customer_id` vs marketing `cust_ref` email) and **marketing consent** (loyalty vs marketing
systems of record disagree).

Recommended standards: publish-time gate on `owner`/`classification`/`retention`; apply the PII
tag to personal-data columns at creation; designate one consent system of record.

## Common Mistakes to Avoid

- **Auditing but not remediating** — the skill is closing the gap in Glue and proving it with a
  re-audit, not just listing findings.
- **Listing the untagged column as merely "missing a tag"** without recognizing it holds PII —
  the classification gap on a personal-data column is the headline GDPR finding.
- **Auditing all domains** instead of narrowing to the two owned domains.
- **Treating the consent disagreement as a data-quality bug** rather than a governance conflict
  with a single-system-of-record fix.
- **Fixing the data but not naming the standard** (publish-time gate) that prevents recurrence.
