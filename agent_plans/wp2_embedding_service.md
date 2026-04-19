# WP2: Embedding Service

**Depends on:** WP1 (models.py must have `embedding` field on Memory)

## New File: `src/prior_auth_bot/services/embedding_service.py`

```python
class EmbeddingService:
    """Wraps AWS Bedrock Titan Text Embeddings v2 for generating and comparing embeddings."""

    def __init__(self, bedrock_client, model_id: str = "amazon.titan-embed-text-v2:0"):
        self.bedrock = bedrock_client
        self.model_id = model_id

    def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text using Bedrock Titan."""
        # Call bedrock_client.invoke_model(modelId=self.model_id, body=json.dumps({"inputText": text[:8000)}))
        # Parse response body JSON, return response["embedding"]
        # Titan v2 returns 1024-dim vectors by default
        # Truncate input to 8000 chars (Titan limit is ~8192 tokens)

    def cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Pure Python cosine similarity. No numpy dependency."""
        # dot = sum(x*y for x,y in zip(a,b))
        # norm_a = sum(x*x for x in a) ** 0.5
        # norm_b = sum(x*x for x in b) ** 0.5
        # return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0

    def semantic_search(self, query_embedding: list[float], candidates: list[tuple[str, list[float]]], top_k: int = 10) -> list[tuple[str, float]]:
        """Rank candidates by cosine similarity to query embedding."""
        # Compute similarity for each candidate
        # Sort by score descending
        # Return top_k (memory_id, score) tuples
```

## Modified File: `src/prior_auth_bot/services/memory_feature.py`

**Modify `save_memory()`:**
- The existing method serializes a Memory to a DynamoDB item
- If `memory.embedding` is non-empty, include it in the item dict
- DynamoDB stores `list[float]` natively as List of Number type
- Also store the new `memory_subtype` field

**Add `scan_all_with_embeddings()` method:**
```python
def scan_all_with_embeddings(self) -> list[Memory]:
    """Return all memories that have stored embeddings."""
    response = self.table.scan(
        FilterExpression=Attr("embedding").exists()
    )
    items = response.get("Items", [])
    # Handle pagination if needed
    while "LastEvaluatedKey" in response:
        response = self.table.scan(
            FilterExpression=Attr("embedding").exists(),
            ExclusiveStartKey=response["LastEvaluatedKey"]
        )
        items.extend(response.get("Items", []))
    return [self._item_to_memory(item) for item in items]
```

**Add `increment_success_count()` method:**
```python
def increment_success_count(self, memory_type: str, memory_id: str) -> None:
    """Increment success_count and update timestamp."""
    self.table.update_item(
        Key={"memory_type": memory_type, "memory_id": memory_id},
        UpdateExpression="SET success_count = success_count + :inc, updated_at = :ts",
        ExpressionAttributeValues={":inc": 1, ":ts": datetime.now(timezone.utc).isoformat()},
    )
```

## Verify
```bash
uv run python -c "
from prior_auth_bot.services.embedding_service import EmbeddingService
print('EmbeddingService imported OK')
"
```

## What NOT to touch
- Do not modify search_service.py (that's WP3)
- Do not modify orchestrator.py or steps.py (that's WP3)
- Do not modify self_improvement.py (that's WP6)
