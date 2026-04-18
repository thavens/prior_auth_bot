"""Step 7b -- Self Improvement Handler.

Invoked when a PA request is rejected. Analyzes the rejection (or
brainstorms improvements when no reasons are given), decides whether to
retry, and returns context for the next submission attempt.
"""

from __future__ import annotations

import logging
from typing import Any

from shared.bedrock_client import BedrockClient
from shared.config import Config
from shared.dynamo_client import DynamoClient
from shared.models import PARequest, Patient, Treatment

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

cfg = Config()
bedrock = BedrockClient()
dynamo = DynamoClient()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Determine whether to retry a rejected PA and prepare improvements.

    Event keys:
        pa_request_id     -- tracking ID of the rejected request
        rejection_reasons -- (optional) string describing why it was rejected
        attempt_number    -- current attempt number (1-based)
        treatment         -- serialized Treatment
        patient           -- serialized Patient
        selected_form     -- serialized FormMetadata
    """

    pa_request_id: str = event["pa_request_id"]
    rejection_reasons: str | None = event.get("rejection_reasons")
    attempt_number: int = event.get("attempt_number", 1)
    treatment = Treatment(**event["treatment"])
    patient = Patient(**event["patient"])
    selected_form_data: dict[str, Any] = event["selected_form"]

    max_attempts = cfg.MAX_SELF_IMPROVEMENT_ATTEMPTS

    # -----------------------------------------------------------------
    # Check if we have exhausted retry attempts
    # -----------------------------------------------------------------
    if attempt_number >= max_attempts:
        logger.info(
            "PA %s: attempt %d >= max %d, no more retries",
            pa_request_id,
            attempt_number,
            max_attempts,
        )
        return {
            "should_retry": False,
            "reason": "exhausted",
            "pa_request_id": pa_request_id,
            "attempt_number": attempt_number,
        }

    # -----------------------------------------------------------------
    # Reconstruct the PARequest from tracking data
    # -----------------------------------------------------------------
    tracking_item = dynamo.get_tracking(cfg.TRACKING_TABLE, pa_request_id)
    if tracking_item is None:
        logger.error("Tracking record not found for %s", pa_request_id)
        return {
            "should_retry": False,
            "reason": "tracking_record_not_found",
            "pa_request_id": pa_request_id,
            "attempt_number": attempt_number,
        }

    pa_request = PARequest(**tracking_item)

    # -----------------------------------------------------------------
    # Path A: explicit rejection reasons provided
    # -----------------------------------------------------------------
    if rejection_reasons:
        logger.info(
            "PA %s: analyzing rejection reasons for attempt %d",
            pa_request_id,
            attempt_number,
        )

        analysis = bedrock.analyze_rejection(
            rejection_reasons=rejection_reasons,
            pa_request=pa_request,
            patient=patient,
        )

        enhanced_context: list[str] = analysis.get("enhanced_context", [])
        fixes: list[str] = analysis.get("fixes", [])

        logger.info(
            "Rejection analysis produced %d fixes and %d context items",
            len(fixes),
            len(enhanced_context),
        )

        return {
            "should_retry": True,
            "improvement_context": enhanced_context,
            "attempt_number": attempt_number + 1,
            "treatment": treatment.model_dump(),
            "patient": patient.model_dump(),
            "selected_form": selected_form_data,
            "pa_request_id": pa_request_id,
        }

    # -----------------------------------------------------------------
    # Path B: no explicit reasons -- brainstorm improvements
    # -----------------------------------------------------------------
    logger.info(
        "PA %s: no rejection reasons, brainstorming improvements for attempt %d",
        pa_request_id,
        attempt_number,
    )

    previous_attempts = pa_request.improvement_context
    improvements = bedrock.brainstorm_improvements(
        pa_request=pa_request,
        patient=patient,
        previous_attempts=[{"context": ctx} for ctx in previous_attempts],
    )

    # Improvements are sorted by priority (1 = highest). Pick the top
    # one that was not already tried in a previous attempt.
    tried_descriptions: set[str] = set(previous_attempts)
    selected_improvement: str | None = None

    for improvement in sorted(improvements, key=lambda i: i.get("priority", 999)):
        desc: str = improvement.get("description", "")
        if desc and desc not in tried_descriptions:
            selected_improvement = desc
            break

    # If all brainstormed ideas were already tried, use the top one anyway
    # as a last resort with potentially different framing.
    if selected_improvement is None and improvements:
        selected_improvement = improvements[0].get("description", "")

    if not selected_improvement:
        logger.warning("PA %s: brainstorming produced no usable improvements", pa_request_id)
        return {
            "should_retry": False,
            "reason": "no_improvements_available",
            "pa_request_id": pa_request_id,
            "attempt_number": attempt_number,
        }

    logger.info("Selected improvement: %s", selected_improvement)

    return {
        "should_retry": True,
        "improvement_context": [selected_improvement],
        "attempt_number": attempt_number + 1,
        "treatment": treatment.model_dump(),
        "patient": patient.model_dump(),
        "selected_form": selected_form_data,
        "pa_request_id": pa_request_id,
    }
