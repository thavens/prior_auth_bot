from __future__ import annotations

import json
import logging
import math

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self, bedrock_client, model_id: str = "amazon.titan-embed-text-v2:0"):
        self.bedrock = bedrock_client
        self.model_id = model_id

    def embed(self, text: str) -> list[float]:
        truncated = text[:8000]
        try:
            response = self.bedrock.invoke_model(
                modelId=self.model_id,
                body=json.dumps({"inputText": truncated}),
            )
            body = json.loads(response["body"].read())
            return body["embedding"]
        except Exception:
            logger.exception("Embedding generation failed")
            return []

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot / (norm_a * norm_b)

    def semantic_search(
        self,
        query_embedding: list[float],
        candidates: list[tuple[str, list[float]]],
        top_k: int = 10,
    ) -> list[tuple[str, float]]:
        scored = []
        for memory_id, emb in candidates:
            score = self.cosine_similarity(query_embedding, emb)
            scored.append((memory_id, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
