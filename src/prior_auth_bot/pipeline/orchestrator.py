import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import boto3


def _sanitize_for_dynamo(obj):
    """Convert floats to Decimals for DynamoDB compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _sanitize_for_dynamo(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_dynamo(i) for i in obj]
    return obj

from prior_auth_bot.models import (
    PARequest,
    Patient,
    Physician,
    TreatmentInfo,
    DocumentPopulationInput,
    ReentryPayload,
    EarlyMemoryContext,
    Memory,
)
from prior_auth_bot.services.speech_to_text import SpeechToTextService
from prior_auth_bot.services.search_service import SearchService
from prior_auth_bot.services.memory_feature import MemoryFeatureService
from prior_auth_bot.services.document_download import DocumentDownloadService
from prior_auth_bot.services.document_population import DocumentPopulationService
from prior_auth_bot.services.document_courier import EmailCourierService
from prior_auth_bot.services.self_improvement import SelfImprovementService
from prior_auth_bot.services.patient_service import PatientService
from prior_auth_bot.services.physician_service import PhysicianService
from prior_auth_bot.pipeline import steps

PATIENT_SNAPSHOT_FIELDS = ("patient_id", "first_name", "last_name", "dob", "insurance_provider", "insurance_id", "address", "phone")
PHYSICIAN_SNAPSHOT_FIELDS = ("physician_id", "first_name", "last_name", "npi", "specialty", "phone", "fax")


class PipelineOrchestrator:
    def __init__(
        self,
        speech_to_text: SpeechToTextService,
        search_service: SearchService,
        memory_service: MemoryFeatureService,
        document_download: DocumentDownloadService,
        document_population: DocumentPopulationService,
        document_courier: EmailCourierService,
        self_improvement: SelfImprovementService,
        patient_service: PatientService,
        physician_service: PhysicianService,
        dynamodb_resource,
        s3_client,
        textract_output_bucket: str,
        bedrock_client,
        pa_requests_table: str,
        model_id: str = "anthropic.claude-sonnet-4-6",
        embedding_service=None,
    ):
        self.stt = speech_to_text
        self.search = search_service
        self.memory = memory_service
        self.doc_download = document_download
        self.doc_pop = document_population
        self.courier = document_courier
        self.self_improvement = self_improvement
        self.patient_service = patient_service
        self.physician_service = physician_service
        self.table = dynamodb_resource.Table(pa_requests_table)
        self.s3 = s3_client
        self.textract_output_bucket = textract_output_bucket
        self.bedrock = bedrock_client
        self.model_id = model_id
        self.embedding_service = embedding_service

    def _hydrate_snapshot(self, patient_id: str, physician_id: str) -> tuple[Patient, Physician]:
        patient_record = self.patient_service.get(patient_id)
        physician_record = self.physician_service.get(physician_id)
        patient_snapshot = {k: patient_record.get(k, "") for k in PATIENT_SNAPSHOT_FIELDS}
        physician_snapshot = {k: physician_record.get(k, "") for k in PHYSICIAN_SNAPSHOT_FIELDS}
        return Patient(**patient_snapshot), Physician(**physician_snapshot)

    def run_pipeline(
        self,
        pa_request_id: str,
        audio_bytes: bytes,
        audio_format: str,
        patient_id: str,
        physician_id: str,
    ) -> dict:
        patient, physician = self._hydrate_snapshot(patient_id, physician_id)

        attempt_hash = f"att_{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "pa_request_id": pa_request_id,
            "created_at": now,
            "updated_at": now,
            "status": "queued",
            "patient": patient.model_dump(),
            "physician": physician.model_dump(),
            "attempt_number": 1,
            "attempt_hash": attempt_hash,
            "rejection_history": [],
        }
        self.table.put_item(Item=record)

        try:
            self._update_status(pa_request_id, "step_1_entity_extraction")
            transcript = self.stt.transcribe(pa_request_id, audio_bytes, audio_format)
            self._update_field(pa_request_id, "transcript", transcript.transcript_text)
            self._update_field(pa_request_id, "audio_s3_key", f"pa-audio-uploads/{pa_request_id}/appointment.{audio_format}")

            # Early memory retrieval for RAG injection into steps 1 & 2
            early_memories = self._get_early_memory_context(
                insurance_provider=patient.insurance_provider,
                context_text=transcript.transcript_text,
            )

            entities = steps.step_1_entity_extraction(
                transcript_text=transcript.transcript_text,
                insurance_provider=patient.insurance_provider,
                search_service=self.search,
                s3_client=self.s3,
                textract_output_bucket=self.textract_output_bucket,
                bedrock_client=self.bedrock,
                model_id=self.model_id,
                memory_context=early_memories,
            )
            self._update_field(pa_request_id, "entities", [e.model_dump() for e in entities.entities])

            self._update_status(pa_request_id, "step_2_pa_determination")
            pa_result = steps.step_2_pa_determination(
                entities,
                {"insurance_provider": patient.insurance_provider},
                self.search,
                self.bedrock,
                self.model_id,
                memory_context=early_memories,
            )
            self._update_field(pa_request_id, "treatments_requiring_pa", [t.model_dump() for t in pa_result.treatments_requiring_pa])

            if not pa_result.treatments_requiring_pa:
                self._update_status(pa_request_id, "completed_no_pa_required")
                return self._get_record(pa_request_id)

            self._update_status(pa_request_id, "step_3_form_selection")
            forms = steps.step_3_form_selection(
                pa_result.treatments_requiring_pa,
                {"insurance_provider": patient.insurance_provider},
                self.search,
                self.bedrock,
                self.model_id,
            )
            self._update_field(pa_request_id, "selected_forms", [f.model_dump() for f in forms.selected_forms])

            self._update_status(pa_request_id, "step_4_memory_retrieval")
            memories = steps.step_4_memory_retrieval(pa_result.treatments_requiring_pa, self.search)
            self._update_field(pa_request_id, "memories", [m.model_dump() for m in memories.memories])

            self._update_status(pa_request_id, "step_5_document_population")
            completed_keys = []
            for form in forms.selected_forms:
                matching_treatment = next(
                    (t for t in pa_result.treatments_requiring_pa if t.entity_id == form.treatment_entity_id),
                    pa_result.treatments_requiring_pa[0],
                )
                pop_input = DocumentPopulationInput(
                    pa_request_id=pa_request_id,
                    attempt_hash=attempt_hash,
                    form_s3_key=form.form_s3_key.replace("pa-blank-forms/", ""),
                    textract_s3_key=form.textract_s3_key.replace("pa-textract-output/", ""),
                    patient=patient,
                    physician=physician,
                    treatment=TreatmentInfo(
                        entity_id=matching_treatment.entity_id,
                        text=matching_treatment.treatment_text,
                        category=matching_treatment.category,
                        pa_reason=matching_treatment.pa_reason,
                    ),
                    memories=memories.memories,
                )
                result = self.doc_pop.populate_form(pop_input)
                completed_keys.append(result.completed_form_s3_key)
            self._update_field(pa_request_id, "completed_form_s3_keys", completed_keys)

            self._update_status(pa_request_id, "step_6_document_submission")
            sub_result = None
            for key in completed_keys:
                s3_key = key.replace("pa-completed-forms/", "")
                treatment_text = pa_result.treatments_requiring_pa[0].treatment_text
                sub_result = self.courier.send(
                    patient=patient,
                    physician=physician,
                    treatment_text=treatment_text,
                    insurance_provider=patient.insurance_provider,
                    insurance_id=patient.insurance_id,
                    completed_form_s3_key=s3_key,
                )
            if sub_result:
                self._update_field(pa_request_id, "submission_result", sub_result.model_dump())

            self._update_status(pa_request_id, "pending_insurer_review")

        except Exception as e:
            try:
                self._update_status(pa_request_id, "failed")
                self._update_field(pa_request_id, "error", str(e))
            except Exception:
                pass
            raise

        return self._get_record(pa_request_id)

    def reenter_pipeline(self, reentry: ReentryPayload) -> dict:
        pa_request_id = reentry.pa_request_id

        self._update_status(pa_request_id, "appealing")
        self._update_field(pa_request_id, "attempt_number", reentry.attempt_number)
        self._update_field(pa_request_id, "attempt_hash", reentry.attempt_hash)

        existing = self._get_record(pa_request_id)
        history = existing.get("rejection_history", [])
        history.append(reentry.rejection_context.model_dump())
        self._update_field(pa_request_id, "rejection_history", history)

        patient = Patient(**existing["patient"])
        physician = Physician(**existing["physician"])

        try:
            treatments_raw = existing.get("treatments_requiring_pa", [])
            from prior_auth_bot.models import TreatmentPAResult
            treatments = [TreatmentPAResult(**t) for t in treatments_raw]

            # Early memory retrieval for re-entry, using rejection context for richer queries
            rejection_text = " ".join(
                reason
                for entry in history
                for reason in (entry.get("rejection_reasons") or [])
            )
            treatment_text = " ".join(t.treatment_text for t in treatments)
            reentry_context = f"{rejection_text} {treatment_text}"
            early_memories = self._get_early_memory_context(
                insurance_provider=patient.insurance_provider,
                context_text=reentry_context,
            )

            self._update_status(pa_request_id, "step_3_form_selection")
            forms = steps.step_3_form_selection(
                treatments,
                {"insurance_provider": patient.insurance_provider},
                self.search,
                self.bedrock,
                self.model_id,
            )
            self._update_field(pa_request_id, "selected_forms", [f.model_dump() for f in forms.selected_forms])

            self._update_status(pa_request_id, "step_4_memory_retrieval")
            memories = steps.step_4_memory_retrieval(treatments, self.search)
            self._update_field(pa_request_id, "memories", [m.model_dump() for m in memories.memories])

            self._update_status(pa_request_id, "step_5_document_population")
            completed_keys = []
            for form in forms.selected_forms:
                matching_treatment = next(
                    (t for t in treatments if t.entity_id == form.treatment_entity_id),
                    treatments[0],
                )
                pop_input = DocumentPopulationInput(
                    pa_request_id=pa_request_id,
                    attempt_hash=reentry.attempt_hash,
                    form_s3_key=form.form_s3_key.replace("pa-blank-forms/", ""),
                    textract_s3_key=form.textract_s3_key.replace("pa-textract-output/", ""),
                    patient=patient,
                    physician=physician,
                    treatment=TreatmentInfo(
                        entity_id=matching_treatment.entity_id,
                        text=matching_treatment.treatment_text,
                        category=matching_treatment.category,
                        pa_reason=matching_treatment.pa_reason,
                    ),
                    memories=memories.memories,
                    rejection_context=reentry.rejection_context.model_dump(),
                )
                result = self.doc_pop.populate_form(pop_input)
                completed_keys.append(result.completed_form_s3_key)
            self._update_field(pa_request_id, "completed_form_s3_keys", completed_keys)

            self._update_status(pa_request_id, "step_6_document_submission")
            sub_result = None
            for key in completed_keys:
                s3_key = key.replace("pa-completed-forms/", "")
                treatment_text = treatments[0].treatment_text
                sub_result = self.courier.send(
                    patient=patient,
                    physician=physician,
                    treatment_text=treatment_text,
                    insurance_provider=patient.insurance_provider,
                    insurance_id=patient.insurance_id,
                    completed_form_s3_key=s3_key,
                )
            if sub_result:
                self._update_field(pa_request_id, "submission_result", sub_result.model_dump())

            self._update_status(pa_request_id, "pending_insurer_review")

        except Exception as e:
            try:
                self._update_status(pa_request_id, "failed")
                self._update_field(pa_request_id, "error", str(e))
            except Exception:
                pass
            raise

        return self._get_record(pa_request_id)

    def _get_early_memory_context(
        self, insurance_provider: str, context_text: str
    ) -> EarlyMemoryContext | None:
        """Retrieve memories early for RAG injection into steps 1 and 2."""
        try:
            provider_memories = self.search.search_memories(
                insurance_provider, "", limit=5
            ).memories

            treatment_memories: list[Memory] = []
            if hasattr(self.search, "search_memories_semantic"):
                query = f"{insurance_provider} {context_text[:500]}"
                treatment_memories = self.search.search_memories_semantic(
                    query, limit=5
                ).memories

            summary = ""
            if provider_memories or treatment_memories:
                all_advice = [
                    m.advice for m in (provider_memories + treatment_memories)[:5] if m.advice
                ]
                summary = "; ".join(all_advice)

            return EarlyMemoryContext(
                provider_memories=provider_memories,
                treatment_memories=treatment_memories,
                summary=summary,
            )
        except Exception:
            return None

    def _update_status(self, pa_request_id: str, status: str):
        self.table.update_item(
            Key={"pa_request_id": pa_request_id},
            UpdateExpression="SET #s = :s, updated_at = :t",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": status,
                ":t": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _update_field(self, pa_request_id: str, field: str, value):
        self.table.update_item(
            Key={"pa_request_id": pa_request_id},
            UpdateExpression="SET #f = :v, updated_at = :t",
            ExpressionAttributeNames={"#f": field},
            ExpressionAttributeValues={
                ":v": _sanitize_for_dynamo(value),
                ":t": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _get_record(self, pa_request_id: str) -> dict:
        return self.table.get_item(Key={"pa_request_id": pa_request_id}).get("Item", {})
