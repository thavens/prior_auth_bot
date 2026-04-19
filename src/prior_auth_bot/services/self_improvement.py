from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from prior_auth_bot.models import (
    Memory,
    PARequest,
    RejectionContext,
    RejectionMessage,
    ReentryPayload,
)
from prior_auth_bot.services.memory_feature import MemoryFeatureService

if TYPE_CHECKING:
    from prior_auth_bot.services.embedding_service import EmbeddingService
    from prior_auth_bot.services.search_service import SearchService

logger = logging.getLogger(__name__)


class SelfImprovementService:
    def __init__(
        self,
        sqs_client=None,
        bedrock_client=None,
        memory_service: MemoryFeatureService | None = None,
        queue_url: str = "",
        model_id: str = "anthropic.claude-sonnet-4-6",
        search_service: SearchService | None = None,
        embedding_service: EmbeddingService | None = None,
    ):
        self.sqs = sqs_client
        self.bedrock = bedrock_client
        self.memory_service = memory_service
        self.queue_url = queue_url
        self.model_id = model_id
        self.search_service = search_service
        self.embedding_service = embedding_service

    def handle_rejection(self, rejection: RejectionMessage, pa_request: PARequest) -> ReentryPayload:
        mode = "rejection_with_reasons" if rejection.has_reasons else "rejection_without_reasons"

        # RAG: search for similar past rejections to inject into the prompt
        similar_context = ""
        if self.search_service:
            try:
                treatment_text = ""
                treatments = pa_request.treatments_requiring_pa or []
                if treatments:
                    first = treatments[0]
                    treatment_text = first.get("treatment_text", "") if isinstance(first, dict) else ""
                provider = pa_request.patient.insurance_provider if pa_request.patient else ""
                query = f"rejection {provider} {treatment_text} {' '.join(rejection.rejection_reasons)}"
                similar_memories = self.search_service.search_memories_semantic(query, limit=5)
                if similar_memories.memories:
                    similar_context = "\nSIMILAR PAST CASES:\n"
                    for m in similar_memories.memories:
                        outcome = (m.outcome or "").lower()
                        if "approved" in outcome or "appeal" in outcome:
                            label = f"PROVEN FIX (approved on appeal, success_count: {m.success_count})"
                        elif "rejected" in outcome or "exhausted" in outcome:
                            label = "ANTI-PATTERN (led to final rejection)"
                        else:
                            label = f"OUTCOME: {m.outcome}"
                        similar_context += f"- {label}: {m.advice}\n"
            except Exception:
                logger.exception("Failed to retrieve similar memories for rejection handling")

        prompt = self._build_prompt(rejection, pa_request, mode, similar_context=similar_context)
        proposed_fixes = self._call_llm(prompt)
        attempt_hash = f"att_{uuid.uuid4().hex[:8]}"
        return ReentryPayload(
            pa_request_id=rejection.pa_request_id,
            attempt_number=pa_request.attempt_number + 1,
            attempt_hash=attempt_hash,
            mode=mode,
            rejection_context=RejectionContext(
                previous_attempt_hash=pa_request.attempt_hash,
                rejection_reasons=rejection.rejection_reasons,
                proposed_fixes=proposed_fixes,
            ),
        )

    def save_successful_appeal(self, pa_request: PARequest, provider: str, treatment: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        advice_parts = []
        for entry in pa_request.rejection_history:
            reasons = entry.get("rejection_reasons", [])
            fixes = entry.get("proposed_fixes", [])
            if reasons:
                advice_parts.append(f"Rejected for: {'; '.join(reasons)}")
            if fixes:
                advice_parts.append(f"Fixed by: {'; '.join(fixes)}")
        advice = " | ".join(advice_parts) if advice_parts else "Approved on appeal after resubmission."

        embedding = []
        if self.embedding_service:
            try:
                embedding_text = f"{provider} {treatment} {advice}"
                embedding = self.embedding_service.embed(embedding_text)
            except Exception:
                logger.exception("Failed to generate embedding for successful appeal memory")

        memory = Memory(
            memory_id=f"mem_{uuid.uuid4().hex[:8]}",
            memory_type="treatment_provider",
            memory_subtype="appeal_success",
            provider=provider,
            treatment=treatment,
            advice=advice,
            source_pa_request_id=pa_request.pa_request_id,
            outcome="approved_on_appeal",
            attempt_count=pa_request.attempt_number,
            success_count=1,
            tags=["appeal", "successful"],
            created_at=now,
            updated_at=now,
            embedding=embedding,
        )
        self.memory_service.save_memory(memory)

    def save_first_approval_memory(self, record: PARequest, provider: str, treatment: str) -> None:
        """Save a memory when a PA is approved on the first attempt."""
        now = datetime.now(timezone.utc).isoformat()
        advice = f"Approved on first attempt for {treatment} with {provider}."
        selected_forms = record.selected_forms or []
        if selected_forms:
            first_form = selected_forms[0]
            form_name = first_form.get("form_name", "") if isinstance(first_form, dict) else getattr(first_form, "form_name", "")
            if form_name:
                advice += f" Form: {form_name}."

        embedding = []
        if self.embedding_service:
            try:
                embedding_text = f"{provider} {treatment} {advice}"
                embedding = self.embedding_service.embed(embedding_text)
            except Exception:
                logger.exception("Failed to generate embedding for first-approval memory")

        memory = Memory(
            memory_id=f"mem_{uuid.uuid4().hex[:8]}",
            memory_type="strategy",
            memory_subtype="first_approval",
            provider=provider,
            treatment=treatment,
            advice=advice,
            source_pa_request_id=record.pa_request_id,
            outcome="approved_first_attempt",
            attempt_count=1,
            success_count=1,
            tags=["first_approval", "successful"],
            created_at=now,
            updated_at=now,
            embedding=embedding,
        )
        self.memory_service.save_memory(memory)

    def save_exhausted_rejection_memory(self, record: PARequest, provider: str, treatment: str, rejection_history: list) -> None:
        """Save an anti-pattern memory when all appeal attempts are exhausted."""
        now = datetime.now(timezone.utc).isoformat()
        advice_parts = [
            f"ANTI-PATTERN: Failed after {record.attempt_number} attempts for {treatment} with {provider}."
        ]
        for entry in rejection_history:
            reasons = entry.get("rejection_reasons", []) if isinstance(entry, dict) else []
            fixes = entry.get("proposed_fixes", []) if isinstance(entry, dict) else []
            if reasons:
                advice_parts.append(f"Rejected for: {'; '.join(reasons)}")
            if fixes:
                advice_parts.append(f"Tried fix: {'; '.join(fixes)}")
        advice = " | ".join(advice_parts)

        embedding = []
        if self.embedding_service:
            try:
                embedding_text = f"{provider} {treatment} {advice}"
                embedding = self.embedding_service.embed(embedding_text)
            except Exception:
                logger.exception("Failed to generate embedding for exhausted-rejection memory")

        memory = Memory(
            memory_id=f"mem_{uuid.uuid4().hex[:8]}",
            memory_type="strategy",
            memory_subtype="exhausted_rejection",
            provider=provider,
            treatment=treatment,
            advice=advice,
            source_pa_request_id=record.pa_request_id,
            outcome="rejected_exhausted",
            attempt_count=record.attempt_number,
            success_count=0,
            tags=["anti_pattern", "exhausted"],
            created_at=now,
            updated_at=now,
            embedding=embedding,
        )
        self.memory_service.save_memory(memory)

    def _build_prompt(self, rejection: RejectionMessage, pa_request: PARequest, mode: str, similar_context: str = "") -> str:
        patient_name = f"{pa_request.patient.first_name} {pa_request.patient.last_name}"
        insurance = pa_request.patient.insurance_provider
        treatment_info = json.dumps(pa_request.treatments_requiring_pa) if pa_request.treatments_requiring_pa else "N/A"
        if mode == "rejection_with_reasons":
            reasons_list = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(rejection.rejection_reasons))
            return (
                "A prior authorization request was rejected. Analyze the rejection reasons and propose specific fixes.\n"
                "\n"
                f"PA Request ID: {rejection.pa_request_id}\n"
                f"Patient: {patient_name}\n"
                f"Insurance: {insurance}\n"
                f"Treatment: {treatment_info}\n"
                f"Current attempt: {pa_request.attempt_number}\n"
                "\n"
                "Rejection reasons:\n"
                f"{reasons_list}\n"
                f"{similar_context}\n"
                "Propose specific, actionable fixes for each rejection reason. Respond with a JSON array of fix strings.\n"
                "\n"
                "JSON:"
            )
        return (
            "A prior authorization request was rejected without explanation. Based on common PA rejection patterns, brainstorm the most likely reasons and propose fixes ranked from most to least likely.\n"
            "\n"
            f"PA Request ID: {rejection.pa_request_id}\n"
            f"Patient: {patient_name}\n"
            f"Insurance: {insurance}\n"
            f"Treatment: {treatment_info}\n"
            f"Current attempt: {pa_request.attempt_number}\n"
            f"{similar_context}\n"
            "Propose a ranked list of the 3-5 most likely fixes. Respond with a JSON array of fix strings, ordered from most to least likely helpful.\n"
            "\n"
            "JSON:"
        )

    def _call_llm(self, prompt: str) -> list[str]:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": prompt}],
        })
        response = self.bedrock.invoke_model(
            modelId=self.model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        text = result["content"][0]["text"]
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            cleaned = re.sub(r",\s*([}\]])", r"\1", text.strip())
            return json.loads(cleaned)
