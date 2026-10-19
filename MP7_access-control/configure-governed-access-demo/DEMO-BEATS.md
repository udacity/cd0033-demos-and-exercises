# Demo beats — Fine-grained access with Lake Formation on AWS (record in your voice)

Keep it light — this shows the *technique* on one persona and previews the Terraform governance chain; the exercise is all four personas.

- Premise: marketing needs customer data but must never see contact PII. Access is a control,
  not a trust exercise.
- `make_catalog("trailhead.db")`; confirm `lf_backend()` -> `live`. Show empty `grants_summary()`.
- `grant_columns("co_marketing_analyst", "customer", exclude=["email","phone"])` — narrate that
  this is a real Lake Formation column grant.
- `query_as("co_marketing_analyst", "SELECT * FROM customer LIMIT 5")` — point out `email`/`phone`
  are simply absent; Athena + Lake Formation enforced it, the analyst didn't have to behave.
- Inspect `terraform/governed-data-product/main.tf` — walk through the 5 numbered sections showing
  the **S3 -> Glue -> Lake Formation -> IAM** chain, and highlight that the consumer role has no
  direct `s3:GetObject` on the data bucket (only LF-mediated Athena access).
- Hand off: "that's column-level for one persona and how IaC wires the chain — in the exercise
  you'll add row-level, tag-based, and metadata-only grants, run `verify_step7()`, and analyze
  `main.tf`."
