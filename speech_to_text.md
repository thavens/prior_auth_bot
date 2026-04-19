# Speech to Text

Converts doctor appointment recordings into text transcripts for the [Agent Pipeline](agent_pipeline.md).

## Requirements

1. Accept a recording of a doctor's appointment as input.
2. Use AWS Transcribe to extract a transcript of the appointment.

**Input:** Audio file (from [Physician Dashboard](physician_dashboard.md) recording submission)
**Output:** Text transcript (consumed by Agent Pipeline Step 1)
