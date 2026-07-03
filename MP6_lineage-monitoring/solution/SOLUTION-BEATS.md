# Solution beats — Trace Lineage & Specify Monitoring exercise (record in your voice)

- Trace downstream of customer (customer_360, marketing_audience) and upstream of the CSRD report.
- Build the monitoring table: signal, source, threshold, owner, SLA/regulation.
- Land the gap: no monitor on the customer_id<->cust_ref match quality — add match-rate monitoring
  on build_customer_360.
