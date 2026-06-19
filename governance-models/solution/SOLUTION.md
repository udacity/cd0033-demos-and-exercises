# Solution — Choose a Governance Model

## Summary

The defensible answer is **federated governance with a thin central core**: domains keep
ownership while a small set of decisions (PII classification, consent system of record, contract
schema, shared metric definitions) are centralized and gate publication — the least
centralization that satisfies GDPR and CSRD without a bottleneck.

## Key points

- **Why not centralized:** four independently-shipping domains; a central rewrite stalls on friction.
- **Why not decentralized:** that is today's state, and it produced the audit failure.
- **RACI:** one accountable owner per function (Central Governance Lead for classification &
  access; Customer Identity Lead for consent; domain leads for contracts & quality; Platform
  Engineering for lineage; CSRD Owner for the carbon metric), with a Governance Council for escalation.
- **Topology:** central core → standards/gates to four domains; consent SoR flows loyalty→marketing;
  order+carbon flow into the CSRD report.

## Common Mistakes to Avoid

- **Choosing centralized for "control"** without weighing the four-team political/bottleneck cost.
- **A RACI with multiple accountable owners** for one function — accountability must be singular.
- **Listing roles but no enforcement/escalation** — governance needs a gate and a tie-breaker.
- **A topology that omits the cross-domain flows** (consent, order→carbon→report) that drive the obligations.
