# Solution beats — Extend a Data Contract exercise (record in your voice)

- Restate: turn governance intent into a machine-checkable contract.
- Show the base contract failing; add pii_tags, retention (P7Y), quality_slos; re-validate -> pass.
- Walk propagation: producers (SLOs + retention), consumers (PII inheritance via customer_id join),
  mechanism (version-bump + schema publish gate, upstream-first).
- Note the common mistakes: retention format, empty quality_slos, missing the downstream PII inheritance.
