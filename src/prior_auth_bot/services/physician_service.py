from boto3.dynamodb.conditions import Key


class PhysicianService:
    def __init__(self, dynamodb_resource, table_name: str):
        self.table = dynamodb_resource.Table(table_name)

    def get(self, physician_id: str) -> dict:
        response = self.table.get_item(Key={"physician_id": physician_id})
        item = response.get("Item")
        if not item:
            raise ValueError(f"Physician {physician_id} not found")
        return item

    def list_all(self) -> list[dict]:
        response = self.table.scan()
        return response.get("Items", [])

    def search_by_name(self, last_name: str, first_name: str | None = None) -> list[dict]:
        if first_name:
            response = self.table.query(
                IndexName="by_name",
                KeyConditionExpression=Key("last_name").eq(last_name) & Key("first_name").begins_with(first_name),
            )
        else:
            response = self.table.query(
                IndexName="by_name",
                KeyConditionExpression=Key("last_name").eq(last_name),
            )
        return response.get("Items", [])

    def get_by_npi(self, npi: str) -> dict | None:
        response = self.table.query(
            IndexName="by_npi",
            KeyConditionExpression=Key("npi").eq(npi),
        )
        items = response.get("Items", [])
        return items[0] if items else None
