# Supplemental Exercise: Regulatory Justification

> Add this section after your reconciliation memo in the exercise notebook.

## Regulatory Framing

For each of your top-3 highest-priority findings from the catalog audit, answer:

1. **Which regulation** (GDPR or CSRD) makes this finding high-priority?
2. **What is the specific risk** if it remains unresolved? (e.g., "untagged PII column means we cannot prove column-level access restriction under GDPR Art. 25")
3. **What is the remediation deadline pressure?** (audit notice = immediate; CSRD reporting = quarterly)

### Example (provided)

| Finding | Regulation | Risk | Pressure |
|---------|-----------|------|----------|
| `customer.phone` untagged | GDPR (Art. 25, 32) | Cannot prove data minimization; auditor finds PII without classification | Immediate (audit notice) |

### Your answers

| Finding | Regulation | Risk | Pressure |
|---------|-----------|------|----------|
| TODO | TODO | TODO | TODO |
| TODO | TODO | TODO | TODO |
| TODO | TODO | TODO | TODO |

**Key insight**: Not all governance gaps carry equal regulatory weight. A missing `retention` on a non-PII table is medium priority; a missing PII classification on `customer.email` is a GDPR Art. 30 recordkeeping violation — high priority with the audit notice pending.
