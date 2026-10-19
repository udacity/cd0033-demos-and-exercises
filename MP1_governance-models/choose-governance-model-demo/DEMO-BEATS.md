# Demo beats — Mapping a federated platform to a governance operating model (record in your voice)

Keep it light — this inspects the four domains and models one RACI row and a two-domain topology slice; the exercise is the full operating model.

- Open on the premise: governance is an operating model before it is technology. When four
  autonomous domain teams share one platform under GDPR and CSRD pressure, you must decide what stays
  central and what stays federated.
- Connect with `GovernedCatalog("trailhead.db")` and display the 8-table domain inventory. Point out
  that tables span four domains and several already lack an `owner` or `classification`.
- Run `gc.semantic_conflicts()` and `gc.lineage.events()` to show why pure decentralization fails:
  Marketing and Loyalty disagree on customer identity and consent (GDPR risk), while Orders and
  Inventory feed a single CSRD carbon disclosure.
- Walk through one sample RACI row (`Classification taxonomy`): show all four domains as
  Responsible (`R`) for tagging their own assets, and the Central Governance Lead as the **single
  Accountable (`A`)** owner. Emphasize the hard rule: two `A`s in one row means nobody is
  accountable.
- Show the two-domain Mermaid topology slice (`Core` -> `Customer` -> `Marketing`) so learners see
  the diagram syntax.
- Hand off: "in the exercise you'll justify the governance model for Trailhead Provisions, complete
  the RACI across all governance functions, and draw the full four-domain topology."
