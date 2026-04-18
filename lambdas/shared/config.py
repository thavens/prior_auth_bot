"""Centralized configuration loaded from environment variables with sensible defaults."""

from __future__ import annotations

import os


class Config:
    """Reads all configuration from environment variables.

    Instantiate once at module level in each Lambda handler and pass around
    via dependency injection.  Every attribute has a default so local testing
    works without a full environment.
    """

    def __init__(self) -> None:
        # S3 ----------------------------------------------------------------
        self.DATA_BUCKET: str = os.environ.get("DATA_BUCKET", "")
        self.TRANSCRIPTS_PREFIX: str = os.environ.get("TRANSCRIPTS_PREFIX", "transcripts")
        self.PATIENT_DATA_PREFIX: str = os.environ.get("PATIENT_DATA_PREFIX", "patient-data")
        self.BLANK_FORMS_PREFIX: str = os.environ.get("BLANK_FORMS_PREFIX", "blank-forms")
        self.FILLED_FORMS_PREFIX: str = os.environ.get("FILLED_FORMS_PREFIX", "filled-forms")

        # DynamoDB -----------------------------------------------------------
        self.CACHE_TABLE: str = os.environ.get("CACHE_TABLE", "")
        self.MEMORIES_TABLE: str = os.environ.get("MEMORIES_TABLE", "")
        self.TRACKING_TABLE: str = os.environ.get("TRACKING_TABLE", "")

        # OpenSearch ---------------------------------------------------------
        self.OPENSEARCH_ENDPOINT: str = os.environ.get("OPENSEARCH_ENDPOINT", "")
        self.FORMS_INDEX: str = os.environ.get("FORMS_INDEX", "blank-forms")
        self.MEMORIES_INDEX: str = os.environ.get("MEMORIES_INDEX", "memories")

        # Bedrock ------------------------------------------------------------
        self.BEDROCK_MODEL_ID: str = os.environ.get(
            "BEDROCK_MODEL_ID",
            "anthropic.claude-sonnet-4-5-20250929-v1:0",
        )
        self.BEDROCK_EMBED_MODEL_ID: str = os.environ.get(
            "BEDROCK_EMBED_MODEL_ID",
            "amazon.titan-embed-text-v2:0",
        )

        # SES ----------------------------------------------------------------
        self.SES_FROM_EMAIL: str = os.environ.get("SES_FROM_EMAIL", "")
        self.SES_TO_EMAIL: str = os.environ.get("SES_TO_EMAIL", "")

        # SNS / Step Functions -----------------------------------------------
        self.SNS_TOPIC_ARN: str = os.environ.get("SNS_TOPIC_ARN", "")
        self.STATE_MACHINE_ARN: str = os.environ.get("STATE_MACHINE_ARN", "")

        # Self-improvement ---------------------------------------------------
        self.MAX_SELF_IMPROVEMENT_ATTEMPTS: int = int(
            os.environ.get("MAX_SELF_IMPROVEMENT_ATTEMPTS", "3")
        )

        # AWS ----------------------------------------------------------------
        self.AWS_REGION: str = os.environ.get("AWS_REGION", "us-east-1")


# Module-level singleton so callers can simply ``from shared.config import cfg``.
cfg = Config()
