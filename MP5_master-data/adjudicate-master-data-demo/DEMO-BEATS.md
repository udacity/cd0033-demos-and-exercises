# Demo beats — Stewardship on the ambiguous band (record in your voice)

Keep it light — this shows the resolution bands and adjudicates one pair; the exercise is all six pairs plus the stewardship log.

- Open on the premise: entity resolution in a federated platform has three bands — `auto-merge` for
  high-confidence matches, `reject` for clear non-matches, and the **ambiguous band** where
  automation stops and a human steward must decide.
- Connect with `GovernedCatalog("trailhead.db")` and run `gc.resolve_customers()`. Point out the
  band counts: 2 auto-merged, 6 ambiguous waiting in the steward queue, 0 rejected.
- Compare the `auto-merge` pairs (`score == 1.0`, identical name and email) with row `0` of
  `m.ambiguous` (`score == 0.80`, same name and email local-part, swapped domain).
- Demonstrate `apply_adjudications(m, decisions={0: "accept"})` on that single pair. Point out the
  returned `merges` DataFrame: `golden_id`, `merged_id`, and the deterministic survivorship rule
  (`lowest customer_id wins` — the loyalty system of record). Contrast with why a last-name-only
  match must be rejected (false merge = cross-customer PII breach).
- Hand off: "in the exercise you'll adjudicate all six ambiguous pairs, apply them, and write the
  stewardship decision log and survivorship rule."
