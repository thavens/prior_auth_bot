# Self Improvement Pipeline

Handles prior authorization rejections by analyzing feedback, improving applications, and resubmitting appeals. Invoked by [Agent Pipeline](agent_pipeline.md) Step 7 on rejection.

## Rejection with Reasons

When a rejection includes a description of the reasons, search through the patient's data to make necessary fixes and resend the prior authorization using the existing pipeline components. "Patient's data" here refers to the `patient` snapshot on the in-flight `pa_request` (originally hydrated from [`pa_patients`](patient_data.md) at Step 0); the snapshot is authoritative for the lifetime of the attempt so that in-flight appeals are not perturbed by concurrent edits to the source record. Integrate the feedback into additional context that is provided at all stages of the pipeline. On success, save the feedback into the [Memory](memory_feature.md) subsystem.

## Rejection without Reasons

When a rejection provides no reasoning, propose potential reasoning in an experimental format. Iterate through a ranked list of most likely helpful to least likely helpful changes, and use informed guesses to maximize chances in the appeals process. On success, save the successful brainstormed change into the [Memory](memory_feature.md) subsystem.

## AWS Dependencies

This spec reads from:
- **SQS: `pa-ses-responses`** (owned by [Document Courier](document_courier.md)) — Consumes rejection/approval messages from insurers.

This spec writes to:
- **DynamoDB: `pa_memories`** (owned by [Memory Feature](memory_feature.md)) — Saves learnings on successful appeals.

## Rejection Input Schema (from SQS)

```json
{
  "pa_request_id": "pr_a1b2c3d4",
  "submission_id": "sub_m1n2o3",
  "outcome": "rejected",
  "has_reasons": true,
  "rejection_reasons": [
    "Insufficient documentation of step therapy failure.",
    "Missing prescriber NPI on page 2."
  ],
  "received_at": "2026-04-21T10:00:00Z"
}
```

## Re-entry Payload (back to Agent Pipeline Step 3)

```json
{
  "pa_request_id": "pr_a1b2c3d4",
  "attempt_number": 2,
  "attempt_hash": "att_q2r3s4",
  "mode": "rejection_with_reasons",
  "rejection_context": {
    "previous_attempt_hash": "att_x7y8z9",
    "rejection_reasons": [
      "Insufficient documentation of step therapy failure.",
      "Missing prescriber NPI on page 2."
    ],
    "proposed_fixes": [
      "Add explicit dates for methotrexate trial (2025-10-01 to 2025-12-24)",
      "Populate NPI field (Text_12) with physician NPI 1234567890"
    ]
  }
}
```
