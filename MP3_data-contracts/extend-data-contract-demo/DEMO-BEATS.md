# Demo beats — A contract that carries policy (record in your voice)

Keep it light — this demonstrates contract validation on `customer`; the exercise is `orders` plus propagation reasoning.

- Open on the premise: a data contract is only a control if a pipeline can **validate** it. Prose
  in a wiki doesn't stop an ungoverned table from shipping.
- Show the ungoverned `customer_contract` dictionary (columns only, no `governance` block) and run
  `validate_contract(customer_contract)` -> `False` (`'governance' is a required property`).
- Show what `CONTRACT_SCHEMA` enforces by intentionally passing `"retention": "3 years"` and an
  empty `quality_slos: []` -> point out the exact schema errors (`^P\d+[YMD]$` ISO-8601 pattern
  and `minItems: 1`).
- Fix the governance block on `customer_contract` (`pii_tags` for `email`/`full_name`/`phone`,
  `retention: "P3Y"`, and `quality_slos` for validity, uniqueness, and consistency) and mark
  `col["pii"]` on the columns -> re-run `validate_contract()` -> `True`.
- Land the architectural point: now a CI gate can block deployment if a contract omits policy, and
  downstream systems can read `retention` and `pii_tags` to enforce deletion and column masking.
- Hand off: "in the exercise you'll govern the `orders` contract and write up how a retention
  change propagates upstream-first to producers and consumers."
