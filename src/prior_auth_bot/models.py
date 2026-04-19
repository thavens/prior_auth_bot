from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


# --- Core entities ---

class Patient(BaseModel):
    patient_id: str
    first_name: str
    last_name: str
    dob: str
    insurance_provider: str
    insurance_id: str
    address: str = ""
    phone: str = ""
    primary_physician_id: str = ""
    created_at: str = ""
    updated_at: str = ""


class PatientCreateInput(BaseModel):
    first_name: str
    last_name: str
    dob: str
    insurance_provider: str
    insurance_id: str
    address: str = ""
    phone: str = ""


class Physician(BaseModel):
    physician_id: str
    first_name: str
    last_name: str
    npi: str
    specialty: str = ""
    phone: str = ""
    fax: str = ""
    created_at: str = ""
    updated_at: str = ""


# --- PA Request ---

PAStatus = Literal[
    "queued",
    "step_1_entity_extraction",
    "step_2_pa_determination",
    "step_3_form_selection",
    "step_4_memory_retrieval",
    "step_5_document_population",
    "step_6_document_submission",
    "step_7_outcome_handling",
    "pending_insurer_review",
    "completed_approved",
    "completed_no_pa_required",
    "completed_rejected_exhausted",
    "failed",
    "appealing",
]


class PARequest(BaseModel):
    pa_request_id: str
    created_at: str
    updated_at: str
    status: PAStatus
    patient: Patient
    physician: Physician
    audio_s3_key: str | None = None
    transcript: str | None = None
    entities: list | None = None
    treatments_requiring_pa: list | None = None
    selected_forms: list | None = None
    memories: list | None = None
    completed_form_s3_keys: list[str] | None = None
    submission_result: dict | None = None
    outcome: str | None = None
    attempt_number: int = 1
    attempt_hash: str = ""
    rejection_history: list = []
    error: str | None = None


# --- Speech to text ---

class TranscriptResult(BaseModel):
    transcript_text: str
    transcript_s3_key: str
    language_code: str = "en-US"
    confidence: float
    duration_seconds: float


# --- Step 1: Entity extraction ---

class NormalizedConcept(BaseModel):
    rxnorm_concept: str = ""
    rxnorm_description: str = ""


class SnomedConcept(BaseModel):
    code: str
    description: str


class MedicalEntity(BaseModel):
    entity_id: str
    category: str
    text: str
    normalized: NormalizedConcept | None = None
    snomed_concepts: list[SnomedConcept] = []
    traits: list[str] = []
    confidence: float = 0.0


class EntityExtractionResult(BaseModel):
    entities: list[MedicalEntity]


# --- Step 2: PA determination ---

class TreatmentPAResult(BaseModel):
    entity_id: str
    treatment_text: str
    category: str
    requires_pa: bool
    pa_reason: str = ""
    provider_name: str = ""
    source_url: str = ""
    cached: bool = False


class PADeterminationResult(BaseModel):
    treatments_requiring_pa: list[TreatmentPAResult]
    treatments_not_requiring_pa: list[TreatmentPAResult] = []


# --- Step 3: Form selection ---

class SelectedForm(BaseModel):
    treatment_entity_id: str
    form_s3_key: str
    textract_s3_key: str
    form_name: str
    provider_name: str
    field_count: int = 0
    field_types_summary: dict[str, int] = {}


class FormSelectionResult(BaseModel):
    selected_forms: list[SelectedForm]


# --- Step 4: Memory retrieval ---

class Memory(BaseModel):
    memory_id: str
    memory_type: str
    memory_subtype: str = ""
    provider: str = ""
    treatment: str = ""
    advice: str = ""
    source_pa_request_id: str = ""
    outcome: str = ""
    attempt_count: int = 0
    success_count: int = 0
    tags: list[str] = []
    created_at: str = ""
    updated_at: str = ""
    relevance_score: float = 0.0
    embedding: list[float] = []


class MemoryRetrievalResult(BaseModel):
    memories: list[Memory]


# --- Step 5: Document population ---

class TreatmentInfo(BaseModel):
    entity_id: str
    text: str
    category: str
    rxnorm_concept: str = ""
    snomed_code: str = ""
    pa_reason: str = ""


class DocumentPopulationInput(BaseModel):
    pa_request_id: str
    attempt_hash: str
    form_s3_key: str
    textract_s3_key: str
    patient: Patient
    physician: Physician
    treatment: TreatmentInfo
    memories: list[Memory] = []
    rejection_context: dict | None = None


class FieldFillResults(BaseModel):
    total_fields: int
    filled_fields: int
    skipped_fields: int
    llm_attempts: int


class DocumentPopulationResult(BaseModel):
    completed_form_s3_key: str
    field_fill_results: FieldFillResults


# --- Step 6: Document submission ---

class DeliveryDetails(BaseModel):
    ses_message_id: str = ""
    recipient_email: str = ""
    sender_email: str = ""
    subject: str = ""
    attachment_s3_key: str = ""


class SubmissionResult(BaseModel):
    submission_id: str
    delivery_method: str
    delivery_details: DeliveryDetails
    submitted_at: str
    status: str


# --- Step 7: Self-improvement / rejection handling ---

class RejectionMessage(BaseModel):
    pa_request_id: str
    submission_id: str
    outcome: str
    has_reasons: bool
    rejection_reasons: list[str] = []
    received_at: str


class RejectionContext(BaseModel):
    previous_attempt_hash: str
    rejection_reasons: list[str] = []
    proposed_fixes: list[str] = []


class ReentryPayload(BaseModel):
    pa_request_id: str
    attempt_number: int
    attempt_hash: str
    mode: str
    rejection_context: RejectionContext


# --- Insurer decision ---

class InsurerDecision(BaseModel):
    pa_request_id: str
    decision: Literal["approved", "rejected"]
    rejection_reasons: list[str] = []
    feedback: str = ""
    decided_by: str = "insurer"
    decided_at: str = ""


# --- Early memory context (injected into steps 1 & 2) ---

class EarlyMemoryContext(BaseModel):
    provider_memories: list[Memory] = []
    treatment_memories: list[Memory] = []
    summary: str = ""


# --- Search / scrape cache ---

class ScrapeCache(BaseModel):
    cache_key: str
    url: str
    scraped_content: str
    scraped_at: str
    ttl: int
    content_hash: str = ""
