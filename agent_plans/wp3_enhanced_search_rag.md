# WP3: Enhanced Search and Memory Injection (RAG Core)

**Depends on:** WP2 (embedding_service.py and memory_feature.py enhancements must exist)

## Modified Files

### 1. `src/prior_auth_bot/services/search_service.py`

**Modify constructor:**
- Add `embedding_service: EmbeddingService = None` parameter
- Store as `self.embedding_service`

**Modify `search_memories()`:**
- Keep existing 3-tier DynamoDB lookup as baseline
- If `self.embedding_service` is not None:
  - Build query context string: `f"{provider} {treatment}"`
  - Generate query embedding: `self.embedding_service.embed(query_context)`
  - Get all memories with embeddings: `self.memory_service.scan_all_with_embeddings()`
  - Compute cosine similarity between query and each candidate
  - For candidates that also matched in the key-based lookup, combine scores:
    `final_score = 0.4 * key_match_score + 0.6 * cosine_similarity`
  - For candidates only found via embedding (not in key lookup), use just cosine similarity * 0.6
  - Sort by final_score descending, return top `limit`
- If no embedding_service, use old behavior (backward compatible)

**Add `search_memories_semantic()` method:**
```python
def search_memories_semantic(self, query: str, limit: int = 10) -> MemoryRetrievalResult:
    """Pure semantic search. Used by self-improvement for finding similar rejections."""
    if not self.embedding_service:
        return MemoryRetrievalResult(memories=[])
    query_embedding = self.embedding_service.embed(query)
    all_memories = self.memory_service.scan_all_with_embeddings()
    candidates = [(m.memory_id, m.embedding) for m in all_memories if m.embedding]
    ranked = self.embedding_service.semantic_search(query_embedding, candidates, top_k=limit)
    # Map ranked IDs back to Memory objects, set relevance_score
    memory_map = {m.memory_id: m for m in all_memories}
    results = []
    for memory_id, score in ranked:
        if memory_id in memory_map:
            m = memory_map[memory_id]
            m.relevance_score = score
            results.append(m)
    return MemoryRetrievalResult(memories=results)
```

### 2. `src/prior_auth_bot/pipeline/orchestrator.py`

**Modify constructor:**
- Add `embedding_service` parameter, store as `self.embedding`

**Modify `run_pipeline()`:**
After transcript is available (after speech-to-text, before Step 1), add early memory retrieval:
```python
# Early memory retrieval for steps 1 and 2
early_memories = self._early_memory_retrieval(patient.insurance_provider, transcript.transcript_text)
```

Pass to step_1 and step_2:
```python
entities = steps.step_1_entity_extraction(
    ...,
    memory_context=early_memories,  # NEW
)
# ...
pa_result = steps.step_2_pa_determination(
    ...,
    memory_context=early_memories,  # NEW
)
```

**Add `_early_memory_retrieval()` method:**
```python
def _early_memory_retrieval(self, insurance_provider: str, transcript_text: str) -> EarlyMemoryContext:
    provider_memories = self.search.search_memories(insurance_provider, "", limit=5).memories
    query = f"{insurance_provider} {transcript_text[:500]}"
    treatment_memories = self.search.search_memories_semantic(query, limit=5).memories if hasattr(self.search, 'search_memories_semantic') else []
    summary = ""
    if provider_memories or treatment_memories:
        all_advice = [m.advice for m in (provider_memories + treatment_memories)[:5]]
        summary = "; ".join(all_advice)
    return EarlyMemoryContext(provider_memories=provider_memories, treatment_memories=treatment_memories, summary=summary)
```

**Modify `reenter_pipeline()`:**
- Same early memory injection for re-entry path
- Use rejection_history + treatment info to construct richer query

**Modify Step 6 status update:**
- Change from `step_7_outcome_handling` to `pending_insurer_review` after submission

### 3. `src/prior_auth_bot/pipeline/steps.py`

**Modify `step_1_entity_extraction()`:**
- Add `memory_context: EarlyMemoryContext | None = None` parameter
- If memory_context provided, inject into prompt between form context and transcript:
```
INSIGHTS FROM PAST APPLICATIONS WITH THIS PROVIDER:
- [m.advice] (success_count: X, outcome: Y, tags: Z)
Use these insights to focus extraction on data points important for this provider.
```

**Modify `step_2_pa_determination()`:**
- Add `memory_context: EarlyMemoryContext | None = None` parameter
- If provided, inject into prompt:
```
HISTORICAL PATTERNS FOR THIS PROVIDER:
- [m.advice] (success_count: X, outcome: Y)
Use these patterns to inform your PA determination.
```

### 4. `src/prior_auth_bot/services/document_population.py`

**Modify `_build_prompt()` (around lines 119-121):**
Replace simple advice concatenation with rich metadata:
```python
if input_data.memories:
    advice_lines = []
    for m in input_data.memories:
        prefix = "AVOID: " if "rejected" in (m.outcome or "") or "exhausted" in (m.outcome or "") else ""
        metadata = f"(outcome: {m.outcome}, success_count: {m.success_count}, tags: {m.tags})"
        advice_lines.append(f"- {prefix}{m.advice} {metadata}")
    parts.append("\nADVICE FROM PAST APPLICATIONS:\n" + "\n".join(advice_lines))
```

## Verify
- Run a pipeline end-to-end
- Check logs for early memory retrieval before Step 1
- Check that Steps 1 and 2 prompts include memory context
- Check that Step 5 prompt includes rich metadata (not just advice text)

## What NOT to touch
- Do not modify insurer_routes.py, portal_courier.py, outcome_handler.py (that's WP4)
- Do not modify self_improvement.py (that's WP6)
- Do not modify frontend files (that's WP5)
