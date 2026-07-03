# Demo beats — A contract that carries policy (record in your voice)

- Premise: a contract should be validated, not just read. Show the ungoverned `orders` contract
  failing validation — no governance block.
- Add the governance block (pii_tags, retention P7Y, quality_slos); re-validate -> passes.
- Land the point: now a CI gate can refuse to publish a product whose contract fails.
- Hand off: in the exercise you'll govern this contract and explain how a retention change
  propagates upstream-first to producers and consumers.
