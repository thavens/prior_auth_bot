from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from prior_auth_bot.models import (
    InsurerDecision,
    PARequest,
    RejectionMessage,
)

logger = logging.getLogger(__name__)


class OutcomeHandler:
    """Handles PA approval/rejection decisions from the insurer portal."""

    MAX_APPEAL_ATTEMPTS = 3

    def __init__(
        self,
        pa_table,
        memory_service,
        self_improvement_service,
        embedding_service,
        search_service,
        orchestrator,
        bedrock_client,
    ):
        self.table = pa_table
        self.memory_service = memory_service
        self.self_improvement = self_improvement_service
        self.embedding_service = embedding_service
        self.search_service = search_service
        self.orchestrator = orchestrator
        self.bedrock = bedrock_client

    async def handle_decision(self, decision: InsurerDecision):
        pa_request_id = decision.pa_request_id
        response = self.table.get_item(Key={"pa_request_id": pa_request_id})
        record = response.get("Item")
        if not record:
            logger.warning(f"PA request {pa_request_id} not found")
            return

        if decision.decision == "approved":
            self.handle_approval(pa_request_id, record, decision)
        elif decision.decision == "rejected":
            self.handle_rejection(pa_request_id, record, decision)

    def handle_approval(self, pa_request_id: str, record: dict, decision: InsurerDecision):
        logger.info(f"PA request {pa_request_id} approved")
        now = datetime.now(timezone.utc).isoformat()
        self.table.update_item(
            Key={"pa_request_id": pa_request_id},
            UpdateExpression="SET #s = :s, outcome = :o, updated_at = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": "completed_approved",
                ":o": "approved",
                ":t": now,
            },
        )

        attempt_number = record.get("attempt_number", 1)
        provider = record.get("patient", {}).get("insurance_provider", "")
        treatments = record.get("treatments_requiring_pa", [])
        treatment_text = treatments[0].get("treatment_text", "") if treatments else ""

        if attempt_number == 1:
            # save_first_approval_memory is added in WP6 -- call if available
            try:
                pa_request = PARequest(**record)
                self.self_improvement.save_first_approval_memory(pa_request, provider, treatment_text)
            except AttributeError:
                logger.debug("save_first_approval_memory not yet available (WP6)")
            except Exception as e:
                logger.error(f"Failed to save first-approval memory for {pa_request_id}: {e}")
        elif attempt_number > 1:
            try:
                pa_request = PARequest(**record)
                self.self_improvement.save_successful_appeal(pa_request, provider, treatment_text)
            except Exception as e:
                logger.error(f"Failed to save appeal memory for {pa_request_id}: {e}")

        # Increment success_count on matching existing memories
        try:
            matching_memories = self.search_service.search_memories(provider, treatment_text, limit=10)
            for mem in matching_memories.memories:
                if mem.relevance_score >= 0.5:
                    self.memory_service.increment_success_count(mem.memory_type, mem.memory_id)
        except Exception as e:
            logger.error(f"Failed to increment success counts for {pa_request_id}: {e}")

    def handle_rejection(self, pa_request_id: str, record: dict, decision: InsurerDecision):
        attempt_number = record.get("attempt_number", 1)

        if attempt_number >= self.MAX_APPEAL_ATTEMPTS:
            logger.info(
                f"PA request {pa_request_id} exhausted all {self.MAX_APPEAL_ATTEMPTS} attempts"
            )
            now = datetime.now(timezone.utc).isoformat()
            self.table.update_item(
                Key={"pa_request_id": pa_request_id},
                UpdateExpression="SET #s = :s, outcome = :o, updated_at = :t",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":s": "completed_rejected_exhausted",
                    ":o": "rejected_exhausted",
                    ":t": now,
                },
            )

            # Save anti-pattern memory
            try:
                provider = record.get("patient", {}).get("insurance_provider", "")
                treatments = record.get("treatments_requiring_pa", [])
                treatment_text = treatments[0].get("treatment_text", "") if treatments else ""
                from prior_auth_bot.models import Memory

                anti_memory = Memory(
                    memory_id=f"mem_{uuid.uuid4().hex[:8]}",
                    memory_type="anti_pattern",
                    provider=provider,
                    treatment=treatment_text,
                    advice=f"Exhausted {self.MAX_APPEAL_ATTEMPTS} attempts. Reasons: {'; '.join(decision.rejection_reasons)}",
                    source_pa_request_id=pa_request_id,
                    outcome="rejected_exhausted",
                    attempt_count=attempt_number,
                    success_count=0,
                    tags=["anti_pattern", "exhausted"],
                    created_at=now,
                    updated_at=now,
                )
                self.memory_service.save_memory(anti_memory)
            except Exception as e:
                logger.error(f"Failed to save anti-pattern memory for {pa_request_id}: {e}")
            return

        logger.info(
            f"PA request {pa_request_id} rejected (attempt {attempt_number}), starting appeal"
        )

        rejection = RejectionMessage(
            pa_request_id=pa_request_id,
            submission_id=record.get("submission_result", {}).get("submission_id", ""),
            outcome="rejected",
            has_reasons=len(decision.rejection_reasons) > 0,
            rejection_reasons=decision.rejection_reasons,
            received_at=decision.decided_at or datetime.now(timezone.utc).isoformat(),
        )

        pa_request = PARequest(**record)
        reentry = self.self_improvement.handle_rejection(rejection, pa_request)
        self.orchestrator.reenter_pipeline(reentry)
