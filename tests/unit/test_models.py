"""Unit tests for Pydantic domain models in lambdas/shared/models.py."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Make the shared layer importable without installing it as a package.
# ---------------------------------------------------------------------------
_LAMBDAS_DIR = str(Path(__file__).resolve().parents[2] / "lambdas")
_SHARED_DIR = str(Path(__file__).resolve().parents[2] / "lambdas" / "shared")
for _p in (_LAMBDAS_DIR, _SHARED_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from models import (  # noqa: E402
    FieldType,
    FormField,
    FormMetadata,
    Memory,
    MemoryType,
    PARequest,
    Patient,
    Treatment,
    TreatmentType,
)


# ===================================================================
# Patient
# ===================================================================

class TestPatient:
    """Tests for the Patient model."""

    def test_create_with_required_fields(self):
        patient = Patient(
            patient_id="P-001",
            name="Jane Doe",
            date_of_birth="1990-05-15",
            insurance_provider="Aetna",
            insurance_id="AET-123456",
        )
        assert patient.patient_id == "P-001"
        assert patient.name == "Jane Doe"
        assert patient.date_of_birth == "1990-05-15"
        assert patient.insurance_provider == "Aetna"
        assert patient.insurance_id == "AET-123456"

    def test_default_lists(self):
        patient = Patient(
            patient_id="P-002",
            name="John Smith",
            date_of_birth="1985-01-01",
            insurance_provider="BCBS",
            insurance_id="BCBS-789",
        )
        assert patient.medical_history == []
        assert patient.current_medications == []
        assert patient.allergies == []

    def test_create_with_all_fields(self):
        patient = Patient(
            patient_id="P-003",
            name="Alice Johnson",
            date_of_birth="1978-12-25",
            insurance_provider="UnitedHealth",
            insurance_id="UH-555",
            medical_history=["Hypertension", "Type 2 Diabetes"],
            current_medications=["Metformin 500mg", "Lisinopril 10mg"],
            allergies=["Penicillin"],
        )
        assert len(patient.medical_history) == 2
        assert "Metformin 500mg" in patient.current_medications
        assert patient.allergies == ["Penicillin"]

    def test_serialization(self):
        patient = Patient(
            patient_id="P-004",
            name="Bob Brown",
            date_of_birth="2000-06-30",
            insurance_provider="Cigna",
            insurance_id="CIG-999",
            allergies=["Sulfa"],
        )
        data = patient.model_dump()
        assert isinstance(data, dict)
        assert data["patient_id"] == "P-004"
        assert data["name"] == "Bob Brown"
        assert data["allergies"] == ["Sulfa"]
        assert data["medical_history"] == []
        assert data["current_medications"] == []

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            Patient(
                patient_id="P-005",
                name="Missing Insurance",
                date_of_birth="1990-01-01",
                # insurance_provider and insurance_id omitted
            )

    def test_default_lists_are_independent(self):
        """Each instance should get its own default list, not a shared reference."""
        p1 = Patient(
            patient_id="P-010",
            name="A",
            date_of_birth="2000-01-01",
            insurance_provider="X",
            insurance_id="X1",
        )
        p2 = Patient(
            patient_id="P-011",
            name="B",
            date_of_birth="2000-01-01",
            insurance_provider="Y",
            insurance_id="Y1",
        )
        p1.allergies.append("Latex")
        assert p2.allergies == []


# ===================================================================
# Treatment
# ===================================================================

class TestTreatment:
    """Tests for the Treatment model."""

    def test_create_medication(self):
        treatment = Treatment(
            treatment_id="T-001",
            treatment_type=TreatmentType.MEDICATION,
            name="Humira",
            rxnorm_code="327361",
            dosage="40mg",
            frequency="biweekly",
        )
        assert treatment.treatment_type == TreatmentType.MEDICATION
        assert treatment.name == "Humira"
        assert treatment.rxnorm_code == "327361"

    def test_create_surgery(self):
        treatment = Treatment(
            treatment_id="T-002",
            treatment_type=TreatmentType.SURGERY,
            name="Knee Replacement",
            snomed_code="179344006",
        )
        assert treatment.treatment_type == TreatmentType.SURGERY
        assert treatment.snomed_code == "179344006"

    def test_create_therapy(self):
        treatment = Treatment(
            treatment_id="T-003",
            treatment_type=TreatmentType.THERAPY,
            name="Physical Therapy",
            duration="6 weeks",
        )
        assert treatment.treatment_type == TreatmentType.THERAPY
        assert treatment.duration == "6 weeks"

    def test_default_values(self):
        treatment = Treatment(
            treatment_id="T-004",
            treatment_type=TreatmentType.MEDICATION,
            name="Aspirin",
        )
        assert treatment.rxnorm_code is None
        assert treatment.snomed_code is None
        assert treatment.dosage is None
        assert treatment.frequency is None
        assert treatment.duration is None
        assert treatment.icd10_codes == []
        assert treatment.confidence_score == 0.0

    def test_serialization(self):
        treatment = Treatment(
            treatment_id="T-005",
            treatment_type=TreatmentType.MEDICATION,
            name="Metformin",
            rxnorm_code="860975",
            icd10_codes=["E11.9"],
            confidence_score=0.95,
        )
        data = treatment.model_dump()
        assert data["treatment_type"] == "MEDICATION"
        assert data["rxnorm_code"] == "860975"
        assert data["icd10_codes"] == ["E11.9"]
        assert data["confidence_score"] == 0.95

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            Treatment(
                treatment_id="T-006",
                # treatment_type omitted
                name="Incomplete",
            )

    def test_treatment_type_enum_values(self):
        assert TreatmentType.MEDICATION.value == "MEDICATION"
        assert TreatmentType.SURGERY.value == "SURGERY"
        assert TreatmentType.THERAPY.value == "THERAPY"


# ===================================================================
# PARequest
# ===================================================================

class TestPARequest:
    """Tests for the PARequest model."""

    def _make_treatment(self) -> Treatment:
        return Treatment(
            treatment_id="T-100",
            treatment_type=TreatmentType.MEDICATION,
            name="Ozempic",
            rxnorm_code="1991302",
        )

    def test_create_with_required_fields(self):
        pa = PARequest(
            pa_request_id="PA-001",
            patient_id="P-001",
            treatment=self._make_treatment(),
            provider_id="PROV-001",
            form_id="FORM-001",
        )
        assert pa.pa_request_id == "PA-001"
        assert pa.treatment.name == "Ozempic"

    def test_default_values(self):
        pa = PARequest(
            pa_request_id="PA-002",
            patient_id="P-002",
            treatment=self._make_treatment(),
            provider_id="PROV-002",
            form_id="FORM-002",
        )
        assert pa.filled_form_s3_key == ""
        assert pa.status == "PENDING"
        assert pa.attempt_number == 1
        assert pa.rejection_reasons is None
        assert pa.improvement_context == []
        assert pa.submitted_at == 0.0
        assert pa.response_at is None

    def test_serialization_includes_nested_treatment(self):
        pa = PARequest(
            pa_request_id="PA-003",
            patient_id="P-003",
            treatment=self._make_treatment(),
            provider_id="PROV-003",
            form_id="FORM-003",
            status="SUBMITTED",
            attempt_number=2,
        )
        data = pa.model_dump()
        assert data["status"] == "SUBMITTED"
        assert data["attempt_number"] == 2
        assert data["treatment"]["name"] == "Ozempic"
        assert data["treatment"]["treatment_type"] == "MEDICATION"

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            PARequest(
                pa_request_id="PA-004",
                patient_id="P-004",
                # treatment omitted
                provider_id="PROV-004",
                form_id="FORM-004",
            )


# ===================================================================
# Memory
# ===================================================================

class TestMemory:
    """Tests for the Memory model."""

    def test_create_global_memory(self):
        memory = Memory(
            memory_id="M-001",
            memory_type=MemoryType.GLOBAL,
            content="Always include ICD-10 codes in the diagnosis field",
        )
        assert memory.memory_type == MemoryType.GLOBAL
        assert memory.document_id is None
        assert memory.provider_id is None
        assert memory.prescription_code is None

    def test_create_document_memory(self):
        memory = Memory(
            memory_id="M-002",
            memory_type=MemoryType.DOCUMENT,
            content="Medi-Cal Rx form requires NDC in field 14",
            document_id="DOC-001",
        )
        assert memory.memory_type == MemoryType.DOCUMENT
        assert memory.document_id == "DOC-001"

    def test_create_provider_memory(self):
        memory = Memory(
            memory_id="M-003",
            memory_type=MemoryType.PROVIDER,
            content="Aetna requires step therapy docs for biologics",
            provider_id="AETNA",
        )
        assert memory.provider_id == "AETNA"

    def test_create_prescription_memory(self):
        memory = Memory(
            memory_id="M-004",
            memory_type=MemoryType.PRESCRIPTION,
            content="Humira PA requires TB test results within 6 months",
            prescription_code="327361",
        )
        assert memory.prescription_code == "327361"

    def test_default_counters_and_timestamps(self):
        memory = Memory(
            memory_id="M-005",
            memory_type=MemoryType.GLOBAL,
            content="Test memory",
        )
        assert memory.success_count == 0
        assert memory.failure_count == 0
        assert memory.created_at == 0.0
        assert memory.updated_at == 0.0

    def test_serialization(self):
        memory = Memory(
            memory_id="M-006",
            memory_type=MemoryType.PROVIDER,
            content="UH requires phone auth for imaging",
            provider_id="UH",
            success_count=5,
            failure_count=1,
            created_at=1700000000.0,
            updated_at=1700100000.0,
        )
        data = memory.model_dump()
        assert data["memory_type"] == "PROVIDER"
        assert data["provider_id"] == "UH"
        assert data["success_count"] == 5
        assert data["failure_count"] == 1

    def test_memory_type_enum_values(self):
        assert MemoryType.GLOBAL.value == "GLOBAL"
        assert MemoryType.DOCUMENT.value == "DOCUMENT"
        assert MemoryType.PROVIDER.value == "PROVIDER"
        assert MemoryType.PRESCRIPTION.value == "PRESCRIPTION"

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            Memory(
                memory_id="M-007",
                # memory_type omitted
                content="Incomplete memory",
            )


# ===================================================================
# FormField
# ===================================================================

class TestFormField:
    """Tests for the FormField model."""

    def test_create_text_field(self):
        field = FormField(
            field_name="patient_name",
            field_type=FieldType.TEXT,
            description="Full legal name of the patient",
        )
        assert field.field_name == "patient_name"
        assert field.field_type == FieldType.TEXT
        assert field.required is True
        assert field.options is None

    def test_create_checkbox_field(self):
        field = FormField(
            field_name="urgent",
            field_type=FieldType.CHECKBOX,
            description="Check if urgent request",
            required=False,
        )
        assert field.field_type == FieldType.CHECKBOX
        assert field.required is False

    def test_create_dropdown_field_with_options(self):
        field = FormField(
            field_name="state",
            field_type=FieldType.DROPDOWN,
            description="Patient state of residence",
            options=["CA", "NY", "TX"],
        )
        assert field.field_type == FieldType.DROPDOWN
        assert field.options == ["CA", "NY", "TX"]

    def test_create_date_field(self):
        field = FormField(
            field_name="date_of_birth",
            field_type=FieldType.DATE,
            description="Patient date of birth",
        )
        assert field.field_type == FieldType.DATE

    def test_default_required_is_true(self):
        field = FormField(
            field_name="diagnosis",
            field_type=FieldType.TEXT,
            description="Primary diagnosis",
        )
        assert field.required is True

    def test_serialization(self):
        field = FormField(
            field_name="ndc_code",
            field_type=FieldType.TEXT,
            description="National Drug Code",
            required=True,
        )
        data = field.model_dump()
        assert data["field_name"] == "ndc_code"
        assert data["field_type"] == "text"
        assert data["required"] is True
        assert data["options"] is None

    def test_field_type_enum_values(self):
        assert FieldType.TEXT.value == "text"
        assert FieldType.CHECKBOX.value == "checkbox"
        assert FieldType.DATE.value == "date"
        assert FieldType.DROPDOWN.value == "dropdown"

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            FormField(
                field_name="incomplete",
                # field_type omitted
                description="Missing type",
            )


# ===================================================================
# FormMetadata
# ===================================================================

class TestFormMetadata:
    """Tests for the FormMetadata model."""

    def test_create_with_required_fields(self):
        meta = FormMetadata(
            form_id="FORM-001",
            title="Medi-Cal Rx Prior Authorization Request",
            description="Standard PA form for Medi-Cal prescription drugs",
            s3_key="blank-forms/medi-cal-rx-pa.pdf",
        )
        assert meta.form_id == "FORM-001"
        assert meta.title == "Medi-Cal Rx Prior Authorization Request"
        assert meta.s3_key == "blank-forms/medi-cal-rx-pa.pdf"

    def test_default_values(self):
        meta = FormMetadata(
            form_id="FORM-002",
            title="Generic PA Form",
            description="A generic form",
            s3_key="blank-forms/generic.pdf",
        )
        assert meta.fields == []
        assert meta.relevance_score == 0.0

    def test_create_with_fields(self):
        fields = [
            FormField(
                field_name="patient_name",
                field_type=FieldType.TEXT,
                description="Patient full name",
            ),
            FormField(
                field_name="dob",
                field_type=FieldType.DATE,
                description="Date of birth",
            ),
        ]
        meta = FormMetadata(
            form_id="FORM-003",
            title="Aetna PA Form",
            description="Aetna prior authorization",
            s3_key="blank-forms/aetna-pa.pdf",
            fields=fields,
            relevance_score=0.92,
        )
        assert len(meta.fields) == 2
        assert meta.fields[0].field_name == "patient_name"
        assert meta.relevance_score == 0.92

    def test_serialization(self):
        meta = FormMetadata(
            form_id="FORM-004",
            title="BCBS PA Form",
            description="Blue Cross Blue Shield PA",
            s3_key="blank-forms/bcbs-pa.pdf",
            fields=[
                FormField(
                    field_name="rx_name",
                    field_type=FieldType.TEXT,
                    description="Medication name",
                ),
            ],
            relevance_score=0.85,
        )
        data = meta.model_dump()
        assert data["form_id"] == "FORM-004"
        assert len(data["fields"]) == 1
        assert data["fields"][0]["field_name"] == "rx_name"
        assert data["relevance_score"] == 0.85

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            FormMetadata(
                form_id="FORM-005",
                title="Incomplete",
                # description omitted
                s3_key="blank-forms/x.pdf",
            )
