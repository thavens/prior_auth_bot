"""Step 5 -- Document Population Handler.

Downloads a blank PA form from S3, extracts its fields, uses the LLM to
fill them based on patient data, treatment info, and memories, then uploads
the completed PDF and creates a tracking record in DynamoDB.
"""

from __future__ import annotations

import logging
import uuid
import time
from typing import Any

from shared.bedrock_client import BedrockClient
from shared.config import Config
from shared.dynamo_client import DynamoClient
from shared.models import FormMetadata, PARequest, Patient, Treatment
from shared.pdf_utils import PDFFormReader, PDFFormWriter
from shared.s3_client import S3Client

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

cfg = Config()
bedrock = BedrockClient()
dynamo = DynamoClient()
s3 = S3Client()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Fill a blank PA form with LLM-generated values and upload the result.

    Event keys:
        treatment            -- serialized Treatment
        patient              -- serialized Patient
        selected_form        -- serialized FormMetadata
        memories             -- list of memory dicts from memory search
        improvement_context  -- (optional) list of improvement strings from
                                prior rejection analysis
    """

    treatment = Treatment(**event["treatment"])
    patient = Patient(**event["patient"])
    selected_form = FormMetadata(**event["selected_form"])
    memories: list[dict[str, Any]] = event.get("memories", [])
    improvement_context: list[str] = event.get("improvement_context", [])

    # -----------------------------------------------------------------
    # Download blank PDF from S3
    # -----------------------------------------------------------------
    logger.info("Downloading blank form: %s", selected_form.s3_key)
    blank_pdf_bytes = s3.read_bytes(selected_form.s3_key)

    # -----------------------------------------------------------------
    # Extract form fields from the PDF
    # -----------------------------------------------------------------
    form_fields = PDFFormReader.extract_fields(blank_pdf_bytes)
    logger.info("Extracted %d form fields", len(form_fields))

    # -----------------------------------------------------------------
    # Use LLM to generate field values
    # -----------------------------------------------------------------
    fields_as_dicts = [f.model_dump() for f in form_fields]
    field_values = bedrock.fill_form_fields(
        form_fields=fields_as_dicts,
        treatment=treatment,
        patient=patient,
        memories=memories,
        improvement_context=improvement_context,
    )
    logger.info("LLM generated values for %d fields", len(field_values))

    # -----------------------------------------------------------------
    # Fill the PDF and generate a traceable label
    # -----------------------------------------------------------------
    filled_pdf_bytes = PDFFormWriter.fill_fields(blank_pdf_bytes, field_values)

    treatment_code = treatment.rxnorm_code or treatment.name
    label = PDFFormWriter.generate_label(patient.patient_id, treatment_code)
    filled_s3_key = f"{cfg.FILLED_FORMS_PREFIX}/{label}"

    # -----------------------------------------------------------------
    # Upload filled PDF to S3
    # -----------------------------------------------------------------
    logger.info("Uploading filled form to s3://%s/%s", cfg.DATA_BUCKET, filled_s3_key)
    s3.write_bytes(filled_s3_key, filled_pdf_bytes, content_type="application/pdf")

    # -----------------------------------------------------------------
    # Create a PARequest tracking record in DynamoDB
    # -----------------------------------------------------------------
    pa_request_id = str(uuid.uuid4())
    pa_request = PARequest(
        pa_request_id=pa_request_id,
        patient_id=patient.patient_id,
        treatment=treatment,
        provider_id=patient.insurance_provider,
        form_id=selected_form.form_id,
        filled_form_s3_key=filled_s3_key,
        status="PENDING",
        attempt_number=event.get("attempt_number", 1),
        improvement_context=improvement_context,
        submitted_at=time.time(),
    )

    dynamo.put_tracking(cfg.TRACKING_TABLE, pa_request)
    logger.info("Created tracking record: %s", pa_request_id)

    return {
        "pa_request_id": pa_request_id,
        "filled_form_s3_key": filled_s3_key,
        "treatment": treatment.model_dump(),
        "patient": patient.model_dump(),
    }
