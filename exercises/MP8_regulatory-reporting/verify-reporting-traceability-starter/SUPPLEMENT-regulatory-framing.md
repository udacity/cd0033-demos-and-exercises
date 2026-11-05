# Supplemental Exercise: Regulatory Justification

> Add this section after your traceability assessment in the exercise notebook.

## Regulatory Framing

Answer the following about the carbon unit defect you identified:

1. **Which CSRD article** requires that disclosed figures be traceable to source data?
2. **What is the magnitude of the error?** (Estimate: how many kg of carbon are over-reported due to the grams-vs-kg defect across all quarters?)
3. **What is the regulatory consequence** if this disclosure goes to market without correction? (Consider: restatement risk, auditor qualification, greenwashing perception)
4. **How does lineage (MP6) help prove the defect's origin?** Trace the path from `shipment.carbon_kg` through to `quarterly_sustainability.disclosed_carbon_kg`.

### Your answers

1. TODO
2. TODO (hint: filter `per_order` for `carbon_kg > 100`, sum, and subtract the normalized sum)
3. TODO
4. TODO

**Key insight**: CSRD Article 29a requires that sustainability disclosures are "faithful, verifiable, and traceable to underlying records." A unit-of-measure defect that inflates carbon figures is exactly the kind of material misstatement an external auditor would qualify. The lineage from MP6 is your forensic evidence that the defect originated in shipment ingestion, not in the reporting pipeline itself.
