# Document Courier Service

Sends completed prior authorization applications and receives responses from insurers. Routes to the proper delivery method based on the healthcare provider's requirements. Used by [Agent Pipeline](agent_pipeline.md) Step 6.

## Courier Classes

- **Courier Service** (base) — Routes to the correct subclass based on the provider's requirements.
- **Fax Service** (subclass) — Configured and used to send fax-based authorizations.
- **Email Service** (subclass) — Configured and used to send email-based authorizations.

## Email Service

Use Amazon SES to send prior authorization email requests. Take responses from Amazon SES and feed rejection reasons back into the [Self Improvement](self_improvement.md) pipeline for appeal.
