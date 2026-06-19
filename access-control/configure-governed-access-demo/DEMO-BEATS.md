# Demo beats — Fine-grained access with Lake Formation on AWS (record in your voice)

Keep it light — this shows the *technique* on one persona; the exercise is all four.

- Premise: marketing needs customer data but must never see contact PII. Access is a control,
  not a trust exercise.
- `make_catalog("trailhead.db")`; confirm `lf_backend()` -> `live`. Show empty `grants_summary()`.
- `grant_columns("co_marketing_analyst", "customer", exclude=["email","phone"])` — narrate that
  this is a real Lake Formation column grant.
- `query_as("co_marketing_analyst", "SELECT * FROM customer LIMIT 5")` — point out email/phone
  are simply absent; Athena + Lake Formation enforced it, the analyst didn't have to behave.
- Hand off: "that's column-level for one persona — in the exercise you'll add row-level,
  tag-based, and metadata-only, and run the verification that proves all four."
