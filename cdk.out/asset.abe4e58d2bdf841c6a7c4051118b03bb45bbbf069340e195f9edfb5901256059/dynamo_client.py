"""DynamoDB client for caching, tracking, and memories."""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import boto3
from boto3.dynamodb.conditions import Key

from shared.config import cfg
from shared.models import Memory, PARequest

logger = logging.getLogger(__name__)

_DAY_SECONDS = 86_400


class DynamoClient:
    """Convenience wrapper around DynamoDB for the PA Bot tables."""

    def __init__(self, region: Optional[str] = None) -> None:
        self._region = region or cfg.AWS_REGION
        self._resource = boto3.resource("dynamodb", region_name=self._region)

    def _table(self, table_name: str):
        return self._resource.Table(table_name)

    # ------------------------------------------------------------------
    # Cache table
    # ------------------------------------------------------------------

    def get_cache(
        self,
        table_name: str,
        provider_id: str,
        treatment_code: str,
    ) -> Optional[dict[str, Any]]:
        """Retrieve a cached PA-requirement lookup, respecting TTL.

        Returns ``None`` if the item does not exist or has expired.
        """

        try:
            response = self._table(table_name).get_item(
                Key={
                    "provider_id": provider_id,
                    "treatment_code": treatment_code,
                }
            )
        except Exception:
            logger.exception("get_cache failed for %s/%s", provider_id, treatment_code)
            raise

        item = response.get("Item")
        if item is None:
            return None

        # Honour the TTL even if DynamoDB hasn't garbage-collected yet.
        ttl = item.get("ttl", 0)
        if ttl and time.time() > ttl:
            logger.debug("Cache item expired for %s/%s", provider_id, treatment_code)
            return None

        return item.get("data")

    def put_cache(
        self,
        table_name: str,
        provider_id: str,
        treatment_code: str,
        data: dict[str, Any],
        ttl_days: int = 7,
    ) -> None:
        """Store a PA-requirement lookup result with a TTL."""

        ttl = int(time.time()) + ttl_days * _DAY_SECONDS

        try:
            self._table(table_name).put_item(
                Item={
                    "provider_id": provider_id,
                    "treatment_code": treatment_code,
                    "data": data,
                    "ttl": ttl,
                    "cached_at": int(time.time()),
                }
            )
        except Exception:
            logger.exception("put_cache failed for %s/%s", provider_id, treatment_code)
            raise

    # ------------------------------------------------------------------
    # Tracking table
    # ------------------------------------------------------------------

    def get_tracking(
        self,
        table_name: str,
        pa_request_id: str,
    ) -> Optional[dict[str, Any]]:
        """Retrieve a PA request tracking record."""

        try:
            response = self._table(table_name).get_item(
                Key={"pa_request_id": pa_request_id}
            )
        except Exception:
            logger.exception("get_tracking failed for %s", pa_request_id)
            raise

        return response.get("Item")

    def put_tracking(
        self,
        table_name: str,
        pa_request: PARequest,
    ) -> None:
        """Write a full PA request tracking record from a PARequest model."""

        item = pa_request.model_dump()
        # Ensure nested Pydantic models are serialised as plain dicts.
        # model_dump() already handles this, but we convert enums to strings.
        item["treatment"]["treatment_type"] = pa_request.treatment.treatment_type.value

        try:
            self._table(table_name).put_item(Item=self._sanitize_for_dynamo(item))
        except Exception:
            logger.exception("put_tracking failed for %s", pa_request.pa_request_id)
            raise

    def update_tracking_status(
        self,
        table_name: str,
        pa_request_id: str,
        status: str,
        **extra_attrs: Any,
    ) -> None:
        """Update the status (and optionally other attributes) of a tracking record."""

        expr_names = {"#s": "status"}
        expr_values: dict[str, Any] = {":s": status}
        update_parts = ["#s = :s"]

        for idx, (attr_name, attr_value) in enumerate(extra_attrs.items()):
            placeholder_name = f"#a{idx}"
            placeholder_value = f":v{idx}"
            expr_names[placeholder_name] = attr_name
            expr_values[placeholder_value] = attr_value
            update_parts.append(f"{placeholder_name} = {placeholder_value}")

        update_expr = "SET " + ", ".join(update_parts)

        try:
            self._table(table_name).update_item(
                Key={"pa_request_id": pa_request_id},
                UpdateExpression=update_expr,
                ExpressionAttributeNames=expr_names,
                ExpressionAttributeValues=self._sanitize_for_dynamo(expr_values),
            )
        except Exception:
            logger.exception(
                "update_tracking_status failed for %s -> %s", pa_request_id, status
            )
            raise

    # ------------------------------------------------------------------
    # Memories table
    # ------------------------------------------------------------------

    def put_memory(
        self,
        table_name: str,
        memory: Memory,
    ) -> None:
        """Write a Memory model instance to the memories table."""

        item = memory.model_dump()
        item["memory_type"] = memory.memory_type.value

        try:
            self._table(table_name).put_item(Item=self._sanitize_for_dynamo(item))
        except Exception:
            logger.exception("put_memory failed for %s", memory.memory_id)
            raise

    def query_memories_by_type(
        self,
        table_name: str,
        memory_type: str,
        index_name: Optional[str] = None,
        key_name: Optional[str] = None,
        key_value: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Query memories filtered by type and an optional secondary key.

        If ``index_name`` is provided the query runs against that GSI.
        ``key_name`` / ``key_value`` add a sort-key or filter-key condition.
        """

        table = self._table(table_name)

        kwargs: dict[str, Any] = {}
        if index_name:
            kwargs["IndexName"] = index_name

        key_condition = Key("memory_type").eq(memory_type)
        if key_name and key_value:
            key_condition = key_condition & Key(key_name).eq(key_value)

        kwargs["KeyConditionExpression"] = key_condition

        try:
            response = table.query(**kwargs)
            return response.get("Items", [])
        except Exception:
            logger.exception(
                "query_memories_by_type failed for type=%s key=%s",
                memory_type,
                key_name,
            )
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @classmethod
    def _sanitize_for_dynamo(cls, obj: Any) -> Any:
        """Recursively convert Python floats and other types into
        DynamoDB-compatible representations.

        DynamoDB does not accept ``float('inf')``, ``float('nan')``, or bare
        ``None`` inside maps.  We also convert ``float`` to ``Decimal`` is not
        strictly needed when using the resource API, but this keeps items
        clean.
        """

        if isinstance(obj, dict):
            return {k: cls._sanitize_for_dynamo(v) for k, v in obj.items() if v is not None}
        if isinstance(obj, list):
            return [cls._sanitize_for_dynamo(v) for v in obj]
        if isinstance(obj, float):
            from decimal import Decimal
            return Decimal(str(obj))
        return obj
