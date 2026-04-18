"""Step 4 -- Memory Search Handler.

Retrieves relevant memories from OpenSearch across four scopes (global,
document, provider, prescription), deduplicates, ranks by relevance and
success rate, and returns the top 10 to inform form population.
"""

from __future__ import annotations

import logging
from typing import Any

from shared.bedrock_client import BedrockClient
from shared.config import Config
from shared.models import FormMetadata, Patient, Treatment
from shared.opensearch_client import OpenSearchClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

cfg = Config()
bedrock = BedrockClient()
opensearch = OpenSearchClient()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Search memories across four scopes and return the top 10 matches.

    Event keys:
        treatment   -- serialized Treatment
        patient     -- serialized Patient
        selected_form -- serialized FormMetadata
    """

    treatment = Treatment(**event["treatment"])
    patient = Patient(**event["patient"])
    selected_form = FormMetadata(**event["selected_form"])

    # -----------------------------------------------------------------
    # Build a rich query string for embedding generation
    # -----------------------------------------------------------------
    query_text = (
        f"{treatment.name} {selected_form.title} {patient.insurance_provider}"
    )
    logger.info("Generating embedding for query: %s", query_text)
    query_embedding = bedrock.generate_embedding(query_text)

    # -----------------------------------------------------------------
    # Search four memory scopes in sequence
    # -----------------------------------------------------------------
    prescription_code = treatment.rxnorm_code or treatment.name

    global_results = opensearch.search_memories(
        query_embedding=query_embedding,
        memory_type="GLOBAL",
        top_k=10,
    )

    document_results = opensearch.search_memories(
        query_embedding=query_embedding,
        document_id=selected_form.form_id,
        top_k=10,
    )

    provider_results = opensearch.search_memories(
        query_embedding=query_embedding,
        provider_id=patient.insurance_provider,
        top_k=10,
    )

    prescription_results = opensearch.search_memories(
        query_embedding=query_embedding,
        prescription_code=prescription_code,
        top_k=10,
    )

    # -----------------------------------------------------------------
    # Merge and deduplicate by memory_id
    # -----------------------------------------------------------------
    all_results = (
        global_results + document_results + provider_results + prescription_results
    )

    seen: set[str] = set()
    unique_memories: list[dict[str, Any]] = []
    for memory in all_results:
        mid = memory.get("memory_id", "")
        if mid and mid not in seen:
            seen.add(mid)
            unique_memories.append(memory)

    # -----------------------------------------------------------------
    # Sort by relevance_score * success_rate (descending)
    # -----------------------------------------------------------------
    def _sort_key(m: dict[str, Any]) -> float:
        relevance = float(m.get("_score", 0.0))
        success_rate = float(m.get("success_rate", 1.0))
        return relevance * success_rate

    unique_memories.sort(key=_sort_key, reverse=True)
    top_memories = unique_memories[:10]

    logger.info(
        "Memory search complete: %d unique memories found, returning top %d",
        len(unique_memories),
        len(top_memories),
    )

    return {
        "treatment": treatment.model_dump(),
        "patient": patient.model_dump(),
        "selected_form": selected_form.model_dump(),
        "memories": top_memories,
    }
