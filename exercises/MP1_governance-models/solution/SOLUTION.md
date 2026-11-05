# Solution — Choose a Governance Model

## Summary

The defensible answer is **federated governance with a thin central core**: domains keep
day-to-day ownership of their data products while a small set of platform-wide decisions
(PII classification taxonomy, consent system of record, data contract standard, data quality SLO
policy, and shared CSRD metric definitions) are governed centrally and gate publication — the
least centralization that satisfies GDPR and CSRD without creating a single-team bottleneck.

## Key points

- **Why not centralized:** four independently-shipping domains acquired from separate brands; a central team rewriting every pipeline stalls on organizational friction.
- **Why not decentralized:** that is today's state, and it produced the audit failure (conflicting consent records, missing catalog metadata, uninstrumented lineage).
- **Role alignment (central/platform vs. domain):**
  - **Central / platform side:** **Central Governance Lead**, **CSRD Reporting Owner** (Finance-appointed), and **Platform Engineering**.
  - **Domain side:** **E-commerce Orders Lead**, **Customer Identity Lead**, **Inventory & Fulfillment Lead**, and **Marketing & Campaigns Lead**.
- **RACI (singular accountability on every row):**
  - **PII classification & tagging:** **Central Governance Lead** (`A`), all four domain leads (`R`).
  - **Consent system of record:** **Central Governance Lead** (`A`) owns the cross-domain consent standard and designates loyalty (`customer.marketing_consent`) as the authoritative system of record; **Customer Identity Lead** (`R`) maintains the loyalty consent table; **Marketing & Campaigns Lead** (`C`) consumes the governed consent feed; **E-commerce Orders Lead** and **Inventory & Fulfillment Lead** (`I`).
  - **Data contract standard:** **Central Governance Lead** (`A`) owns the required schema and publish gate; the four domain leads (`R`) author and maintain contracts for their domain products.
  - **Data quality SLO policy:** **Central Governance Lead** (`A`) sets the platform minimum SLO policy; the four domain leads (`R`) implement and meet SLOs on their products.
  - **Lineage instrumentation:** **Platform Engineering** (`A`), **Inventory & Fulfillment Lead** (`R` for shipment/carbon job emits), other domain leads (`C`).
  - **Carbon metric definition:** **CSRD Reporting Owner** (`A`), **Inventory & Fulfillment Lead** (`R`), **Marketing & Campaigns Lead** (`C`), **E-commerce Orders Lead** and **Customer Identity Lead** (`I`).
  - **Access policy (Lake Formation):** **Central Governance Lead** (`A`), **Customer Identity Lead** (`R`), other domain leads (`C`).
  - **Enforcement & escalation:** the **Central Governance Lead** can block a data product from publishing if it fails the classification, contract, or consent gate; unresolved cross-domain disputes (such as consent system-of-record conflicts between Loyalty and Marketing) escalate to the **Data Governance Council** chaired by the **Central Governance Lead**.
- **Topology:** central core (`GC`) pushes standards & gates to all four domains; loyalty consent flows from `D2` (`Customer Identity & Loyalty`) through `GC` (`D2 -- loyalty consent --> GC -- authoritative consent SoR --> D4`) to `D4` (`Marketing & Campaigns`); order and shipment carbon data flow from `D1` and `D3` into `R` (`CSRD Quarterly Report`).

## Common Mistakes to Avoid

- **Choosing centralized for "control"** without weighing the four-team political and delivery bottleneck cost.
- **A RACI with collective or multi-person `A`s** (such as `"Owning domain lead (per product)"`) — every row in a RACI must name a **single individual Accountable (`A`) owner**. Separate setting the platform standard (`A`: **Central Governance Lead**) from executing per-product contracts and SLOs (`R`: the four domain leads).
- **Making Customer Identity Lead `A` for cross-domain consent** while Marketing disputes it — because the consent conflict crosses domains, the **Central Governance Lead** must be `A` for the enterprise consent system-of-record policy, with **Customer Identity Lead** as `R`.
- **Introducing roles in the RACI that weren't mapped to the operating model** — explicitly place **Platform Engineering** and **CSRD Reporting Owner** on the central/platform side alongside the **Central Governance Lead**.
- **Listing roles but no enforcement/escalation** — governance needs a publish gate and a tie-breaker.
- **A topology that omits the cross-domain flows** (consent routed via `GC`, and order → carbon → CSRD report) that drive the regulatory obligations.
