# Optional Stretch: Automation Roadmap

> This optional section prepares you for the capstone's "Stand Out" suggestions.

## Challenge

You ran the governance audit manually. **Design an automation roadmap** showing how Steps 2, 7, and 9 could run as scheduled governance pipelines:

1. **Trigger**: What runs the audit? (Cron? EventBridge? On each data load?)
2. **Auto-remediation**: Which findings can be fixed without human judgment? (e.g., setting `retention` on a new table to the domain default)
3. **Human-in-the-loop**: Which findings MUST go to a steward? (e.g., PII classification requires judgment — is `loyalty_tier` PII?)
4. **Architecture**: Sketch the pipeline (EventBridge → Step Functions → Lambda → Glue/LF API → SNS notification)
5. **Drift detection**: How do you detect that a previously-compliant table has DRIFTED back to non-compliance? (Hint: compare current audit output to last week's.)

### Your roadmap

TODO (optional — but the capstone rubric's "Stand Out" section asks you to "design an automation roadmap showing how Steps 2, 7, and 9 could run as scheduled governance pipelines")
