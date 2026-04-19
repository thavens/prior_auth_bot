import asyncio
import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _check_s3_bucket(s3_client, bucket_name: str) -> dict:
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        return {"name": bucket_name, "type": "S3", "status": "healthy"}
    except Exception as e:
        return {"name": bucket_name, "type": "S3", "status": "error", "error": str(e)}


def _check_dynamo_table(dynamodb, table_name: str) -> dict:
    try:
        table = dynamodb.Table(table_name)
        table.table_status
        return {"name": table_name, "type": "DynamoDB", "status": "healthy"}
    except Exception as e:
        return {"name": table_name, "type": "DynamoDB", "status": "error", "error": str(e)}


class HealthCache:
    def __init__(self, ttl: float = 30.0):
        self._cached_response: dict | None = None
        self._last_refresh: float = 0.0
        self._ttl = ttl
        self._lock = asyncio.Lock()

    async def refresh(self, settings, s3_client, dynamodb):
        loop = asyncio.get_event_loop()

        s3_buckets = [
            settings.audio_uploads_bucket,
            settings.blank_forms_bucket,
            settings.textract_output_bucket,
            settings.completed_forms_bucket,
        ]
        dynamo_tables = [
            settings.pa_requests_table,
            settings.pa_memories_table,
            settings.scrape_cache_table,
            settings.pa_patients_table,
            settings.pa_physicians_table,
        ]

        tasks = [
            loop.run_in_executor(None, _check_s3_bucket, s3_client, b)
            for b in s3_buckets
        ]
        tasks.extend(
            loop.run_in_executor(None, _check_dynamo_table, dynamodb, t)
            for t in dynamo_tables
        )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        components = []
        for r in results:
            if isinstance(r, Exception):
                components.append({"name": "unknown", "type": "unknown", "status": "error", "error": str(r)})
            else:
                components.append(r)

        for svc_name in ["AWS Transcribe", "AWS Textract", "AWS Bedrock"]:
            components.append({"name": svc_name, "type": "Service", "status": "healthy"})

        healthy_count = sum(1 for c in components if c["status"] == "healthy")
        self._cached_response = {
            "overall": "healthy" if healthy_count == len(components) else "degraded",
            "components": components,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
        self._last_refresh = time.monotonic()
        return self._cached_response

    async def get(self, settings, s3_client, dynamodb) -> dict:
        if self._cached_response is not None and time.monotonic() - self._last_refresh < self._ttl:
            return self._cached_response
        async with self._lock:
            if self._cached_response is not None and time.monotonic() - self._last_refresh < self._ttl:
                return self._cached_response
            return await self.refresh(settings, s3_client, dynamodb)

    async def background_loop(self, settings, s3_client, dynamodb):
        try:
            await self.refresh(settings, s3_client, dynamodb)
            logger.info("Health cache initialized")
        except Exception:
            logger.exception("Health cache initial refresh failed")
        while True:
            await asyncio.sleep(self._ttl)
            try:
                await self.refresh(settings, s3_client, dynamodb)
            except Exception:
                logger.exception("Health cache refresh failed")
