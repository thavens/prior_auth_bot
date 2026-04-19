import uuid
from datetime import datetime, timezone
from decimal import Decimal

from boto3.dynamodb.conditions import Key

from prior_auth_bot.models import PatientCreateInput


class PatientService:
    def __init__(self, dynamodb_resource, table_name: str):
        self.table = dynamodb_resource.Table(table_name)

    def get(self, patient_id: str) -> dict:
        response = self.table.get_item(Key={"patient_id": patient_id})
        item = response.get("Item")
        if not item:
            raise ValueError(f"Patient {patient_id} not found")
        return item

    def list_by_physician(self, physician_id: str) -> list[dict]:
        response = self.table.query(
            IndexName="by_physician",
            KeyConditionExpression=Key("primary_physician_id").eq(physician_id),
        )
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

    def create(self, physician_id: str, data: PatientCreateInput) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        patient_id = f"pat_{uuid.uuid4().hex[:8]}"
        item = {
            "patient_id": patient_id,
            "first_name": data.first_name,
            "last_name": data.last_name,
            "dob": data.dob,
            "insurance_provider": data.insurance_provider,
            "insurance_id": data.insurance_id,
            "address": data.address,
            "phone": data.phone,
            "primary_physician_id": physician_id,
            "created_at": now,
            "updated_at": now,
        }
        self.table.put_item(Item=item)
        return item
