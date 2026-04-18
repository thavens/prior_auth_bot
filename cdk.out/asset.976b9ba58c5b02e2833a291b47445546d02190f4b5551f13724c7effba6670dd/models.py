"""Pydantic domain models shared across all Lambda functions."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class TreatmentType(str, Enum):
    MEDICATION = "MEDICATION"
    SURGERY = "SURGERY"
    THERAPY = "THERAPY"


class MemoryType(str, Enum):
    GLOBAL = "GLOBAL"
    DOCUMENT = "DOCUMENT"
    PROVIDER = "PROVIDER"
    PRESCRIPTION = "PRESCRIPTION"


class FieldType(str, Enum):
    TEXT = "text"
    CHECKBOX = "checkbox"
    DATE = "date"
    DROPDOWN = "dropdown"


# ---------------------------------------------------------------------------
# Core models
# ---------------------------------------------------------------------------

class Patient(BaseModel):
    patient_id: str
    name: str
    date_of_birth: str
    insurance_provider: str
    insurance_id: str
    medical_history: list[str] = Field(default_factory=list)
    current_medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)


class Treatment(BaseModel):
    treatment_id: str
    treatment_type: TreatmentType
    name: str
    rxnorm_code: Optional[str] = None
    snomed_code: Optional[str] = None
    dosage: Optional[str] = None
    frequency: Optional[str] = None
    duration: Optional[str] = None
    icd10_codes: list[str] = Field(default_factory=list)
    confidence_score: float = 0.0


class PARequirement(BaseModel):
    treatment: Treatment
    pa_required: bool
    requirements_text: str
    provider_id: str
    source_url: str
    cached: bool = False


class FormField(BaseModel):
    field_name: str
    field_type: FieldType
    description: str
    required: bool = True
    options: Optional[list[str]] = None


class FormMetadata(BaseModel):
    form_id: str
    title: str
    description: str
    s3_key: str
    fields: list[FormField] = Field(default_factory=list)
    relevance_score: float = 0.0


class Memory(BaseModel):
    memory_id: str
    memory_type: MemoryType
    content: str
    document_id: Optional[str] = None
    provider_id: Optional[str] = None
    prescription_code: Optional[str] = None
    success_count: int = 0
    failure_count: int = 0
    created_at: float = 0.0
    updated_at: float = 0.0


class PARequest(BaseModel):
    pa_request_id: str
    patient_id: str
    treatment: Treatment
    provider_id: str
    form_id: str
    filled_form_s3_key: str = ""
    status: str = "PENDING"
    attempt_number: int = 1
    rejection_reasons: Optional[str] = None
    improvement_context: list[str] = Field(default_factory=list)
    submitted_at: float = 0.0
    response_at: Optional[float] = None
