# WP6: Enhanced Self-Improvement with RAG

**Depends on:** WP2 (embedding_service), WP3 (search_service semantic search)

## Modified File: `src/prior_auth_bot/services/self_improvement.py`

### Constructor changes
- Remove `sqs_client` and `queue_url` parameters (SQS no longer used)
- Add `search_service: SearchService` parameter
- Add `embedding_service: EmbeddingService` parameter
- Store both as instance attributes

### Remove SQS-related methods
- Remove any `poll_rejections` or SQS-reading methods if they exist

### Modify `handle_rejection(rejection, pa_request)`

Before building the LLM prompt, do semantic search for similar past rejections:
```python
treatment_text = ""
treatments = pa_request.treatments_requiring_pa or []
if treatments:
    treatment_text = treatments[0].get("treatment_text", "") if isinstance(treatments[0], dict) else ""
provider = pa_request.patient.insurance_provider if pa_request.patient else ""

query = f"rejection {provider} {treatment_text} {' '.join(rejection.rejection_reasons)}"
similar_memories = self.search_service.search_memories_semantic(query, limit=5)
```

Inject into the LLM prompt:
```python
if similar_memories.memories:
    similar_context = "\nSIMILAR PAST CASES:\n"
    for m in similar_memories.memories:
        if "exhausted" in (m.outcome or "") or "rejected" in (m.outcome or ""):
            similar_context += f"- ANTI-PATTERN (failed): {m.advice}\n"
        else:
            similar_context += f"- PROVEN FIX (success_count: {m.success_count}): {m.advice}\n"
    # Append to the prompt before asking for proposed fixes
```

### Modify `save_successful_appeal(pa_request, provider, treatment)`

After building the advice string, generate embedding and save:
```python
advice = ...  # existing advice construction
embedding = self.embedding_service.embed(advice) if self.embedding_service else []
memory = Memory(
    ...,
    embedding=embedding,  # NEW
    memory_subtype="appeal_success",  # NEW
)
self.memory_service.save_memory(memory)
```

### New method: `save_first_approval_memory(record, provider, treatment)`

Called by OutcomeHandler when attempt_number == 1:
```python
def save_first_approval_memory(self, record: dict, provider: str, treatment: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    advice = f"Approved on first attempt for {treatment} with {provider}."
    # If we have access to what fields were filled, include key info
    selected_forms = record.get("selected_forms", [])
    if selected_forms:
        form_name = selected_forms[0].get("form_name", "")
        advice += f" Form: {form_name}."

    embedding = self.embedding_service.embed(advice) if self.embedding_service else []

    memory = Memory(
        memory_id=f"mem_{uuid.uuid4().hex[:8]}",
        memory_type="treatment_provider",
        memory_subtype="first_approval",
        provider=provider,
        treatment=treatment,
        advice=advice,
        source_pa_request_id=record.get("pa_request_id", ""),
        outcome="approved_first_attempt",
        attempt_count=1,
        success_count=1,
        tags=["first_approval", "successful"],
        created_at=now,
        updated_at=now,
        embedding=embedding,
    )
    self.memory_service.save_memory(memory)
```

### New method: `save_exhausted_rejection_memory(record, provider, treatment)`

Called by OutcomeHandler when all appeal attempts exhausted:
```python
def save_exhausted_rejection_memory(self, record: dict, provider: str, treatment: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    advice_parts = [f"ANTI-PATTERN: Failed after {record.get('attempt_number', 3)} attempts for {treatment} with {provider}."]
    for entry in record.get("rejection_history", []):
        reasons = entry.get("rejection_reasons", [])
        fixes = entry.get("proposed_fixes", [])
        if reasons:
            advice_parts.append(f"Rejected for: {'; '.join(reasons)}")
        if fixes:
            advice_parts.append(f"Tried fix: {'; '.join(fixes)}")
    advice = " | ".join(advice_parts)

    embedding = self.embedding_service.embed(advice) if self.embedding_service else []

    memory = Memory(
        memory_id=f"mem_{uuid.uuid4().hex[:8]}",
        memory_type="treatment_provider",
        memory_subtype="anti_pattern",
        provider=provider,
        treatment=treatment,
        advice=advice,
        source_pa_request_id=record.get("pa_request_id", ""),
        outcome="rejected_exhausted",
        attempt_count=record.get("attempt_number", 3),
        success_count=0,
        tags=["anti_pattern", "exhausted"],
        created_at=now,
        updated_at=now,
        embedding=embedding,
    )
    self.memory_service.save_memory(memory)
```

## Verify
- Reject a PA via insurer portal, check that self-improvement prompt includes RAG context from similar past cases
- Approve after appeal, verify memory saved with embedding (check pa_memories in DynamoDB)
- Reject 3 times (exhaust appeals), verify anti-pattern memory saved
- Run same provider/treatment again, verify these memories are found by search_memories

## What NOT to touch
- Do not modify search_service.py (already done in WP3)
- Do not modify embedding_service.py (already done in WP2)
- Do not modify frontend files (that's WP5)
- Do not modify outcome_handler.py (that's WP4) - this WP only modifies self_improvement.py
