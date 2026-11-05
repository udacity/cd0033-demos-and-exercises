# Solution — Plan Quality Remediation

## Summary

The skill is turning expectation failures into **remediation decisions** across `quarantine` /
`source` / `downstream`, prioritized by active GDPR and CSRD regulatory harm and tied to the
platform's target contract SLOs (`gc.contract_slos()`).

## Strategy map

| Failure (`table.column`) | Dimension | Unexpected % | Strategy | Target Contract SLO (`gc.contract_slos()`) |
|---|---|---|---|---|
| `customer.email` | validity | `4.55%` (20 of 440) | `quarantine` | `>= 99.5% valid format` |
| `customer.phone` | validity | `7.95%` (35 of 440) | `quarantine` | `>= 99.5% E.164 format` |
| `campaign_membership.mkt_consent` | consistency | `20.71%` (157 of 758 valid-email rows; plus 42 `unresolvable_count` `'n/a'` rows) | `quarantine` | `>= 99.0% match loyalty SoR` |
| `shipment.carbon_kg` | accuracy | `9.29%` (65 of 700 > 100 kg, recorded in grams) | `quarantine` | `100% in kg (0 < kg <= 100)` |
| `product.category` | completeness | `8.33%` (5 of 60 null) | `source` | `>= 99.0% non-null` |
| `product.sustainability_class` | completeness | `50.00%` (30 of 60 null) | `source` | `>= 99.0% non-null` |
| `orders.amount` | accuracy | `1.11%` (10 of 900 negative) | `source` | `>= 99.9% non-negative` |
| `customer.created_ts` | timeliness | `5.68%` (25 of 440 > 1095d) | `downstream` | `>= 98.0% within 1095d` |

## Prioritized tiers

- **Priority 1 — Quarantine immediately (active GDPR & CSRD regulatory harm):**
  - `campaign_membership.mkt_consent` (~21% / `20.71%` mismatch on the 758 valid-email rows, plus 42 unresolvable `'n/a'` rows): marketing to customers who withdrew consent in the loyalty system of record is an active GDPR Art. 7/21 violation. Quarantine conflicting and unresolvable rows from campaign sends immediately while re-pointing marketing to the loyalty consent SoR (`>= 99.0% match loyalty SoR`).
  - `shipment.carbon_kg` (`9.29%` > 100 kg): gram-scaled shipments inflate the CSRD quarterly carbon disclosure ~100x. Quarantine gram-scaled rows from the reporting feed (`100% in kg (0 < kg <= 100)`) while normalizing units and fixing the carrier ingest contract.
  - `customer.email` (`4.55%`) and `customer.phone` (`7.95%`): invalid PII contact formats break GDPR subject-access/erasure matching and message delivery. Quarantine malformed rows out of downstream audiences until signup validation meets `>= 99.5% valid format` and `>= 99.5% E.164 format`.
- **Priority 2 — Fix at source (producer contract enforcement):**
  - `product.category` (`8.33%` null) and `product.sustainability_class` (`50.00%` null): mandatory catalog/CSRD attributes owned by `Inventory & Fulfillment`; enforce `>= 99.0% non-null` completeness at the producer publish gate.
  - `orders.amount` (`1.11%` negative): upstream checkout/refund sign bug in `E-commerce Orders`; enforce `>= 99.9% non-negative` accuracy at source.
- **Priority 3 — Handle downstream (transform / load rules):**
  - `customer.created_ts` (`5.68%` older than 1095 days): historical loyalty records are expected in an acquired customer base; flag or archive stale records in downstream retention/analytics transforms to meet `>= 98.0% within 1095d` timeliness on active cohorts.
- **Recurring drift watch (ongoing SLOs):**
  - Consent consistency (`campaign_membership.mkt_consent`, ~21% mismatch) and shipment carbon unit accuracy (`shipment.carbon_kg`, grams vs. kg) are recurring cross-domain drift — monitor them continuously as standing SLOs on the governance dashboard.

## Common Mistakes to Avoid

- **Not quarantining `campaign_membership.mkt_consent` or `shipment.carbon_kg` in Priority 1** — both cause immediate regulatory harm (unlawful GDPR marketing sends and ~100x inflated CSRD carbon disclosures) if allowed to flow into production pipelines unquarantined.
- **Quoting a Cartesian-inflated consent mismatch rate** instead of the true `~21%` (`20.71%` across 758 valid-email memberships, with 42 `'n/a'` rows reported in `unresolvable_count`).
- **Choosing `downstream` for an upstream integrity error** (`orders.amount` negatives and missing `product` attributes belong at `source`).
- **Omitting explicit target contract SLO numbers** from `gc.contract_slos()` for each priority tier.
