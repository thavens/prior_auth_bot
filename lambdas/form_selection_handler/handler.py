"""Step 3 -- Select the best PA form for a treatment.

Invoked by Step Functions (typically inside a Map state) with a single
treatment that requires PA and the patient data.  Uses vector search over
the blank-forms index in OpenSearch, then asks Bedrock to pick the best
candidate.
"""

from __future__ import annotations

import logging
from typing import Any

from shared.config import Config
from shared.models import Patient, Treatment
from shared.bedrock_client import BedrockClient
from shared.opensearch_client import OpenSearchClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

cfg = Config()

bedrock = BedrockClient()
opensearch = OpenSearchClient()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Select the most appropriate blank PA form for a treatment.

    Expected event (from a Map state iterating over pa_required_treatments)::

        {
            "treatment": { ... },
            "patient": { ... },
            ... (additional fields like pa_required, requirements_text are
                 passed through but not consumed here)
        }
    """

    treatment_data: dict[str, Any] = event["treatment"]
    patient_data: dict[str, Any] = event["patient"]

    treatment = Treatment(**treatment_data)
    patient = Patient(**patient_data)

    logger.info(
        "Selecting form for treatment '%s' (id=%s), patient=%s",
        treatment.name,
        treatment.treatment_id,
        patient.patient_id,
    )

    # --- Build a rich description for embedding ----------------------------
    description_parts = [
        f"Treatment: {treatment.name}",
        f"Type: {treatment.treatment_type.value}",
        f"Insurance provider: {patient.insurance_provider}",
    ]
    if treatment.rxnorm_code:
        description_parts.append(f"RxNorm: {treatment.rxnorm_code}")
    if treatment.snomed_code:
        description_parts.append(f"SNOMED: {treatment.snomed_code}")
    if treatment.icd10_codes:
        description_parts.append(f"ICD-10: {', '.join(treatment.icd10_codes)}")
    if treatment.dosage:
        description_parts.append(f"Dosage: {treatment.dosage}")

    description_text = ". ".join(description_parts)
    logger.info("Embedding text: %s", description_text)

    # --- Generate embedding ------------------------------------------------
    embedding = bedrock.generate_embedding(description_text)

    # --- Search OpenSearch for candidate forms -----------------------------
    candidates = opensearch.search_forms(
        query_embedding=embedding,
        top_k=5,
    )

    if not candidates:
        raise ValueError(
            f"No candidate forms found for treatment '{treatment.name}'. "
            "Ensure the blank-forms index has been populated."
        )

    logger.info("Found %d candidate form(s)", len(candidates))

    # --- Ask Bedrock to pick the best form ---------------------------------
    selected_form_id = bedrock.select_form(
        treatment=treatment,
        candidate_forms=candidates,
        patient=patient,
    )

    # Find the full metadata for the selected form.
    selected_form: dict[str, Any] | None = None
    for candidate in candidates:
        if candidate.get("form_id") == selected_form_id:
            selected_form = {
                "form_id": candidate["form_id"],
                "s3_key": candidate.get("s3_key", ""),
                "title": candidate.get("title", ""),
            }
            break

    if selected_form is None:
        # Bedrock returned an ID that does not match any candidate.  Fall back
        # to the top-scoring result from the vector search.
        logger.warning(
            "Bedrock selected form_id '%s' not found in candidates; "
            "falling back to top vector-search result",
            selected_form_id,
        )
        top = candidates[0]
        selected_form = {
            "form_id": top.get("form_id", ""),
            "s3_key": top.get("s3_key", ""),
            "title": top.get("title", ""),
        }

    logger.info(
        "Selected form: %s (%s)",
        selected_form["form_id"],
        selected_form["title"],
    )

    return {
        "treatment": treatment_data,
        "patient": patient_data,
        "selected_form": selected_form,
    }
