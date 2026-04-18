"""Step 7a -- Response Handler.

Operates in two modes:
  1. Normal mode  -- processes an insurance provider's PA response
                     (APPROVED / REJECTED), updates tracking, and sends
                     an SNS notification.
  2. Save mode    -- extracts reusable learnings from an approved PA,
                     generates embeddings, persists memories in DynamoDB
                     and indexes them in OpenSearch.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import boto3

from shared.bedrock_client import BedrockClient
from shared.config import Config
from shared.dynamo_client import DynamoClient
from shared.models import Memory, MemoryType, PARequest
from shared.opensearch_client import OpenSearchClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

cfg = Config()
bedrock = BedrockClient()
dynamo = DynamoClient()
opensearch = OpenSearchClient()


def _handle_normal(event: dict[str, Any]) -> dict[str, Any]:
    """Process an insurance provider's PA decision."""

    pa_request_id: str = event["pa_request_id"]
    response_data: dict[str, Any] = event["response"]

    outcome: str = response_data.get("outcome", "UNKNOWN")
    rejection_reasons: str | None = response_data.get("rejection_reasons")

    # -----------------------------------------------------------------
    # Update tracking record
    # -----------------------------------------------------------------
    extra_attrs: dict[str, Any] = {"response_at": int(time.time())}
    if rejection_reasons:
        extra_attrs["rejection_reasons"] = rejection_reasons

    dynamo.update_tracking_status(
        cfg.TRACKING_TABLE,
        pa_request_id,
        status=outcome,
        **extra_attrs,
    )
    logger.info("Tracking record %s updated to %s", pa_request_id, outcome)

    # -----------------------------------------------------------------
    # Publish SNS notification
    # -----------------------------------------------------------------
    if cfg.SNS_TOPIC_ARN:
        sns = boto3.client("sns", region_name=cfg.AWS_REGION)
        sns.publish(
            TopicArn=cfg.SNS_TOPIC_ARN,
            Subject=f"PA {outcome}: Request {pa_request_id}",
            Message=json.dumps(
                {
                    "event": f"PA_{outcome}",
                    "pa_request_id": pa_request_id,
                    "outcome": outcome,
                    "rejection_reasons": rejection_reasons,
                },
                default=str,
            ),
        )
        logger.info("SNS notification published for %s", outcome)

    result: dict[str, Any] = {
        "pa_request_id": pa_request_id,
        "outcome": outcome,
    }
    if rejection_reasons:
        result["rejection_reasons"] = rejection_reasons

    return result


def _handle_save(event: dict[str, Any]) -> dict[str, Any]:
    """Extract and persist learnings from a successful PA submission."""

    pa_request_id: str = event["pa_request_id"]

    # -----------------------------------------------------------------
    # Reconstruct the PARequest from tracking data
    # -----------------------------------------------------------------
    tracking_item = dynamo.get_tracking(cfg.TRACKING_TABLE, pa_request_id)
    if tracking_item is None:
        raise ValueError(f"Tracking record not found for {pa_request_id}")

    pa_request = PARequest(**tracking_item)
    outcome = tracking_item.get("status", "APPROVED")

    # -----------------------------------------------------------------
    # Extract learnings via LLM
    # -----------------------------------------------------------------
    learnings = bedrock.extract_learnings(pa_request, outcome)
    logger.info("Extracted %d learnings from PA %s", len(learnings), pa_request_id)

    # -----------------------------------------------------------------
    # Persist each learning as a Memory
    # -----------------------------------------------------------------
    memories_saved = 0
    for learning in learnings:
        memory_id = str(uuid.uuid4())
        content: str = learning["content"]
        memory_type_str: str = learning["memory_type"]
        memory_type = MemoryType(memory_type_str)

        # Generate embedding for the learning content
        embedding = bedrock.generate_embedding(content)

        now = time.time()
        memory = Memory(
            memory_id=memory_id,
            memory_type=memory_type,
            content=content,
            document_id=pa_request.form_id if memory_type == MemoryType.DOCUMENT else None,
            provider_id=pa_request.provider_id if memory_type == MemoryType.PROVIDER else None,
            prescription_code=(
                pa_request.treatment.rxnorm_code or pa_request.treatment.name
                if memory_type == MemoryType.PRESCRIPTION
                else None
            ),
            success_count=1,
            failure_count=0,
            created_at=now,
            updated_at=now,
        )

        # Save to DynamoDB
        dynamo.put_memory(cfg.MEMORIES_TABLE, memory)

        # Index in OpenSearch
        opensearch.index_memory(
            memory_id=memory_id,
            content=content,
            memory_type=memory_type_str,
            embedding=embedding,
            document_id=memory.document_id,
            provider_id=memory.provider_id,
            prescription_code=memory.prescription_code,
            success_rate=1.0,
        )

        memories_saved += 1
        logger.info("Saved memory %s (type=%s)", memory_id, memory_type_str)

    return {
        "pa_request_id": pa_request_id,
        "outcome": outcome,
        "memories_saved": memories_saved,
    }


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Route to normal or save mode based on the event payload.

    Normal mode event:
        { pa_request_id, response: { outcome, rejection_reasons? } }

    Save mode event:
        { pa_request_id, save_mode: true }
    """

    if event.get("save_mode"):
        logger.info("Running in save mode for %s", event.get("pa_request_id"))
        return _handle_save(event)

    logger.info("Running in normal mode for %s", event.get("pa_request_id"))
    return _handle_normal(event)
