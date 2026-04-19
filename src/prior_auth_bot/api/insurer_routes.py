from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from prior_auth_bot.models import InsurerDecision

logger = logging.getLogger(__name__)


def create_insurer_router() -> APIRouter:
    router = APIRouter()

    @router.get("/insurer/queue")
    async def get_insurer_queue(request: Request):
        pa_table = request.app.state.dynamodb_resource.Table(request.app.state.settings.pa_requests_table)
        response = pa_table.scan(
            FilterExpression="#s = :status1 OR #s = :status2",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":status1": "pending_insurer_review",
                ":status2": "step_7_outcome_handling",
            },
        )
        items = response.get("Items", [])

        queue = []
        for item in items:
            queue.append({
                "pa_request_id": item.get("pa_request_id"),
                "status": item.get("status"),
                "patient_name": f"{item.get('patient', {}).get('first_name', '')} {item.get('patient', {}).get('last_name', '')}".strip(),
                "physician_name": f"{item.get('physician', {}).get('first_name', '')} {item.get('physician', {}).get('last_name', '')}".strip(),
                "insurance_provider": item.get("patient", {}).get("insurance_provider", ""),
                "treatment_text": _extract_treatment_text(item),
                "created_at": item.get("created_at", ""),
                "attempt_number": item.get("attempt_number", 1),
            })

        return {"queue": queue}

    @router.get("/insurer/pa-requests/{pa_request_id}")
    async def get_insurer_pa_request(pa_request_id: str, request: Request):
        pa_table = request.app.state.dynamodb_resource.Table(request.app.state.settings.pa_requests_table)
        response = pa_table.get_item(Key={"pa_request_id": pa_request_id})
        item = response.get("Item")
        if not item:
            raise HTTPException(status_code=404, detail="PA request not found")
        return item

    @router.post("/insurer/pa-requests/{pa_request_id}/decide")
    async def decide_pa_request(
        pa_request_id: str,
        request: Request,
        background_tasks: BackgroundTasks,
    ):
        outcome_handler = request.app.state.outcome_handler
        pa_table = request.app.state.dynamodb_resource.Table(request.app.state.settings.pa_requests_table)

        body = await request.json()
        decision = InsurerDecision(
            pa_request_id=pa_request_id,
            decision=body.get("decision", "rejected"),
            rejection_reasons=body.get("rejection_reasons", []),
            feedback=body.get("feedback", ""),
            decided_by=body.get("decided_by", "insurer"),
            decided_at=datetime.now(timezone.utc).isoformat(),
        )

        response = pa_table.get_item(Key={"pa_request_id": pa_request_id})
        record = response.get("Item")
        if not record:
            raise HTTPException(status_code=404, detail="PA request not found")

        if decision.decision == "approved":
            outcome_handler.handle_approval(pa_request_id, record, decision)
            new_status = "completed_approved"
        elif decision.decision == "rejected":
            background_tasks.add_task(
                outcome_handler.handle_rejection,
                pa_request_id, record, decision,
            )
            new_status = "appealing"
        else:
            raise HTTPException(status_code=400, detail=f"Invalid decision: {decision.decision}")

        try:
            from prior_auth_bot.api.websocket import manager
            await manager.broadcast({
                "type": "status_update",
                "pa_request_id": pa_request_id,
                "status": new_status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "patient_name": f"{record.get('patient', {}).get('first_name', '')} {record.get('patient', {}).get('last_name', '')}".strip(),
            })
        except Exception as e:
            logger.error(f"Failed to broadcast WebSocket update: {e}")

        return {"status": "ok", "decision": decision.decision, "pa_request_id": pa_request_id}

    return router


def _extract_treatment_text(item: dict) -> str:
    treatments = item.get("treatments_requiring_pa", [])
    if treatments:
        return treatments[0].get("treatment_text", "")
    return ""
