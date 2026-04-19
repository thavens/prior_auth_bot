# Speech to Text

Converts doctor appointment recordings into text transcripts for the [Agent Pipeline](agent_pipeline.md).

## Requirements

1. Accept a recording of a doctor's appointment as input.
2. Use AWS Transcribe to extract a transcript of the appointment.

**Input:** Audio file (from [Physician Dashboard](physician_dashboard.md) recording submission)
**Output:** Text transcript (consumed by Agent Pipeline Step 1)

## AWS Ownership

This spec owns:
- **S3: `pa-audio-uploads`** — Stores uploaded audio files and transcripts. Structure: `/{pa_request_id}/appointment.wav`, `/{pa_request_id}/transcript.json`
- **AWS Transcribe** — Creates and manages transcription jobs.

## Output Schema

```json
{
  "transcript_text": "Patient presents with persistent lower back pain...",
  "transcript_s3_key": "pa-audio-uploads/pr_a1b2c3d4/transcript.json",
  "language_code": "en-US",
  "confidence": 0.94,
  "duration_seconds": 847
}
```
