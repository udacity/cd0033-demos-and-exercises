# Demo beats — Reading quality results & choosing a strategy (record in your voice)

Keep it light — this demonstrates reading the quality suite and classifying one failure; the exercise is all failing expectations.

- Open on the premise: quality results are decisions, not a scoreboard. A failing expectation
  tells you *what* broke, but an architect must decide *where* to handle it: `source`,
  `downstream`, or `quarantine`.
- Connect with `GovernedCatalog("trailhead.db")` and run `gc.run_quality_suite()`. Point out the
  Great Expectations-shaped schema (`expectation_type`, `dimension`, `unexpected_count`,
  `unexpected_percent`) and that 8 of 9 expectations fail.
- Run the `groupby("dimension")` rollup to see where the platform is weakest across the six
  quality dimensions (uniqueness passes; validity, completeness, accuracy, timeliness, and
  consistency have failures).
- Filter to one specific failure (`customer.email` failing `validity`) and map it via a dictionary
  (`sample_remediation = {"customer.email": "quarantine"}`). Explain why PII validity failures get
  quarantined first: active GDPR harm and broken contact workflows.
- Hand off: "in the exercise you'll map every failing `table.column` to `source`, `downstream`,
  or `quarantine` and write a remediation plan prioritized by regulatory severity."
