# Document Courier Service

Sends completed prior authorization applications and receives responses from insurers. Routes to the proper delivery method based on the healthcare provider's requirements. Used by [Agent Pipeline](agent_pipeline.md) Step 6.

## Courier Classes

- **Courier Service** (base) — Routes to the correct subclass based on the provider's requirements.
- **Fax Service** (subclass) — Configured and used to send fax-based authorizations.
- **Email Service** (subclass) — Configured and used to send email-based authorizations.

## Email Service

while normally a system like FAX is used to send over the prior authorization request, the email service will be used for the demo of the hackathon. prior authorization emails should be sent to "michael.lavery.2017@gmail.com". Use Amazon SES to send prior authorization email requests, the email should include the patient name, provider name, insurance name, and attach the required and completed prior authorization paperwork. Patient name and insurance fields are read from the `patient` snapshot on the pa_request record (originally hydrated from [`pa_patients`](patient_data.md) at Agent Pipeline Step 0). There will be email replies and feed rejection reasons back into the [Self Improvement](self_improvement.md) pipeline for appeal. the responses will come simply in the form of either "accepted" or "rejected. Reasons: '...' ". 

## AWS Ownership

This spec owns:
- **Amazon SES** — Sends PA emails and receives insurer responses.
- **SQS: `pa-ses-responses`** — SES incoming email notifications land here for async processing.

This spec reads from:
- **S3: `pa-completed-forms`** (owned by [Document Population](document_population.md)) — To attach completed forms to outgoing emails.

SQS is consumed by:
- [Self Improvement](self_improvement.md) — Reads rejection messages from the queue.

## Submission Result Schema (to Agent Pipeline Step 7)

```json
{
  "submission_id": "sub_m1n2o3",
  "delivery_method": "email",
  "delivery_details": {
    "ses_message_id": "0100018f-1234-5678-abcd-example",
    "recipient_email": "pa-submissions@medi-calrx.dhcs.ca.gov",
    "sender_email": "pa-bot@ourclinic.example.com",
    "subject": "Prior Authorization Request - Jane Doe - MC-9876543 - adalimumab",
    "attachment_s3_key": "pa-completed-forms/att_x7y8z9/1.pdf"
  },
  "submitted_at": "2026-04-19T14:35:00Z",
  "status": "sent"
}
```
