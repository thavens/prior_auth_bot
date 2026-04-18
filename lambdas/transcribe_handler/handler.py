"""Step 0 -- Transcribe audio and kick off the PA pipeline.

Triggered by an S3 event when audio is uploaded to the recordings/ prefix.
Starts an Amazon Transcribe job, polls until complete, then launches the
Step Functions state machine with the transcript location.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import boto3

from shared.config import Config

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

cfg = Config()

transcribe_client = boto3.client("transcribe", region_name=cfg.AWS_REGION)
sfn_client = boto3.client("stepfunctions", region_name=cfg.AWS_REGION)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SANITIZE_RE = re.compile(r"[^0-9a-zA-Z._-]")
_MAX_JOB_NAME_LEN = 200


def _sanitize_job_name(raw: str) -> str:
    """Produce a Transcribe-safe job name from an S3 key.

    Transcribe job names must match ``[0-9a-zA-Z._-]+`` and be at most 200
    characters.
    """
    sanitized = _SANITIZE_RE.sub("-", raw)
    # Ensure uniqueness by appending a short epoch suffix.
    suffix = f"-{int(time.time())}"
    max_base = _MAX_JOB_NAME_LEN - len(suffix)
    return sanitized[:max_base] + suffix


# ---------------------------------------------------------------------------
# Lambda handler
# ---------------------------------------------------------------------------


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Handle an S3 PutObject event for audio uploads."""

    record = event["Records"][0]
    bucket = record["s3"]["bucket"]["name"]
    key = record["s3"]["object"]["key"]

    logger.info("Received audio upload: s3://%s/%s", bucket, key)

    job_name = _sanitize_job_name(key)
    media_uri = f"s3://{bucket}/{key}"
    output_key = f"{cfg.TRANSCRIPTS_PREFIX}/{job_name}.json"

    # --- Start Transcribe job ---------------------------------------------
    transcribe_client.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": media_uri},
        MediaFormat=key.rsplit(".", 1)[-1] if "." in key else "wav",
        LanguageCode="en-US",
        OutputBucketName=cfg.DATA_BUCKET,
        OutputKey=output_key,
        Settings={
            "ShowSpeakerLabels": True,
            "MaxSpeakerLabels": 2,
        },
    )

    logger.info("Started transcription job: %s", job_name)

    # --- Poll for completion ----------------------------------------------
    max_iterations = 60
    for _ in range(max_iterations):
        resp = transcribe_client.get_transcription_job(
            TranscriptionJobName=job_name,
        )
        status = resp["TranscriptionJob"]["TranscriptionJobStatus"]

        if status == "COMPLETED":
            logger.info("Transcription job %s completed", job_name)
            break
        elif status == "FAILED":
            reason = resp["TranscriptionJob"].get("FailureReason", "unknown")
            raise RuntimeError(
                f"Transcription job {job_name} failed: {reason}"
            )
        else:
            time.sleep(5)
    else:
        raise TimeoutError(
            f"Transcription job {job_name} did not complete within "
            f"{max_iterations * 5} seconds"
        )

    # The transcript S3 key is the OutputKey we specified.
    transcript_s3_key = output_key

    # Derive a patient data key.  For the hackathon we default to a known
    # sample file; a production system would look this up from metadata.
    patient_data_s3_key = f"{cfg.PATIENT_DATA_PREFIX}/patient_001.json"

    # --- Start the Step Functions pipeline ---------------------------------
    execution_input = json.dumps({
        "transcript_s3_key": transcript_s3_key,
        "patient_data_s3_key": patient_data_s3_key,
    })

    execution_resp = sfn_client.start_execution(
        stateMachineArn=cfg.STATE_MACHINE_ARN,
        name=f"pa-pipeline-{job_name}",
        input=execution_input,
    )

    execution_arn = execution_resp["executionArn"]
    logger.info("Started Step Functions execution: %s", execution_arn)

    return {
        "statusCode": 200,
        "transcription_job_name": job_name,
        "transcript_s3_key": transcript_s3_key,
        "execution_arn": execution_arn,
    }
