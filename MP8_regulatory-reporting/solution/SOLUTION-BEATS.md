# Solution beats — Verify Reporting Traceability exercise (record in your voice)

- Run the report; reconciliation shows a large delta every quarter.
- Trace one quarter to per-shipment rows; isolate carbon_kg > 100 (the grams slice).
- Land the distinction: traceability holds, integrity breaks at the unit boundary — the number is
  auditable to a wrong value.
- Fix: downstream normalization + a carbon_kg>100 monitor; metric definition must be central.
