# Motivation
We want a system that is not only able to produce applications for prior authrization, but also be able to make appeals that have increasing likelyhood of successfully applying.

# Requirement
This feature will implement search and return the relevant learnings and inject this into the context of an LLM that is tasked with completing the prior authorization forms. The LLM recieves advice at all stages of the pipeline.
This feature is responsible for storing the memories to achieve this task.
Memories will be stored in a amazon database service.

## database structure
1. Must store a general knowedge.
2. Knowledge by provider.
3. Knowledge by treatment.
4. Knowledge by treatment, and provider.

## AWS Ownership

This spec owns:
- **DynamoDB: `pa_memories`** — Stores all learnings with 4 GSIs matching the access patterns above.

This spec is read by:
- [Search Service](search_service.md) — For memory search queries in Agent Pipeline Step 4.

## DynamoDB Table Design (`pa_memories`)

**Key design:**
- PK: `memory_type` (one of: `general`, `provider`, `treatment`, `treatment_provider`)
- SK: `memory_id`
- GSI-1: PK `provider` + SK `created_at` — "all memories for medi-cal"
- GSI-2: PK `treatment` + SK `created_at` — "all memories for adalimumab"
- GSI-3: PK `provider#treatment` (composite) + SK `success_count` — "memories for adalimumab + medi-cal, ranked by success"

## Memory Schema

```json
{
  "memory_id": "mem_new789",
  "memory_type": "treatment_provider",
  "provider": "medi-cal",
  "treatment": "adalimumab",
  "advice": "Include explicit start/end dates for all prior DMARD trials. Medi-Cal rejected a Humira PA when dates were described vaguely.",
  "source_pa_request_id": "pr_a1b2c3d4",
  "outcome": "approved_on_appeal",
  "attempt_count": 2,
  "success_count": 1,
  "tags": ["step_therapy", "documentation"],
  "created_at": "2026-04-22T08:05:00Z",
  "updated_at": "2026-04-22T08:05:00Z"
}
```

## Memory Retrieval Output (consumed by Agent Pipeline Step 5)

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