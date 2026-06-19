# Solution beats — Configure Governed Access exercise (record in your voice)

- Restate: four personas, four Lake Formation modes, on the customer table.
- `make_catalog`, confirm `live`; show the empty grant state.
- Apply each grant, naming the mode: column (analyst, exclude email/phone), row (cs_rep EU
  filter), tag-based (steward via governed=true), metadata-only (auditor).
- Run `verify_step7` — walk each PASS: analyst has no PII columns, cs_rep sees only EU rows,
  steward sees everything via the tag, auditor can DESCRIBE but SELECT is denied.
- Land the principles: least privilege (auditor), and tag-based grants so new governed tables
  inherit access. Note the common mistake of declaring access without verifying enforcement.
