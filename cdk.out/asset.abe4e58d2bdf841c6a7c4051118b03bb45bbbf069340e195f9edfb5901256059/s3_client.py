"""S3 client for reading and writing prior-authorization artefacts."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import boto3

from shared.config import cfg

logger = logging.getLogger(__name__)


class S3Client:
    """Thin wrapper around boto3 S3 for the PA Bot data bucket."""

    def __init__(
        self,
        bucket: Optional[str] = None,
        region: Optional[str] = None,
    ) -> None:
        self._bucket = bucket or cfg.DATA_BUCKET
        self._region = region or cfg.AWS_REGION
        self._client = boto3.client("s3", region_name=self._region)

    # ------------------------------------------------------------------
    # JSON helpers
    # ------------------------------------------------------------------

    def read_json(self, key: str) -> dict[str, Any]:
        """Download a JSON object from S3 and return it as a dict."""

        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            body = response["Body"].read()
            return json.loads(body)
        except Exception:
            logger.exception("read_json failed for s3://%s/%s", self._bucket, key)
            raise

    def write_json(self, key: str, data: Any) -> None:
        """Serialize ``data`` to JSON and upload to S3."""

        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=json.dumps(data, default=str).encode("utf-8"),
                ContentType="application/json",
            )
        except Exception:
            logger.exception("write_json failed for s3://%s/%s", self._bucket, key)
            raise

    # ------------------------------------------------------------------
    # Raw byte helpers
    # ------------------------------------------------------------------

    def read_bytes(self, key: str) -> bytes:
        """Download raw bytes from S3."""

        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()
        except Exception:
            logger.exception("read_bytes failed for s3://%s/%s", self._bucket, key)
            raise

    def write_bytes(
        self,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> None:
        """Upload raw bytes to S3."""

        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
        except Exception:
            logger.exception("write_bytes failed for s3://%s/%s", self._bucket, key)
            raise

    # ------------------------------------------------------------------
    # Presigned URLs
    # ------------------------------------------------------------------

    def generate_presigned_url(self, key: str, expiration: int = 3600) -> str:
        """Generate a presigned GET URL for an S3 object.

        ``expiration`` is in seconds (default 1 hour).
        """

        try:
            url = self._client.generate_presigned_url(
                ClientMethod="get_object",
                Params={"Bucket": self._bucket, "Key": key},
                ExpiresIn=expiration,
            )
            return url
        except Exception:
            logger.exception(
                "generate_presigned_url failed for s3://%s/%s", self._bucket, key
            )
            raise

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    def list_objects(self, prefix: str) -> list[str]:
        """List all object keys under a given prefix.

        Uses the paginator to handle prefixes with more than 1 000 keys.
        """

        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")

        try:
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    keys.append(obj["Key"])
        except Exception:
            logger.exception(
                "list_objects failed for s3://%s/%s", self._bucket, prefix
            )
            raise

        return keys
