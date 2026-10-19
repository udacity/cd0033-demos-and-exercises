# Supplemental Exercise: Mini-Brief Preview

> Add this section after your RACI matrix and topology in the exercise notebook.

## Preview: The Architect's Brief Format

In the capstone project, you'll write a full Architect's Brief — a 1–2 page executive synthesis. Here's a 2-paragraph example of what that looks like, based on YOUR governance model choice:

### Example mini-brief (provided)

> *Trailhead Provisions operates a federated governance model with a thin central core: each of
> the four domain teams owns its data products end-to-end (catalog, quality, access), while a
> central governance function sets policy (PII classification standards, retention minimums,
> access-control baselines) and operates the audit loop. This balances domain autonomy with the
> consistency required by GDPR and CSRD — domains move fast on their data, but cannot ship a
> table to production without meeting the baseline controls the audit checks for.*
>
> *The key tradeoff is enforcement latency vs. domain velocity: a centralized model would catch
> gaps before they go live (pre-publish gate), but would bottleneck four teams through one
> approval queue. Our federated model catches gaps post-publish (weekly audit) — fast enough for
> GDPR compliance (30-day remediation window) while preserving domain autonomy. The risk is a
> gap surviving one audit cycle before detection; we mitigate with real-time alerting on
> high-severity findings (untagged PII, ungoverned access) via the dashboard spec.*

### Your turn (optional, for practice)

Write 2 paragraphs synthesizing YOUR governance model choice. Include:
- What model you chose and why it fits Trailhead's 4-domain structure
- One tradeoff you navigated and how you resolved it

This is optional for this exercise but directly prepares you for the capstone's Step 10.
