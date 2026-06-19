# Solution — Plan Quality Remediation

## Summary

The skill is turning expectation failures into **remediation decisions** across source /
downstream / quarantine, prioritized by GDPR/active-harm.

## Strategy map

| Failure | Strategy |
|---|---|
| product.category, product.sustainability_class | source |
| customer.email, customer.phone (validity) | quarantine |
| orders.amount (negatives) | source |
| shipment.carbon_kg (unit) | downstream |
| customer.created_ts (stale) | downstream |
| campaign_membership.mkt_consent | source (read from consent SoR) |

Priority 1: quarantine invalid PII contact data (GDPR + active harm). Priority 2: source fixes
for mandatory attributes / integrity / consent. Priority 3: downstream normalization + staleness.
Consent (~37%) and carbon unit recur — assert as ongoing SLOs.

## Common Mistakes to Avoid

- **Treating all failures as equal** — invalid PII contact data is quarantine-now; a stale
  timestamp is not.
- **Choosing "downstream" for an upstream integrity error** (negative amounts belong at source).
- **Missing that consent/carbon are recurring drift**, not one-time fixes.
- **No tie to contract SLOs** — the plan should make producers accountable.
