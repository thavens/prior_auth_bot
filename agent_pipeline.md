# Agent Pipeline

The agent pipeline is the core orchestration layer that coordinates all services to process a single prior authorization request from transcript to submission. It is triggered when a physician submits an appointment recording via the [Physician Dashboard](physician_dashboard.md).

## Pipeline Steps

### Step 1: Entity Extraction

Extract anything from the appointment transcript and patient data that may require prior authorization — prescriptions, surgeries, and therapies. Cast a wide net because downstream steps determine what actually requires prior authorization.

**AWS Services:** Comprehend Medical, InferRxNorm, InferSNOMEDCT, DetectEntitiesV2
**Input:** Transcript from [Speech to Text](speech_to_text.md), patient data
**Output:** List of candidate treatments

### Step 2: PA Requirement Determination

Use LLM with the context of treatments, patient data, and healthcare providers to find the treatments that require prior authorization. Use a web agent to scrape the provider's website. Cache the data retrieved from the web agent so it doesn't scrape every search.

**Input:** Candidate treatments, patient data, provider info
**Output:** Filtered list of treatments requiring PA

### Step 3: Form Selection

Using prescriptions that require prior authorization and user data, use LLM to search our list of blank forms. Pick the document that will be used to send the prior authorization.

**Depends on:** [Document Download](document_download.md), [Search Service](search_service.md)
**Input:** Treatments requiring PA, patient data
**Output:** Selected blank form(s)

### Step 4: Memory Retrieval

Search for relevant advice and previous successful prior authorizations to maximize the success rate of this application.

**Depends on:** [Memory Feature](memory_feature.md), [Search Service](search_service.md)
**Input:** Treatment context, provider, form type
**Output:** Relevant memories and advice

### Step 5: Document Population

Call a subagent who fills out the blank form using the document population service and the results of the memory search.

**Depends on:** [Document Population](document_population.md)
**Input:** Blank form, patient data, memory context
**Output:** Completed PA form

### Step 6: Document Submission

Send the filled document using the document courier service.

**Depends on:** [Document Courier](document_courier.md)
**Input:** Completed PA form, provider routing info
**Output:** Submission confirmation

### Step 7: Outcome Handling

Once sent, there will be two outcomes:

1. **Authorization** — Clean up. Save relevant learning experiences: what was effective, what was unnecessary.
2. **Rejection** — Leverage the [Self Improvement](self_improvement.md) pipeline to attempt a stronger appeal.

**Depends on:** [Memory Feature](memory_feature.md), [Self Improvement](self_improvement.md)

## Flow

```
Step 1 → Step 2 → Step 3 → Step 4 → Step 5 → Step 6 → Step 7
                                                          ↓
                                              ┌── Approved → Save to Memory
                                              └── Rejected → Self Improvement → Step 3
```

## AWS Ownership

This spec owns:
- **DynamoDB: `pa_requests`** — Central pipeline state table. Every step reads and updates this record.
- **DynamoDB Streams** on `pa_requests` — Powers real-time WebSocket updates to dashboards.
- **AWS Comprehend Medical** — InferRxNorm, InferSNOMEDCT, DetectEntitiesV2 (used in Step 1).

## Pipeline State Tracking

Each step updates the `pa_requests` DynamoDB record with its status before proceeding. The `status` field takes one of:

`"queued"` | `"step_1_entity_extraction"` | `"step_2_pa_determination"` | `"step_3_form_selection"` | `"step_4_memory_retrieval"` | `"step_5_document_population"` | `"step_6_document_submission"` | `"step_7_outcome_handling"` | `"completed_approved"` | `"completed_rejected_exhausted"` | `"failed"` | `"appealing"`

## Central PA Request Record (DynamoDB `pa_requests`)

```json
{
  "pa_request_id": "pr_a1b2c3d4",
  "created_at": "2026-04-19T14:30:00Z",
  "updated_at": "2026-04-19T14:32:15Z",
  "status": "step_5_document_population",
  "patient": {
    "patient_id": "pat_001",
    "first_name": "Jane",
    "last_name": "Doe",
    "dob": "1985-03-12",
    "insurance_provider": "medi-cal",
    "insurance_id": "MC-9876543",
    "address": "123 Main St, Sacramento, CA 95814",
    "phone": "916-555-0100"
  },
  "physician": {
    "physician_id": "doc_042",
    "first_name": "Robert",
    "last_name": "Chen",
    "npi": "1234567890",
    "specialty": "Oncology",
    "phone": "916-555-0200",
    "fax": "916-555-0201"
  },
  "audio_s3_key": "pa-audio-uploads/pr_a1b2c3d4/appointment.wav",
  "transcript": null,
  "entities": null,
  "treatments_requiring_pa": null,
  "selected_forms": null,
  "memories": null,
  "completed_form_s3_keys": null,
  "submission_result": null,
  "outcome": null,
  "attempt_number": 1,
  "attempt_hash": "att_x7y8z9",
  "rejection_history": [],
  "error": null
}
```

## Inter-Step Data Schemas

### Speech-to-Text -> Step 1

```json
{
  "transcript_text": "Patient presents with persistent lower back pain...",
  "transcript_s3_key": "pa-audio-uploads/pr_a1b2c3d4/transcript.json",
  "language_code": "en-US",
  "confidence": 0.94,
  "duration_seconds": 847
}
```

### Step 1 (Entity Extraction) -> Step 2

```json
{
  "entities": [
    {
      "entity_id": "ent_001",
      "category": "MEDICATION",
      "text": "Humira",
      "normalized": {
        "rxnorm_concept": "327361",
        "rxnorm_description": "adalimumab 40 MG/0.8 ML Pen Injector"
      },
      "snomed_concepts": [
        { "code": "391188009", "description": "Adalimumab therapy" }
      ],
      "traits": ["NEGATION:false", "PAST_HISTORY:false"],
      "confidence": 0.97
    }
  ]
}
```

### Step 2 (PA Determination) -> Step 3

```json
{
  "treatments_requiring_pa": [
    {
      "entity_id": "ent_001",
      "treatment_text": "Humira (adalimumab)",
      "category": "MEDICATION",
      "requires_pa": true,
      "pa_reason": "Specialty medication requiring step therapy documentation",
      "provider_name": "medi-cal",
      "source_url": "https://medi-calrx.dhcs.ca.gov/provider/forms/",
      "cached": true
    }
  ],
  "treatments_not_requiring_pa": []
}
```

### Step 3 (Form Selection) -> Step 4/5

```json
{
  "selected_forms": [
    {
      "treatment_entity_id": "ent_001",
      "form_s3_key": "pa-blank-forms/medi-cal/Medi-Cal_Rx_PA_Request_Form.pdf",
      "textract_s3_key": "pa-textract-output/medi-cal/Medi-Cal_Rx_PA_Request_Form.json",
      "form_name": "Medi-Cal Rx PA Request Form",
      "provider_name": "medi-cal",
      "field_count": 42,
      "field_types_summary": { "Text": 28, "CheckBox": 10, "RadioButton": 4 }
    }
  ]
}
```

### Step 4 (Memory Retrieval) -> Step 5

```json
{
  "memories": [
    {
      "memory_id": "mem_abc123",
      "memory_type": "treatment_provider",
      "treatment": "adalimumab",
      "provider": "medi-cal",
      "advice": "Include explicit dates for all prior DMARD trials...",
      "source_pa_request_id": "pr_prev_456",
      "success_count": 3,
      "relevance_score": 0.92
    }
  ]
}
```

### Step 5 (Document Population) -> Step 6

See [Document Population](document_population.md) for the full input/output schema including the LLM widget response format.

### Step 6 (Document Courier) -> Step 7

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

### Step 7 Outcome -> Memory / Self-Improvement

**Approval:**
```json
{
  "pa_request_id": "pr_a1b2c3d4",
  "outcome": "approved",
  "approved_at": "2026-04-22T08:00:00Z",
  "authorization_number": "AUTH-2026-78901"
}
```

**Rejection (via SQS -> Self Improvement):**
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
