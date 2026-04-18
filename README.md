# Prior Authorization Bot

**Automated Prior Authorization using AWS**

---

## Overview

Prior authorization is one of the biggest friction points in healthcare today. Physicians spend an average of 16 hours per week on paperwork, and prior authorization accounts for a disproportionate share of that burden. Delayed approvals mean delayed care, frustrated patients, and burned-out doctors.

The **Prior Authorization Bot** is an intelligent, end-to-end system that automates the entire prior authorization lifecycle. It ingests a recording of a doctor's appointment, extracts medical entities, determines which treatments require prior authorization, selects and fills the correct forms, submits them to the insurance provider, and -- critically -- **self-improves from rejections** to increase approval rates over time.

The system is built entirely on AWS and leverages 12 services in a genuinely integrated architecture, not as a checklist, but because each service solves a specific problem in the pipeline.

---

## AWS Services Used

| Service | Role |
|---|---|
| **Amazon S3** | Central data lake for recordings, transcripts, patient data, blank forms, filled forms, and payer responses |
| **Amazon Transcribe** | Speech-to-text conversion for doctor appointment recordings (MP3, WAV, FLAC) |
| **AWS Comprehend Medical** | Medical entity extraction using InferRxNorm, InferSNOMEDCT, and DetectEntitiesV2 to identify medications, procedures, diagnoses, and dosages |
| **Amazon Bedrock (Claude)** | LLM backbone for PA requirement determination, form filling, rejection analysis, brainstorming improvements, and self-improvement reasoning |
| **Amazon Bedrock (Titan)** | Text embedding model for generating vector representations used in semantic search |
| **Amazon OpenSearch Serverless** | Vector search engine for matching treatments to the correct blank PA forms and retrieving relevant memories |
| **AWS Lambda** | 10 microservice functions implementing each discrete pipeline step, plus a shared utility layer |
| **AWS Step Functions** | Orchestrates the full pipeline with branching logic (approval vs. rejection paths), retry loops for self-improvement, and parallel treatment processing |
| **Amazon SES** | Email-based courier for submitting PA requests to insurance providers and receiving approval/rejection responses |
| **Amazon DynamoDB** | Three tables -- web scrape cache (with TTL), structured memories (with GSIs for document/provider/prescription lookups), and PA request tracking |
| **Amazon SNS** | Real-time email notifications on PA status changes (submitted, approved, rejected, retry) |
| **Amazon CloudWatch** | Centralized monitoring dashboard with per-function invocation/error/duration graphs, Step Functions execution metrics, and per-function error alarms |

---

## Architecture

The system operates as a **7-step agent pipeline**, orchestrated by AWS Step Functions with a self-improvement feedback loop:

### Step 1: Speech-to-Text
The pipeline begins when an appointment recording (MP3/WAV/FLAC) is uploaded to S3. An S3 event notification triggers the **Transcribe Lambda**, which starts an Amazon Transcribe job and stores the resulting transcript in S3.

### Step 2: Medical Entity Extraction
The **Extract Entities Lambda** passes the transcript through AWS Comprehend Medical's three APIs:
- **InferRxNorm** -- identifies medications and maps them to standard RxNorm codes
- **InferSNOMEDCT** -- identifies clinical concepts and maps them to SNOMED CT codes
- **DetectEntitiesV2** -- extracts diagnoses, procedures, dosages, and other medical entities

The system casts a wide net at this stage because the next step determines what actually requires PA.

### Step 3: PA Requirement Determination
The **PA Check Lambda** uses Bedrock (Claude) with the context of extracted treatments, patient data, and insurance provider information to determine which treatments require prior authorization. A web agent scrapes provider websites for formulary and PA requirement data, with results cached in DynamoDB (with TTL) to avoid redundant scraping.

### Step 4: Form Selection
For each treatment requiring PA, the **Form Selection Lambda** generates a Titan embedding of the treatment context and performs a vector search against the OpenSearch Serverless `blank-forms` index. The top candidates are then re-ranked by the LLM to select the most appropriate form.

### Step 5: Memory Search
The **Memory Search Lambda** queries the 4-dimensional memory system (see below) to retrieve relevant advice, past successful applications, and learned patterns. This context is injected into the form-filling step to maximize approval probability.

### Step 6: Document Population
The **Document Population Lambda** reads the blank PDF form, extracts its AcroForm fields (field names, types, descriptions, required flags), and passes them to the LLM along with patient data, treatment details, and memory context. The LLM returns field values, which are written into the PDF. The filled form is saved to S3 with a traceable label: `pa_{patient_id}_{treatment_code}_{timestamp}.pdf`.

### Step 7: Document Submission
The **Document Courier Lambda** attaches the filled PDF and sends it via Amazon SES to the insurance provider's PA intake address. The PA request is tracked in DynamoDB with status `SUBMITTED`, and an SNS notification is published.

### Step 8: Response Handling
When a response arrives:
- **Approved**: The **Response Handler** saves successful strategies as memories across all applicable tiers (global, document, provider, prescription) so future applications benefit from what worked.
- **Rejected**: The **Self-Improvement Handler** analyzes the rejection and triggers a retry loop (see below).

---

## Self-Improvement Pipeline

The self-improvement system operates in two modes depending on the information available:

### Mode 1: Rejection with Reasons
When the rejection includes specific reasons (e.g., "Missing diagnosis code", "Insufficient clinical justification"), the Self-Improvement Handler:
1. Parses the rejection reasons
2. Searches patient data for the missing information
3. Queries the memory system for advice on handling similar rejections
4. Generates targeted fixes using the LLM
5. Re-enters the pipeline at the Document Population step with augmented context

### Mode 2: Rejection without Reasons
When no rejection reasons are provided, the system:
1. Uses the LLM to brainstorm a **ranked list** of the most likely issues, from most probable to least probable
2. Selects the top-ranked improvement
3. Applies it and resubmits
4. On continued rejection, moves to the next candidate in the ranked list
5. On success, saves the successful brainstormed improvement as a memory for future use

In both modes, the Step Functions state machine manages the retry loop with a configurable maximum attempt count, and the self-improvement handler can feed the pipeline back into the Document Population step.

---

## Memory System

The memory system is a **4-tier architecture** that balances breadth and specificity. Memories are stored in both DynamoDB (for structured lookup via GSIs) and OpenSearch Serverless (for semantic vector search via Titan embeddings).

| Tier | Scope | Example |
|---|---|---|
| **Global** | Applicable to all PA applications | "Always include ICD-10 codes in the diagnosis field" |
| **Per-Document** | Specific to a form type | "Medi-Cal Rx form requires NDC number in field 14" |
| **Per-Provider** | Specific to an insurance company | "Aetna requires step therapy documentation for biologics" |
| **Per-Prescription** | Specific to a medication or treatment | "Humira PA requires TB test results within last 6 months" |

During form filling, all four tiers are queried and the results are merged, with more specific memories taking precedence. Each memory tracks `success_count` and `failure_count` to enable confidence-weighted retrieval.

---

## Project Structure

```
prior_auth_bot/
├── app.py                          # CDK app entry point
├── cdk.json                        # CDK configuration
├── pyproject.toml                  # Python project metadata and dependencies
├── architecture.md                 # Detailed architecture notes
│
├── stacks/                         # CDK infrastructure
│   └── pa_bot_stack.py             #   All AWS resources in a single stack
│
├── lambdas/                        # Lambda function source code
│   ├── shared/                     #   Shared Lambda Layer
│   │   ├── models.py               #     Pydantic domain models
│   │   ├── pdf_utils.py            #     PDF form reader/writer
│   │   ├── bedrock_client.py       #     Bedrock LLM + embedding client
│   │   ├── comprehend_medical.py   #     Comprehend Medical wrapper
│   │   ├── opensearch_client.py    #     OpenSearch vector search client
│   │   ├── dynamo_client.py        #     DynamoDB client
│   │   ├── s3_client.py            #     S3 client
│   │   └── config.py               #     Environment configuration
│   │
│   ├── transcribe_handler/         #   Step 1: Speech-to-text
│   ├── extract_entities_handler/   #   Step 2: Medical entity extraction
│   ├── pa_check_handler/           #   Step 3: PA requirement determination
│   ├── form_selection_handler/     #   Step 4: Form selection via vector search
│   ├── memory_search_handler/      #   Step 5: Memory retrieval
│   ├── document_population_handler/#   Step 6: PDF form filling
│   ├── document_courier_handler/   #   Step 7: Email submission via SES
│   ├── response_handler/           #   Step 8a: Response processing + learning
│   ├── self_improvement_handler/   #   Step 8b: Self-improvement loop
│   └── embedding_handler/          #   Utility: Titan text embeddings
│
├── sample_data/                    # Sample data for testing
│   ├── recordings/                 #   Sample appointment recordings
│   ├── patient_data/               #   Sample patient JSON files
│   └── blank_forms/                #   Sample blank PA forms
│
├── scripts/                        # Operational scripts
│   ├── bootstrap.sh                #   Full setup script
│   ├── verify_ses.py               #   SES identity verification
│   ├── seed_opensearch.py          #   Seed OpenSearch with forms + memories
│   ├── trigger_pipeline.py         #   Trigger pipeline with a recording
│   └── simulate_response.py        #   Simulate payer approval/rejection
│
└── tests/                          # Test suite
    ├── unit/                       #   Unit tests
    │   ├── test_models.py          #     Domain model tests
    │   └── test_pdf_utils.py       #     PDF utility tests
    └── integration/                #   Integration tests
```

---

## Prerequisites

- **AWS CLI** configured with appropriate credentials (`aws configure`)
- **Node.js** >= 18 (required by AWS CDK)
- **Python** >= 3.12 (managed via `uv`)
- **uv** package manager (`brew install uv`)
- **AWS CDK** (`npm install -g aws-cdk`)
- An AWS account with access to Amazon Bedrock (Claude and Titan models must be enabled in us-east-1)

---

## Quick Start

```bash
# Clone and setup
git clone <repo-url>
cd prior_auth_bot

# Option 1: Automated setup
./scripts/bootstrap.sh

# Option 2: Manual setup
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e ".[dev]"

# Bootstrap CDK (first time only)
cdk bootstrap

# Deploy the stack
cdk deploy

# Verify SES email identity (check inbox for confirmation)
python scripts/verify_ses.py

# Seed OpenSearch with blank forms and initial memories
python scripts/seed_opensearch.py

# Run the pipeline with a sample recording
python scripts/trigger_pipeline.py --recording sample_data/recordings/sample_appointment.mp3

# Simulate a rejection response
python scripts/simulate_response.py \
  --pa-request-id <id> \
  --outcome REJECTED \
  --reasons "Missing diagnosis code"

# Simulate an approval response
python scripts/simulate_response.py \
  --pa-request-id <id> \
  --outcome APPROVED

# Run tests
pytest tests/ -v
```

---

## CDK Stack

All infrastructure is deployed as a single `PABotStack` in `stacks/pa_bot_stack.py`, organized into these sections:

| Section | Resources |
|---|---|
| **Storage** | S3 data bucket (versioned, private) with 6 key prefixes. Three DynamoDB tables: web scrape cache (with TTL), memories (with 3 GSIs for document/provider/prescription), and PA request tracking. |
| **Search** | OpenSearch Serverless VECTORSEARCH collection (`pa-bot-vectors`) with encryption, network, and data access policies. Houses `blank-forms` and `memories` indices. |
| **Messaging** | SES email identity for PA submission/response. SNS topic (`pa-bot-notifications`) with email subscription for real-time status alerts. |
| **Compute** | 10 Lambda functions (Python 3.12) with a shared utility layer. IAM policies for S3, DynamoDB, Bedrock, OpenSearch, SES, SNS, Transcribe, and Comprehend Medical. S3 event notifications for recording uploads. |
| **Pipeline** | Step Functions state machine with branching (approval/rejection paths), a Map state for parallel treatment processing, retry loops for self-improvement, and CloudWatch logging. |
| **Monitoring** | CloudWatch dashboard (`PABotDashboard`) with 4 widget rows: Step Functions executions, Lambda invocations, Lambda errors, and key function durations. Per-function error alarms and a Step Functions failure alarm. |

---

## Lambda Functions

| # | Function | Memory | Timeout | Description |
|---|---|---|---|---|
| 1 | `transcribe_handler` | 256 MB | 30 s | Starts Amazon Transcribe job on uploaded recordings, stores transcript in S3. Triggered by S3 events and can start the Step Functions pipeline. |
| 2 | `extract_entities_handler` | 512 MB | 60 s | Runs Comprehend Medical (InferRxNorm, InferSNOMEDCT, DetectEntitiesV2) on transcript to extract medications, diagnoses, procedures. |
| 3 | `pa_check_handler` | 512 MB | 120 s | Uses Bedrock LLM to determine which extracted treatments require PA. Scrapes provider websites with DynamoDB-cached results (TTL). |
| 4 | `form_selection_handler` | 512 MB | 60 s | Generates Titan embedding, vector searches OpenSearch `blank-forms` index, re-ranks candidates with LLM to select the best form. |
| 5 | `memory_search_handler` | 512 MB | 60 s | Queries all 4 memory tiers via OpenSearch vector search and DynamoDB GSIs. Merges and ranks memories by relevance and success rate. |
| 6 | `document_population_handler` | 1024 MB | 300 s | Extracts AcroForm fields from blank PDF, uses LLM to fill fields with patient/treatment/memory context, writes filled PDF to S3. |
| 7 | `document_courier_handler` | 256 MB | 60 s | Sends filled PDF via SES, updates tracking table status to SUBMITTED, publishes SNS notification. |
| 8 | `response_handler` | 512 MB | 120 s | Processes payer responses. On approval, saves learnings as memories across all applicable tiers. On rejection, prepares context for self-improvement. |
| 9 | `self_improvement_handler` | 1024 MB | 300 s | Analyzes rejections (with or without reasons), generates targeted fixes or ranked brainstormed improvements, feeds back into pipeline retry loop. |
| 10 | `embedding_handler` | 256 MB | 30 s | Utility function that generates Titan text embeddings. Used by seeding scripts and ad-hoc embedding needs. |

---

## Key Design Decisions

### Why Step Functions?
Step Functions provides **visual debugging** through the AWS console -- every execution renders as a flow diagram showing exactly which step succeeded, failed, or is in progress. This is invaluable for a complex 7-step pipeline. Built-in **retry and error handling** at the state level means transient failures (Bedrock throttling, Transcribe delays) are handled declaratively rather than with custom retry code. The Map state enables **parallel processing** of multiple treatments from a single appointment, and the Choice states enable clean branching between approval and rejection paths.

### Why OpenSearch Serverless?
OpenSearch Serverless with the VECTORSEARCH collection type provides **native k-NN vector search** without managing clusters, shards, or capacity planning. This is critical for two use cases: matching treatments to the correct PA form (semantic similarity, not keyword match) and retrieving relevant memories (fuzzy matching on clinical concepts). The serverless model means zero operational overhead and automatic scaling.

### Why a Shared Lambda Layer?
All 10 Lambda functions share common utilities: Pydantic models, Bedrock/OpenSearch/DynamoDB clients, PDF utilities, and configuration. A Lambda Layer implements **DRY principles** -- a single copy of shared code deployed once and mounted into every function. This eliminates code duplication, ensures consistency, and reduces deployment package sizes.

### Why Bedrock (Claude + Titan)?
**Claude** provides the reasoning capabilities needed for PA determination, form filling, rejection analysis, and brainstorming improvements. These tasks require understanding medical context, insurance requirements, and nuanced clinical language -- a strong LLM is non-negotiable. **Titan** provides fast, cost-effective text embeddings for vector search. Using both models through Bedrock means no self-managed inference infrastructure, no API key management, and native IAM integration.

### Why a 4-Tier Memory System?
A single flat memory store would either be too generic (useless advice) or too specific (no matches). The 4-tier system provides **graduated specificity**: global memories apply everywhere, document memories apply to specific forms, provider memories capture insurer quirks, and prescription memories store drug-specific requirements. During retrieval, all tiers are queried and merged, so the system always has relevant context regardless of how novel the current request is. Success/failure counters enable confidence-weighted ranking.

---

## Team

**Michael Lavery** -- Architecture, Infrastructure, Pipeline, and Implementation
