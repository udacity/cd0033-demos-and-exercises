# Solution — Adjudicate Master Data

## Summary

The skill is **stewardship judgment on the ambiguous band** (*pairs that share a name and an email
that differs only by mail provider or a trailing digit*): accepting true duplicates corroborated by
secondary signals (phone, country, `created_ts`), rejecting homonym non-matches, setting an explicit
survivorship rule, and reasoning about the cost of over- vs under-merging under GDPR.

## Key steps

Of the **8** ambiguous pairs (`0..7`), rows `0..5` (`score == 0.80`) are true duplicates (each has
an email variant — domain swap or trailing digit — plus matching phone, country, and `created_ts`),
while rows `6..7` (`score == 0.75`) are homonym non-matches (different people who share a name and
email base, but have different phones, countries, and registration dates):

```python
decisions = {
    0: "accept", 1: "accept", 2: "accept",
    3: "accept", 4: "accept", 5: "accept",
    6: "reject", 7: "reject",
}
outcome = apply_adjudications(m, decisions, survivor="lowest_id")
```

### Per-pair stewardship decision log (all 8 pairs)

| Row | Pair (`id_a ↔ id_b`) | Name | Signal | Decision | Rationale |
|---|---|---|---|---|---|
| 0 | `45 ↔ 307` | Esme Reyes | same name + domain-swapped email (`trailmail.co` → `outlook.com`), same phone (`+1058040488`), country (`CA`), `created_ts` (`2017-08-20`) | **accept** | same person re-registered with a different mail provider |
| 1 | `133 ↔ 306` | Esme Sattar | same name + trailing-digit email (`esme.sattar` → `esme.sattar2@gmail.com`), same phone (`+81084471562`), country (`IN`), `created_ts` (`2023-08-30`) | **accept** | typo/auto-suffix on re-entry; identical phone, country, and timestamp |
| 2 | `159 ↔ 303` | Yara Pope | same name + domain-swapped email (`proton.me` → `outlook.com`), same phone (`+49578658551`), country (`DE`), `created_ts` (`2014-12-06`) | **accept** | same person re-registered with a different mail provider |
| 3 | `190 ↔ 308` | Felix Reyes | same name + trailing-digit email (`felix.reyes` → `felix.reyes6@trailmail.co`), same phone (`+55952523669`), country (`MX`), `created_ts` (`2024-11-05`) | **accept** | auto-suffixed email handle with identical phone, country, and timestamp |
| 4 | `249 ↔ 304` | Esme Saleh | same name + trailing-digit email (`esme.saleh` → `esme.saleh5@trailmail.co`), both missing phone, same country (`BR`) and `created_ts` (`2024-03-29`) | **accept** | same person re-registered on the same date in `BR` with a trailing digit on the email local-part |
| 5 | `272 ↔ 305` | Yara Adeyemi | same name (extra space) + domain-swapped email (`outlook.com` → `gmail.com`), same phone/country/`created_ts` (`+49296788738`, `DE`, `2024-08-23`) | **accept** | same name (extra space) + domain-swapped email (`outlook.com` → `gmail.com`), same phone/country/`created_ts` → accept (all 6 accepted pairs have an email variant) |
| 6 | `1 ↔ 309` | Zane Saleh | same name + trailing-digit/domain-swapped email (`zane.saleh@proton.me` vs `zane.saleh2@outlook.com`), **different** phone (`+81936622768` vs `+14158902341`), country (`IN` vs `US`), `created_ts` (`2024-12-12` vs `2022-03-14`) | **reject** | homonym collision across two different countries, phones, and registration years |
| 7 | `3 ↔ 310` | Pia Lindqvist | same name + trailing-digit/domain-swapped email (`pia.lindqvist@outlook.com` vs `pia.lindqvist7@proton.me`), **different** phone (`+1919729372` vs `+55119876543`), country (`CA` vs `BR`), `created_ts` (`2023-11-18` vs `2021-05-11`) | **reject** | homonym collision across `CA` and `BR` with distinct phones and registration dates |

*(Note: in `m.ambiguous`, pair `272 ↔ 305` is at row index `5` and `249 ↔ 304` is at row index `4`; whether ordered by customer ID or score, all 6 accepted pairs `0..5` share an email variant plus corroborating phone/country/`created_ts`, while rows `6..7` are rejected as homonyms.)*

**Survivorship rule:** `survivor="lowest_id"` — lowest `customer_id` wins as the golden record
because Customer Identity & Loyalty is the designated system of record and lower IDs represent the
original registration; non-key attributes take the most-recent non-null value.

**False-positive vs false-negative tradeoff:** Under GDPR, a **false positive** (over-merging two
different people, such as the `Zane Saleh` or `Pia Lindqvist` homonyms in rows `6` and `7`) is far
worse than a **false negative** (leaving a true duplicate unmerged): a false merge contaminates one
person's profile with another's PII and consent state (a cross-customer data breach under GDPR Art.
5(1)(f) & Art. 32), whereas a missed duplicate only causes temporary fragmentation.

**Structural fix:** Push the loyalty `customer_id` into Marketing (`campaign_membership`) as the
mandatory foreign key at capture time, eliminating email-based cross-domain resolution entirely.

## Common Mistakes to Avoid

- **Rubber-stamping all 8 ambiguous pairs as `"accept"`** without checking phone, country, and
  `created_ts` — rows `6` (`Zane Saleh`, `IN` vs `US`) and `7` (`Pia Lindqvist`, `CA` vs `BR`) are
  homonyms that must be rejected.
- **Describing `272 ↔ 305` (`Yara Adeyemi`) as only a whitespace difference** — it also has a
  domain-swapped email (`outlook.com` → `gmail.com`); all 6 accepted pairs have an email variant.
- **No survivorship rule** (or omitting `survivor=...` / not tying it to the loyalty system of record).
- **Ignoring the FP/FN asymmetry** — over-merging is the worse GDPR error.
- **Stopping at the merge** without naming the structural shared-key fix.
