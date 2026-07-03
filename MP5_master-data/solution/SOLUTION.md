# Solution — Adjudicate Master Data

## Summary

The skill is **stewardship judgment on the ambiguous band**: accepting same-person variants,
setting a survivorship rule, and reasoning about the cost of over- vs under-merging.

## Key steps

All six ambiguous pairs are one person with an email variant (domain swap / inserted digit) or a
whitespace name variant — accept all six:

```python
decisions = {0: "accept", 1: "accept", 2: "accept", 3: "accept", 4: "accept", 5: "accept"}
outcome = apply_adjudications(m, decisions)
```

Survivorship: lowest `customer_id` wins (loyalty is the system of record). Accept only pairs with
both a name and an email-local signal; under GDPR, over-merging (exposing one person's data to
another) is worse than a missed duplicate. Structural fix: push the loyalty `customer_id` into
marketing as the shared key.

## Common Mistakes to Avoid

- **Rejecting same-person email variants** as different people — the email-local + name match is strong.
- **No survivorship rule** (or one not tied to the system of record).
- **Ignoring the FP/FN asymmetry** — over-merging is the worse GDPR error.
- **Stopping at the merge** without naming the structural shared-key fix.
