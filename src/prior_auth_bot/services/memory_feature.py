from datetime import datetime, timezone

from boto3.dynamodb.conditions import Attr, Key

from prior_auth_bot.models import Memory


class MemoryFeatureService:
    def __init__(self, dynamodb_resource, table_name: str):
        self.table = dynamodb_resource.Table(table_name)

    def save_memory(self, memory: Memory) -> str:
        item = memory.model_dump(exclude={"relevance_score"})
        if not item.get("embedding"):
            item.pop("embedding", None)
        item["provider_treatment"] = f"{memory.provider}#{memory.treatment}"
        self.table.put_item(Item=item)
        return memory.memory_id

    def get_memory(self, memory_type: str, memory_id: str) -> Memory | None:
        response = self.table.get_item(Key={"memory_type": memory_type, "memory_id": memory_id})
        item = response.get("Item")
        if not item:
            return None
        item.pop("provider_treatment", None)
        return Memory(**item)

    def query_by_provider(self, provider: str, limit: int = 10) -> list[Memory]:
        response = self.table.query(
            IndexName="gsi-provider-created",
            KeyConditionExpression=Key("provider").eq(provider),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [Memory(**{k: v for k, v in item.items() if k != "provider_treatment"}) for item in response["Items"]]

    def query_by_treatment(self, treatment: str, limit: int = 10) -> list[Memory]:
        response = self.table.query(
            IndexName="gsi-treatment-created",
            KeyConditionExpression=Key("treatment").eq(treatment),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [Memory(**{k: v for k, v in item.items() if k != "provider_treatment"}) for item in response["Items"]]

    def query_by_provider_treatment(self, provider: str, treatment: str, limit: int = 10) -> list[Memory]:
        composite_key = f"{provider}#{treatment}"
        response = self.table.query(
            IndexName="gsi-provider-treatment-success",
            KeyConditionExpression=Key("provider_treatment").eq(composite_key),
            ScanIndexForward=False,
            Limit=limit,
        )
        return [Memory(**{k: v for k, v in item.items() if k != "provider_treatment"}) for item in response["Items"]]

    def update_success_count(self, memory_type: str, memory_id: str, increment: int = 1) -> None:
        self.table.update_item(
            Key={"memory_type": memory_type, "memory_id": memory_id},
            UpdateExpression="SET success_count = success_count + :inc",
            ExpressionAttributeValues={":inc": increment},
        )

    def scan_all_with_embeddings(self) -> list[Memory]:
        items: list[dict] = []
        response = self.table.scan(FilterExpression=Attr("embedding").exists())
        items.extend(response.get("Items", []))
        while "LastEvaluatedKey" in response:
            response = self.table.scan(
                FilterExpression=Attr("embedding").exists(),
                ExclusiveStartKey=response["LastEvaluatedKey"],
            )
            items.extend(response.get("Items", []))
        return [Memory(**{k: v for k, v in item.items() if k != "provider_treatment"}) for item in items]

    def increment_success_count(self, memory_type: str, memory_id: str) -> None:
        self.table.update_item(
            Key={"memory_type": memory_type, "memory_id": memory_id},
            UpdateExpression="SET success_count = success_count + :inc, updated_at = :ts",
            ExpressionAttributeValues={
                ":inc": 1,
                ":ts": datetime.now(timezone.utc).isoformat(),
            },
        )

    def delete_memory(self, memory_type: str, memory_id: str) -> None:
        self.table.delete_item(Key={"memory_type": memory_type, "memory_id": memory_id})
