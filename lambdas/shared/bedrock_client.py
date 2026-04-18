"""Bedrock client for LLM inference and embedding generation."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import boto3

from shared.config import cfg
from shared.models import (
    PARequest,
    PARequirement,
    Patient,
    Treatment,
)

logger = logging.getLogger(__name__)


class BedrockClient:
    """Thin wrapper around Amazon Bedrock Runtime with domain-specific helpers."""

    def __init__(
        self,
        model_id: Optional[str] = None,
        region: Optional[str] = None,
    ) -> None:
        self.model_id = model_id or cfg.BEDROCK_MODEL_ID
        self.embed_model_id = cfg.BEDROCK_EMBED_MODEL_ID
        self._region = region or cfg.AWS_REGION
        self._client = boto3.client("bedrock-runtime", region_name=self._region)

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def converse(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: Optional[list[dict[str, Any]]] = None,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """Call the Bedrock Converse API and return the full response dict."""

        kwargs: dict[str, Any] = {
            "modelId": self.model_id,
            "system": [{"text": system_prompt}],
            "messages": messages,
            "inferenceConfig": {
                "maxTokens": max_tokens,
                "temperature": temperature,
            },
        }
        if tools:
            kwargs["toolConfig"] = {"tools": tools}

        try:
            response = self._client.converse(**kwargs)
            return response
        except Exception:
            logger.exception("Bedrock converse call failed")
            raise

    def generate_embedding(self, text: str) -> list[float]:
        """Generate a 1024-dimensional embedding via Amazon Titan Embed V2."""

        body = json.dumps({"inputText": text})
        try:
            response = self._client.invoke_model(
                modelId=self.embed_model_id,
                contentType="application/json",
                accept="application/json",
                body=body,
            )
            result = json.loads(response["body"].read())
            return result["embedding"]
        except Exception:
            logger.exception("Embedding generation failed")
            raise

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(response: dict[str, Any]) -> str:
        """Pull the assistant text from a Converse response."""

        for block in response.get("output", {}).get("message", {}).get("content", []):
            if "text" in block:
                return block["text"]
        return ""

    @staticmethod
    def _parse_json_response(text: str) -> Any:
        """Extract and parse a JSON payload from LLM output.

        The model may wrap JSON in a markdown code fence; we handle that
        gracefully.
        """

        cleaned = text.strip()
        if cleaned.startswith("```"):
            # Strip opening fence (with optional language tag) and closing fence.
            lines = cleaned.split("\n")
            lines = lines[1:]  # drop opening ```json / ```
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines)
        return json.loads(cleaned)

    def _converse_json(
        self,
        system_prompt: str,
        user_text: str,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> Any:
        """Convenience: converse with a single user turn, parse JSON output."""

        messages = [{"role": "user", "content": [{"text": user_text}]}]
        response = self.converse(
            system_prompt=system_prompt,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        raw_text = self._extract_text(response)
        return self._parse_json_response(raw_text)

    # ------------------------------------------------------------------
    # Domain methods
    # ------------------------------------------------------------------

    def determine_pa_requirements(
        self,
        treatments: list[Treatment],
        patient: Patient,
        provider_info: dict[str, Any],
    ) -> list[PARequirement]:
        """Determine which treatments require prior authorization.

        Returns a list of ``PARequirement`` objects -- one per input treatment.
        """

        system_prompt = (
            "You are a prior authorization requirements analyst for health insurance.\n"
            "You will receive a list of treatments, patient data, and insurance provider "
            "information. For each treatment decide whether prior authorization (PA) is "
            "required by the patient's insurance plan.\n\n"
            "Consider the following when making your determination:\n"
            "- The specific insurance provider's formulary and coverage policies\n"
            "- Whether the treatment is a brand-name drug with a generic alternative\n"
            "- Step therapy requirements\n"
            "- Quantity limits or age restrictions\n"
            "- Whether the diagnosis codes support medical necessity\n\n"
            "Return a JSON array where each element has these fields:\n"
            "  treatment_id   - the treatment's ID\n"
            "  pa_required    - boolean\n"
            "  requirements_text - description of what the PA requires (or why none is needed)\n"
            "  provider_id    - the insurance provider ID\n"
            "  source_url     - reference URL for the policy (use best guess if unknown)\n"
        )

        user_text = json.dumps(
            {
                "treatments": [t.model_dump() for t in treatments],
                "patient": patient.model_dump(),
                "provider_info": provider_info,
            },
            default=str,
        )

        parsed = self._converse_json(system_prompt, user_text)

        results: list[PARequirement] = []
        treatments_by_id = {t.treatment_id: t for t in treatments}
        for item in parsed:
            treatment = treatments_by_id.get(item["treatment_id"])
            if treatment is None:
                logger.warning("LLM returned unknown treatment_id %s", item["treatment_id"])
                continue
            results.append(
                PARequirement(
                    treatment=treatment,
                    pa_required=item["pa_required"],
                    requirements_text=item.get("requirements_text", ""),
                    provider_id=item.get("provider_id", ""),
                    source_url=item.get("source_url", ""),
                    cached=False,
                )
            )
        return results

    def select_form(
        self,
        treatment: Treatment,
        candidate_forms: list[dict[str, Any]],
        patient: Patient,
    ) -> str:
        """Choose the best prior-authorization form from a list of candidates.

        Returns the ``form_id`` of the best match.
        """

        system_prompt = (
            "You are a prior authorization form selection specialist.\n"
            "Given a treatment that requires prior authorization, a list of candidate "
            "blank PA forms, and the patient's insurance information, select the single "
            "form that is the best match.\n\n"
            "Consider:\n"
            "- The insurance provider and plan type\n"
            "- The treatment type (medication vs. surgery vs. therapy)\n"
            "- Whether the form covers the relevant drug class or procedure category\n"
            "- State or regional form requirements\n\n"
            "Return a JSON object with a single key:\n"
            '  { "form_id": "<the selected form_id>" }\n'
        )

        user_text = json.dumps(
            {
                "treatment": treatment.model_dump(),
                "candidate_forms": candidate_forms,
                "patient": patient.model_dump(),
            },
            default=str,
        )

        parsed = self._converse_json(system_prompt, user_text)
        return parsed["form_id"]

    def fill_form_fields(
        self,
        form_fields: list[dict[str, Any]],
        treatment: Treatment,
        patient: Patient,
        memories: list[dict[str, Any]],
        improvement_context: list[str],
    ) -> dict[str, str]:
        """Generate values for every field on a PA form.

        Returns a dict mapping ``field_name`` to its filled value.
        """

        system_prompt = (
            "You are an expert medical prior authorization form-filling assistant.\n"
            "Your task is to fill out a prior authorization form accurately and "
            "completely to maximize the chance of approval.\n\n"
            "Guidelines:\n"
            "- Use the patient's real data for demographic and insurance fields.\n"
            "- For medical justification fields, construct a compelling clinical "
            "  narrative that establishes medical necessity.\n"
            "- Reference relevant diagnosis codes (ICD-10) and procedure codes.\n"
            "- Incorporate advice from past successful submissions (memories).\n"
            "- Apply any improvement context from prior rejected attempts.\n"
            "- For checkbox fields, return 'Yes' or 'No'.\n"
            "- For date fields, use MM/DD/YYYY format.\n"
            "- For dropdown fields, choose from the provided options.\n"
            "- Never leave a required field empty; provide the best available data.\n\n"
            "Return a JSON object mapping each field_name to its string value.\n"
        )

        user_text = json.dumps(
            {
                "form_fields": form_fields,
                "treatment": treatment.model_dump(),
                "patient": patient.model_dump(),
                "memories": memories,
                "improvement_context": improvement_context,
            },
            default=str,
        )

        return self._converse_json(system_prompt, user_text)

    def analyze_rejection(
        self,
        rejection_reasons: str,
        pa_request: PARequest,
        patient: Patient,
    ) -> dict[str, Any]:
        """Analyze a PA rejection and suggest targeted fixes.

        Returns a dict with keys ``fixes`` (list of fix descriptions) and
        ``enhanced_context`` (list of context strings for the next attempt).
        """

        system_prompt = (
            "You are a prior authorization appeals specialist.\n"
            "A prior authorization request was rejected. Analyze the rejection reasons "
            "and the original request to determine what went wrong and how to fix it.\n\n"
            "Provide:\n"
            "1. Specific fixes — concrete changes to form fields or supporting "
            "   documentation that address each rejection reason.\n"
            "2. Enhanced context — additional clinical context, references, or "
            "   justifications to include in the next submission.\n\n"
            "Return a JSON object:\n"
            "{\n"
            '  "fixes": ["fix 1 description", "fix 2 description", ...],\n'
            '  "enhanced_context": ["context string 1", "context string 2", ...]\n'
            "}\n"
        )

        user_text = json.dumps(
            {
                "rejection_reasons": rejection_reasons,
                "pa_request": pa_request.model_dump(),
                "patient": patient.model_dump(),
            },
            default=str,
        )

        return self._converse_json(system_prompt, user_text)

    def brainstorm_improvements(
        self,
        pa_request: PARequest,
        patient: Patient,
        previous_attempts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Brainstorm ranked improvement ideas when no explicit rejection reason is given.

        Returns a list of dicts, each with keys ``description``, ``priority``
        (int, 1 = highest), and ``rationale``.
        """

        system_prompt = (
            "You are a prior authorization strategy consultant.\n"
            "A prior authorization was rejected but no specific rejection reasons were "
            "provided.  Based on the request details, patient data, and history of "
            "previous attempts, brainstorm a prioritized list of potential improvements.\n\n"
            "Rank improvements from most to least likely to succeed.  For each idea, "
            "explain the rationale and what specifically should change.\n\n"
            "Consider strategies such as:\n"
            "- Adding supporting clinical documentation or lab results\n"
            "- Strengthening the medical necessity argument\n"
            "- Including peer-reviewed literature citations\n"
            "- Requesting a peer-to-peer review\n"
            "- Trying an alternative form or submission route\n"
            "- Addressing common denial patterns for this treatment class\n\n"
            "Return a JSON array of objects:\n"
            "[\n"
            '  { "description": "...", "priority": 1, "rationale": "..." },\n'
            "  ...\n"
            "]\n"
        )

        user_text = json.dumps(
            {
                "pa_request": pa_request.model_dump(),
                "patient": patient.model_dump(),
                "previous_attempts": previous_attempts,
            },
            default=str,
        )

        return self._converse_json(system_prompt, user_text)

    def extract_learnings(
        self,
        pa_request: PARequest,
        outcome: str,
    ) -> list[dict[str, Any]]:
        """Extract reusable learnings from a completed PA cycle.

        ``outcome`` should be ``"APPROVED"`` or ``"REJECTED"``.

        Returns a list of dicts with keys ``content`` (the memory text) and
        ``memory_type`` (one of GLOBAL, DOCUMENT, PROVIDER, PRESCRIPTION).
        """

        system_prompt = (
            "You are a prior authorization knowledge engineer.\n"
            "A prior authorization request has completed.  Analyze the request and its "
            "outcome to extract reusable learnings that can improve future submissions.\n\n"
            "Categorize each learning into one of these memory types:\n"
            "- GLOBAL: universally applicable advice (e.g., formatting tips)\n"
            "- DOCUMENT: specific to the form that was used\n"
            "- PROVIDER: specific to the insurance provider\n"
            "- PRESCRIPTION: specific to the medication, surgery, or therapy\n\n"
            "For approvals, capture what worked well.  For rejections after all retries "
            "are exhausted, capture what to avoid and what might work in the future.\n\n"
            "Return a JSON array of objects:\n"
            "[\n"
            '  { "content": "...", "memory_type": "GLOBAL|DOCUMENT|PROVIDER|PRESCRIPTION" },\n'
            "  ...\n"
            "]\n"
        )

        user_text = json.dumps(
            {
                "pa_request": pa_request.model_dump(),
                "outcome": outcome,
            },
            default=str,
        )

        return self._converse_json(system_prompt, user_text)
