"""Step 1 -- Extract medical entities from a transcript.

Invoked by Step Functions with the S3 keys for the transcript and patient
data.  Uses Amazon Comprehend Medical to pull structured treatments from
the free-text transcript.
"""

from __future__ import annotations

import logging
from typing import Any

from shared.config import Config
from shared.comprehend_medical import ComprehendMedicalClient
from shared.s3_client import S3Client

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

cfg = Config()

s3 = S3Client()
comprehend = ComprehendMedicalClient()


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Extract treatments and patient data from S3 artefacts.

    Expected event::

        {
            "transcript_s3_key": "transcripts/...",
            "patient_data_s3_key": "patient-data/..."
        }
    """

    transcript_s3_key: str = event["transcript_s3_key"]
    patient_data_s3_key: str = event["patient_data_s3_key"]

    logger.info(
        "Extracting entities -- transcript: %s, patient: %s",
        transcript_s3_key,
        patient_data_s3_key,
    )

    # --- Read transcript from S3 ------------------------------------------
    transcript_json = s3.read_json(transcript_s3_key)

    # Amazon Transcribe output nests the text under results.transcripts[0].transcript
    transcript_text: str = (
        transcript_json
        .get("results", {})
        .get("transcripts", [{}])[0]
        .get("transcript", "")
    )

    if not transcript_text:
        raise ValueError(
            f"No transcript text found in {transcript_s3_key}. "
            "Ensure the Transcribe job completed successfully."
        )

    logger.info("Transcript length: %d characters", len(transcript_text))

    # --- Read patient data from S3 ----------------------------------------
    patient_data: dict[str, Any] = s3.read_json(patient_data_s3_key)

    logger.info("Loaded patient data for: %s", patient_data.get("name", "unknown"))

    # --- Extract treatments via Comprehend Medical -------------------------
    treatments = comprehend.text_to_treatments(transcript_text)

    logger.info("Extracted %d treatment(s)", len(treatments))

    return {
        "treatments": [t.model_dump() for t in treatments],
        "patient": patient_data,
        "transcript_text": transcript_text,
    }
