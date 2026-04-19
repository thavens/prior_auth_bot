import uuid
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)


def create_router() -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health():
        return {"status": "ok"}

    @router.post("/pa-requests")
    async def create_pa_request(
        background_tasks: BackgroundTasks,
        request: Request,
        audio_file: UploadFile = File(...),
        patient_id: str = Form(...),
        physician_id: str = Form(...),
    ):
        pa_request_id = f"pr_{uuid.uuid4().hex[:8]}"

        audio_bytes = await audio_file.read()
        filename = audio_file.filename or "recording.wav"
        audio_format = filename.rsplit(".", 1)[-1].lower() if "." in filename else "wav"

        orchestrator = request.app.state.orchestrator

        def run_pipeline():
            try:
                orchestrator.run_pipeline(pa_request_id, audio_bytes, audio_format, patient_id, physician_id)
            except Exception as e:
                logger.error(f"Pipeline failed for {pa_request_id}: {e}")

        background_tasks.add_task(run_pipeline)

        return {"pa_request_id": pa_request_id, "status": "queued"}

    @router.get("/pa-requests")
    async def search_pa_requests(request: Request, patient: str = "", physician: str = ""):
        table = request.app.state.dynamodb_resource.Table(request.app.state.settings.pa_requests_table)

        filter_parts = []
        expr_values = {}

        if patient:
            filter_parts.append("(contains(patient.first_name, :pname) OR contains(patient.last_name, :pname))")
            expr_values[":pname"] = patient

        if physician:
            filter_parts.append("(contains(physician.first_name, :dname) OR contains(physician.last_name, :dname))")
            expr_values[":dname"] = physician

        scan_kwargs = {}
        if filter_parts:
            scan_kwargs["FilterExpression"] = " AND ".join(filter_parts)
            scan_kwargs["ExpressionAttributeValues"] = expr_values

        response = table.scan(**scan_kwargs)
        items = response.get("Items", [])

        results = []
        for item in items:
            results.append({
                "pa_request_id": item.get("pa_request_id"),
                "status": item.get("status"),
                "patient_name": f"{item.get('patient', {}).get('first_name', '')} {item.get('patient', {}).get('last_name', '')}".strip(),
                "physician_name": f"{item.get('physician', {}).get('first_name', '')} {item.get('physician', {}).get('last_name', '')}".strip(),
                "created_at": item.get("created_at"),
                "attempt_number": item.get("attempt_number", 1),
            })

        return {"results": results}

    @router.get("/pa-requests/{pa_request_id}")
    async def get_pa_request(pa_request_id: str, request: Request):
        table = request.app.state.dynamodb_resource.Table(request.app.state.settings.pa_requests_table)
        response = table.get_item(Key={"pa_request_id": pa_request_id})
        item = response.get("Item")
        if not item:
            raise HTTPException(status_code=404, detail="PA request not found")
        return item

    @router.get("/pa-requests/{pa_request_id}/documents/{attempt_hash}/{doc_number}")
    async def get_document(pa_request_id: str, attempt_hash: str, doc_number: int, request: Request):
        s3 = request.app.state.s3_client
        settings = request.app.state.settings
        key = f"{attempt_hash}/{doc_number}.pdf"
        try:
            obj = s3.get_object(Bucket=settings.completed_forms_bucket, Key=key)
            return StreamingResponse(
                obj["Body"],
                media_type="application/pdf",
                headers={"Content-Disposition": f"inline; filename=pa_{pa_request_id}_{doc_number}.pdf"},
            )
        except s3.exceptions.NoSuchKey:
            raise HTTPException(status_code=404, detail="Document not found")

    @router.get("/aws/health")
    async def aws_health(request: Request):
        health_cache = request.app.state.health_cache
        data = await health_cache.get(
            request.app.state.settings,
            request.app.state.s3_client,
            request.app.state.dynamodb_resource,
        )
        return JSONResponse(content=data, headers={"Cache-Control": "public, max-age=15"})

    @router.get("/patients")
    async def list_patients(request: Request, physician_id: str = "", q: str = ""):
        patient_service = request.app.state.patient_service
        if physician_id:
            patients = patient_service.list_by_physician(physician_id)
        elif q:
            patients = patient_service.search_by_name(q)
        else:
            patients = []
        return {"patients": patients}

    @router.post("/patients")
    async def create_patient(request: Request):
        from prior_auth_bot.models import PatientCreateInput
        body = await request.json()
        physician_id = body.pop("physician_id", "")
        if not physician_id:
            raise HTTPException(status_code=400, detail="physician_id is required")
        data = PatientCreateInput(**body)
        patient_service = request.app.state.patient_service
        result = patient_service.create(physician_id, data)
        return result

    @router.get("/physicians")
    async def list_physicians(request: Request, q: str = ""):
        physician_service = request.app.state.physician_service
        if q:
            physicians = physician_service.search_by_name(q)
        else:
            physicians = physician_service.list_all()
        return {"physicians": physicians}

    @router.post("/seed-forms")
    async def seed_forms(request: Request):
        doc_download = request.app.state.doc_download
        result = doc_download.download_and_process(
            url="https://medi-calrx.dhcs.ca.gov/cms/medicalrx/static-assets/documents/provider/forms-and-information/Medi-Cal_Rx_PA_Request_Form.pdf",
            provider_name="medi-cal",
            form_name="Medi-Cal_Rx_PA_Request_Form",
        )
        return result

    return router
