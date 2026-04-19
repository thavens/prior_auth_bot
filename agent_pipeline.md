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
