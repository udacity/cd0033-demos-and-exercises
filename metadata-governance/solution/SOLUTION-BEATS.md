# Solution beats — Audit & Remediate Catalog Metadata exercise (record in your voice)

- Restate the task: GDPR notice just landed; audit AND fix the two personal-data domains first.
- `make_catalog`, confirm `live`; run the audit, filter to Customer + Marketing.
- Spotlight the two untagged PII columns (`customer.email`, `campaign_membership.cust_ref`) —
  an untagged personal-data column is the #1 thing an auditor flags — then tag them in Glue.
- Fix the table gaps: `campaign` owner; `campaign_membership` owner AND retention (ungoverned
  PII with no deletion clock). Re-audit -> the two domains show 0 gaps; that's the proof.
- Tie the conflicts in: identity key (no shared join) and consent (two disagreeing systems of
  record) — both GDPR-relevant, not fixable by a tag alone.
- Land the standard, not just the fix: publish-time gate on owner/classification/retention, one
  consent system of record.
