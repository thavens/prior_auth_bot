# prior_auth_bot

Automates physician prior authorization submissions — from appointment recording to form submission and appeals.

## System Architecture

```mermaid
flowchart TB
    subgraph Dashboards["Dashboards"]
        PD["Physician Dashboard\nUpload Audio | Search PAs | View PA"]
        PLD["Pipeline Dashboard\n7-Stage Visualizer | AWS Health | PA Search"]
    end

    subgraph Gateway["FastAPI Gateway"]
        API["REST API + WebSocket\nPOST /pa-requests\nGET /pa-requests/:id\nWS /ws/pa-status"]
    end

    subgraph Pipeline["Agent Pipeline — Orchestrator"]
        S1["Step 1\nEntity Extraction"]
        S2["Step 2\nPA Requirement\nDetermination"]
        S3["Step 3\nForm Selection"]
        S4["Step 4\nMemory Retrieval"]
        S5["Step 5\nDocument Population"]
        S6["Step 6\nDocument Submission"]
        S7["Step 7\nOutcome Handling"]

        S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7
    end

    subgraph Services["Service Modules"]
        STT["Speech to Text"]
        SS["Search Service"]
        MF["Memory Feature"]
        DD["Document Download"]
        DP["Document Population"]
        DC["Document Courier"]
        SI["Self Improvement"]
    end

    subgraph AWS["AWS Services"]
        S3_audio["S3: pa-audio-uploads"]
        S3_blank["S3: pa-blank-forms"]
        S3_textract["S3: pa-textract-output"]
        S3_completed["S3: pa-completed-forms"]
        Transcribe["AWS Transcribe"]
        Comprehend["Comprehend Medical\nInferRxNorm | InferSNOMEDCT\nDetectEntitiesV2"]
        Textract["AWS Textract"]
        SES["Amazon SES"]
        DDB_requests["DynamoDB: pa_requests"]
        DDB_memories["DynamoDB: pa_memories"]
        DDB_cache["DynamoDB: pa_scrape_cache"]
        SQS["SQS: pa-ses-responses"]
        CW["CloudWatch\nMetrics + Alarms"]
        Streams["DynamoDB Streams"]
    end

    %% Dashboard connections
    PD -- "Upload audio\nSearch/View PAs" --> API
    PLD -- "Pipeline status" --> API
    PLD -- "AWS health" --> CW
    API -- "Real-time updates" --> Streams

    %% Pipeline trigger
    API -- "Start pipeline" --> STT
    STT -- "Transcript" --> S1

    %% AWS service connections
    STT -- "Audio" --> Transcribe
    STT -- "Read/Write" --> S3_audio
    S1 -- "Entities" --> Comprehend
    S2 -- "Check PA rules" --> SS
    SS -- "Cache lookups" --> DDB_cache
    S3 -- "Find forms" --> SS
    S3 -- "Get blank forms" --> DD
    DD -- "Read/Write" --> S3_blank
    DD -- "Run OCR" --> Textract
    DD -- "Store results" --> S3_textract
    S4 -- "Search memories" --> SS
    SS -- "Query memories" --> MF
    MF -- "Read/Write" --> DDB_memories
    S5 -- "Fill form" --> DP
    DP -- "Read blanks" --> S3_blank
    DP -- "Read textract" --> S3_textract
    DP -- "Write completed" --> S3_completed
    S6 -- "Send form" --> DC
    DC -- "Email" --> SES
    DC -- "Read form" --> S3_completed
    S7 -- "Approved" --> MF
    SES -- "Responses" --> SQS
    SQS -- "Rejection" --> SI
    SI -- "Re-enter pipeline" --> S3

    %% Pipeline state tracking
    S1 & S2 & S3 & S4 & S5 & S6 & S7 -- "Update status" --> DDB_requests
    DDB_requests -- "Change events" --> Streams
```

## Communication Strategy

| Boundary | Mechanism | Why |
|---|---|---|
| Between pipeline steps (1-7) | Direct Python function calls | Pipeline is sequential — no network overhead needed |
| Physician Dashboard -> Backend | REST API (FastAPI) | Standard HTTP for uploads and queries |
| Pipeline status -> Dashboards | WebSocket via DynamoDB Streams | Real-time updates without polling |
| SES rejection responses -> Self Improvement | SQS queue | Only truly async boundary — insurer replies arrive hours/days later |
| All services -> Pipeline state | DynamoDB `pa_requests` table | Each step writes status before proceeding; dashboards read it |

## AWS Resource Ownership

| AWS Resource | Owner Spec | Readers |
|---|---|---|
| S3: `pa-audio-uploads` | speech_to_text | agent_pipeline |
| S3: `pa-blank-forms` | document_download | document_population, search_service |
| S3: `pa-textract-output` | document_download | document_population |
| S3: `pa-completed-forms` | document_population | document_courier, dashboards |
| AWS Transcribe | speech_to_text | — |
| AWS Comprehend Medical | agent_pipeline (Step 1) | — |
| AWS Textract | document_download | — |
| Amazon SES | document_courier | — |
| SQS: `pa-ses-responses` | document_courier | self_improvement |
| DynamoDB: `pa_requests` | agent_pipeline | all dashboards, all services |
| DynamoDB: `pa_memories` | memory_feature | search_service |
| DynamoDB: `pa_scrape_cache` | search_service | — |
| CloudWatch Metrics/Alarms | pipeline_dashboard | — |
| DynamoDB Streams | agent_pipeline | pipeline_dashboard |

## Specs

| Spec | Description |
|---|---|
| [Architecture](architecture.md) | System overview and design decisions |
| [Agent Pipeline](agent_pipeline.md) | 7-step orchestration pipeline |
| [Speech to Text](speech_to_text.md) | Audio transcription via AWS Transcribe |
| [Search Service](search_service.md) | Form and memory search with caching |
| [Memory Feature](memory_feature.md) | Learning storage in DynamoDB |
| [Document Download](document_download.md) | Blank form retrieval and Textract processing |
| [Document Population](document_population.md) | LLM-powered form filling |
| [Document Courier](document_courier.md) | Form submission via SES/fax |
| [Self Improvement](self_improvement.md) | Rejection handling and appeals |
| [Pipeline Dashboard](pipeline_dashboard.md) | Ops monitoring dashboard |
| [Physician Dashboard](physician_dashboard.md) | Doctor-facing interface |