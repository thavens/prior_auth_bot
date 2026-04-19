# WP1: Models and Configuration (Foundation)

All other WPs depend on this completing first.

## Files to Modify

### 1. `src/prior_auth_bot/models.py`

**Add `pending_insurer_review` to PAStatus:**
- Find the `PAStatus = Literal[...]` type and add `"pending_insurer_review"` to the union

**Extend Memory model:**
- Add `embedding: list[float] = []` field
- Add `memory_subtype: str = ""` field (values: "first_approval", "appeal_success", "anti_pattern")

**Add InsurerDecision model:**
```python
class InsurerDecision(BaseModel):
    pa_request_id: str
    decision: Literal["approved", "rejected"]
    rejection_reasons: list[str] = []
    feedback: str = ""
    decided_by: str = "insurer"
    decided_at: str = ""
```

**Add EarlyMemoryContext model:**
```python
class EarlyMemoryContext(BaseModel):
    provider_memories: list[Memory] = []
    treatment_memories: list[Memory] = []
    summary: str = ""
```

### 2. `src/prior_auth_bot/config.py`

**Add embedding model config:**
```python
bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"
```

### 3. `frontend/src/types/index.ts`

**Add TypeScript interfaces:**
```typescript
export interface InsurerDecision {
  pa_request_id: string;
  decision: 'approved' | 'rejected';
  rejection_reasons: string[];
  feedback: string;
}

export interface InsurerQueueItem {
  pa_request_id: string;
  status: string;
  patient_name: string;
  physician_name: string;
  insurance_provider: string;
  treatment_text: string;
  created_at: string;
  attempt_number: number;
}
```

## Verify
```bash
uv run python -c "from prior_auth_bot.models import PAStatus, Memory, InsurerDecision, EarlyMemoryContext; print('OK')"
cd frontend && npx tsc --noEmit
```

## What NOT to touch
- Do not modify any service files, pipeline files, or API routes
- Do not remove any existing fields or models
- Only ADD new fields/models and extend existing ones
