import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        disconnected = []
        for conn in self.active_connections:
            try:
                await conn.send_json(message)
            except Exception:
                disconnected.append(conn)
        for conn in disconnected:
            self.active_connections.remove(conn)


manager = ConnectionManager()


def create_ws_router() -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/pa-status")
    async def pa_status_ws(websocket: WebSocket):
        await manager.connect(websocket)
        settings = websocket.app.state.settings
        dynamodb = websocket.app.state.dynamodb_resource

        try:
            poll_task = asyncio.create_task(
                _poll_streams(settings, dynamodb)
            )

            while True:
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                except asyncio.TimeoutError:
                    await websocket.send_json({"type": "heartbeat", "timestamp": datetime.now(timezone.utc).isoformat()})
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    return router


async def _poll_streams(settings, dynamodb):
    import boto3

    try:
        streams_client = boto3.client("dynamodbstreams", region_name=settings.aws_region)
        table = dynamodb.Table(settings.pa_requests_table)
        table_desc = table.meta.client.describe_table(TableName=settings.pa_requests_table)
        stream_arn = table_desc["Table"].get("LatestStreamArn")

        if not stream_arn:
            logger.warning("No DynamoDB Stream found on pa_requests table")
            return

        stream_desc = streams_client.describe_stream(StreamArn=stream_arn)
        shards = stream_desc["StreamDescription"]["Shards"]

        if not shards:
            return

        shard_iterators = []
        for shard in shards:
            resp = streams_client.get_shard_iterator(
                StreamArn=stream_arn,
                ShardId=shard["ShardId"],
                ShardIteratorType="LATEST",
            )
            shard_iterators.append(resp["ShardIterator"])

        while True:
            for i, iterator in enumerate(shard_iterators):
                if not iterator:
                    continue
                try:
                    records_response = streams_client.get_records(ShardIterator=iterator, Limit=100)
                    shard_iterators[i] = records_response.get("NextShardIterator")

                    for record in records_response.get("Records", []):
                        if record["eventName"] in ("INSERT", "MODIFY"):
                            new_image = record.get("dynamodb", {}).get("NewImage", {})
                            from boto3.dynamodb.types import TypeDeserializer
                            deserializer = TypeDeserializer()
                            item = {k: deserializer.deserialize(v) for k, v in new_image.items()}

                            await manager.broadcast({
                                "type": "status_update",
                                "pa_request_id": item.get("pa_request_id"),
                                "status": item.get("status"),
                                "updated_at": item.get("updated_at"),
                                "patient_name": f"{item.get('patient', {}).get('first_name', '')} {item.get('patient', {}).get('last_name', '')}".strip(),
                            })
                except Exception as e:
                    logger.error(f"Stream polling error: {e}")

            await asyncio.sleep(1)

    except Exception as e:
        logger.error(f"Stream setup error: {e}")
