# Current AWS Services

## S3 Buckets

### pa-audio-uploads
**Owner:** [Speech to Text](speech_to_text.md)
**Purpose:** Stores uploaded audio recordings and transcripts.
**Structure:**
```
pa-audio-uploads/
  {pa_request_id}/
    appointment.wav
    transcript.json
```

### pa-blank-forms
**Owner:** [Document Download](document_download.md)
**Purpose:** Stores downloaded blank PA forms with labeled AcroForm fields.
**Structure:**
```
pa-blank-forms/
  {provider_name}/
    {form_name}.pdf
```

### pa-textract-output
**Owner:** [Document Download](document_download.md)
**Purpose:** Stores AWS Textract analysis results for blank forms.
**Structure:**
```
pa-textract-output/
  {provider_name}/
    {form_name}.json
```

### pa-completed-forms
**Owner:** [Document Population](document_population.md)
**Purpose:** Stores filled PA forms ready for submission. Each PA session has its own directory with sequentially numbered forms for initial requests and appeals.
**Structure:**
```
pa-completed-forms/
  {attempt_hash}/
    1.pdf
    2.pdf
    ...
```

## DynamoDB Tables

### pa_requests
**Owner:** [Agent Pipeline](agent_pipeline.md)
**Purpose:** Central pipeline state table. Every pipeline step reads and updates this record. Dashboards query it for PA search and visualization.
**Key Design:** PK: `pa_request_id`
**Streams:** Enabled — powers real-time WebSocket updates to dashboards.

### pa_memories
**Owner:** [Memory Feature](memory_feature.md)
**Purpose:** Stores learnings from successful and failed PA applications to improve future submissions.
**Key Design:**
- PK: `memory_type` (`general` | `provider` | `treatment` | `treatment_provider`)
- SK: `memory_id`
- GSI-1: PK `provider` + SK `created_at`
- GSI-2: PK `treatment` + SK `created_at`
- GSI-3: PK `provider#treatment` (composite) + SK `success_count`

### pa_scrape_cache
**Owner:** [Search Service](search_service.md)
**Purpose:** TTL-based cache for web scraping results. Prevents redundant scraping on repeated searches.
**Key Design:** PK: `cache_key`
**TTL:** `ttl` attribute (epoch seconds, auto-expires stale entries)

## Compute / AI Services

### AWS Transcribe
**Owner:** [Speech to Text](speech_to_text.md)
**Purpose:** Converts audio recordings of doctor appointments into text transcripts.

### AWS Comprehend Medical
**Owner:** [Agent Pipeline](agent_pipeline.md) (Step 1: Entity Extraction)
**Purpose:** Extracts medical entities from transcripts. Uses InferRxNorm (medication normalization), InferSNOMEDCT (medical concept standardization), and DetectEntitiesV2 (entity detection).

### AWS Textract
**Owner:** [Document Download](document_download.md)
**Purpose:** Analyzes blank PA form PDFs to extract field structure, types, and positions.

## Messaging Services

### Amazon SES
**Owner:** [Document Courier](document_courier.md)
**Purpose:** Sends PA application emails to insurers and receives responses (approvals/rejections).

### SQS: pa-ses-responses
**Owner:** [Document Courier](document_courier.md)
**Purpose:** Receives SES incoming email notifications (insurer responses). Consumed by [Self Improvement](self_improvement.md) for rejection handling.

## Monitoring

### CloudWatch Metrics/Alarms
**Owner:** [Pipeline Dashboard](pipeline_dashboard.md)
**Purpose:** Aggregates health metrics from all AWS components. Defines alarm thresholds for the pipeline visualizer (green/red stage indicators) and the AWS analytics module.

### DynamoDB Streams (on pa_requests)
**Owner:** [Agent Pipeline](agent_pipeline.md)
**Purpose:** Emits change events when pipeline state updates. Consumed by dashboards via WebSocket for real-time status display.
