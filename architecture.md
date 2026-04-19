# Prior Authorization Bot — System Architecture

## Motivation

Applying for prior authorization is a friction point for physicians and patients alike. We would like to automate this process to enable swift care of patients and reduce the load and burnout of physicians.

## Context

We are trying to win a hackathon under the track of best use of AWS. This doesn't mean use as many services as possible but a genuinely creative and effective use of their products to solve a problem. Assume we have unlimited use of AWS so if you think any service is useful then implement it.  
Example PA form: [https://medi-calrx.dhcs.ca.gov/cms/medicalrx/static-assets/documents/provider/forms-and-information/Medi-Cal\_Rx\_PA\_Request\_Form.pdf\#page=1.00\&gsr=0](https://medi-calrx.dhcs.ca.gov/cms/medicalrx/static-assets/documents/provider/forms-and-information/Medi-Cal_Rx_PA_Request_Form.pdf#page=1.00&gsr=0)

## System Overview

A physician uploads an audio recording of a patient appointment. The system transcribes the recording, extracts medical entities (prescriptions, surgeries, therapies), and determines which treatments require prior authorization by checking against the patient's insurance provider. For each treatment requiring PA, the system selects the appropriate blank form, retrieves relevant memories from past applications, and uses an LLM to populate the form with patient data and learned context.

Completed forms are sent to the insurer through the appropriate channel (email or fax). When an application is approved, the system saves what worked to its memory for future reference. When rejected, a self-improvement pipeline analyzes the rejection, refines the application, and resubmits — learning from each attempt.

Two dashboards provide visibility: a physician-facing dashboard for submitting recordings and tracking requests, and a pipeline dashboard for monitoring system health and PA status across all stages.

## Agent Pipeline

The core orchestration is a 7-step agent pipeline that moves from entity extraction through form submission and outcome handling. It coordinates all services below to process a single prior authorization request end-to-end.

Full specification: [Agent Pipeline](agent_pipeline.md)

## Services

| Service | Description | Spec |
|---------|-------------|------|
| Speech to Text | Transcribes appointment recordings into text | [speech_to_text.md](speech_to_text.md) |
| Search | Finds relevant forms and memories for PA applications | [search_service.md](search_service.md) |
| Memories | Stores and retrieves learnings to improve future applications | [memory_feature.md](memory_feature.md) |
| Document Download | Finds and downloads blank PA forms from providers | [document_download.md](document_download.md) |
| Document Population | Fills blank forms with patient data using LLM | [document_population.md](document_population.md) |
| Document Courier | Sends completed forms to insurers via email or fax | [document_courier.md](document_courier.md) |
| Self Improvement | Handles rejections and iterates on appeals | [self_improvement.md](self_improvement.md) |

## Dashboards

| Dashboard | Description | Spec |
|-----------|-------------|------|
| Pipeline Dashboard | Monitor pipeline health, AWS diagnostics, and PA status | [pipeline_dashboard.md](pipeline_dashboard.md) |
| Physician Dashboard | Submit recordings, search and track PA requests | [physician_dashboard.md](physician_dashboard.md) |

## Communication Strategy

**Architecture: Modular Monolith with FastAPI Gateway**

All service modules live in a single Python process. The agent pipeline orchestrator imports and calls service classes directly via typed Python interfaces. No HTTP between internal services.

| Boundary | Mechanism | Why |
|---|---|---|
| Between pipeline steps (1-7) | Direct Python function calls | Pipeline is sequential — no network overhead needed |
| Physician Dashboard -> Backend | REST API (FastAPI) | Standard HTTP for uploads and queries |
| Pipeline status -> Dashboards | WebSocket via DynamoDB Streams | Real-time updates without polling |
| SES rejection responses -> Self Improvement | SQS queue | Only truly async boundary — insurer replies arrive hours/days later |
| All services -> Pipeline state | DynamoDB `pa_requests` table | Each step writes status before proceeding; dashboards read it |

When the physician dashboard POSTs an audio file, the API returns immediately with a `pa_request_id` and enqueues the pipeline run as a background task. Each step writes its status to the DynamoDB `pa_requests` table as it progresses. DynamoDB Streams pushes status changes to connected dashboard WebSocket clients for real-time updates.

## AWS Resource Ownership

Principle: **the spec that writes to a resource owns its creation. Consumers hold read-only references.**

| AWS Resource | Owner Spec | Readers | Notes |
|---|---|---|---|
| **S3: `pa-audio-uploads`** | `speech_to_text` | `agent_pipeline` | Audio files uploaded by physician dashboard, consumed by Transcribe |
| **S3: `pa-blank-forms`** | `document_download` | `document_population`, `search_service` | Structure: `/{provider_name}/{form_name}.pdf` |
| **S3: `pa-textract-output`** | `document_download` | `document_population` | Structure: `/{provider_name}/{form_name}.json` |
| **S3: `pa-completed-forms`** | `document_population` | `document_courier`, dashboards | Structure: `/{attempt_hash}/1.pdf, 2.pdf, ...` |
| **AWS Transcribe** | `speech_to_text` | — | Sole user |
| **AWS Comprehend Medical** | `agent_pipeline` (Step 1) | — | InferRxNorm, InferSNOMEDCT, DetectEntitiesV2 |
| **AWS Textract** | `document_download` | — | Runs on blank forms to extract field structure |
| **Amazon SES** | `document_courier` | — | Send emails + receive rejection replies |
| **SQS: `pa-ses-responses`** | `document_courier` | `self_improvement` | SES incoming notifications land here |
| **DynamoDB: `pa_requests`** | `agent_pipeline` | All dashboards, all services (read) | Central pipeline state table |
| **DynamoDB: `pa_memories`** | `memory_feature` | `search_service` | 4 GSIs for access patterns |
| **DynamoDB: `pa_scrape_cache`** | `search_service` | — | TTL-based cache for web scraping results |
| **CloudWatch Metrics/Alarms** | `pipeline_dashboard` | — | Aggregates health from all services |
| **DynamoDB Streams** | `agent_pipeline` (on `pa_requests`) | `pipeline_dashboard` | Powers WebSocket real-time updates |

## Central PA Request Record

All pipeline state is stored in the DynamoDB `pa_requests` table. Every pipeline step reads and updates this record. See [Agent Pipeline](agent_pipeline.md) for the full schema and inter-step data contracts.
