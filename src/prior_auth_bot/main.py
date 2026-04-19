import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import boto3
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from prior_auth_bot.config import Settings
from prior_auth_bot.services.speech_to_text import SpeechToTextService
from prior_auth_bot.services.memory_feature import MemoryFeatureService
from prior_auth_bot.services.search_service import SearchService
from prior_auth_bot.services.document_download import DocumentDownloadService
from prior_auth_bot.services.document_population import DocumentPopulationService
from prior_auth_bot.services.portal_courier import PortalCourierService
from prior_auth_bot.services.self_improvement import SelfImprovementService
from prior_auth_bot.services.embedding_service import EmbeddingService
from prior_auth_bot.services.patient_service import PatientService
from prior_auth_bot.services.physician_service import PhysicianService
from prior_auth_bot.pipeline.orchestrator import PipelineOrchestrator
from prior_auth_bot.pipeline.outcome_monitor import OutcomeMonitor
from prior_auth_bot.pipeline.outcome_handler import OutcomeHandler
from prior_auth_bot.api.health_cache import HealthCache
from prior_auth_bot.api.routes import create_router
from prior_auth_bot.api.insurer_routes import create_insurer_router
from prior_auth_bot.api.websocket import create_ws_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()

    session = boto3.Session(region_name=settings.aws_region)
    s3_client = session.client("s3")
    transcribe_client = session.client("transcribe")
    textract_client = session.client("textract")
    bedrock_client = session.client("bedrock-runtime", region_name=settings.bedrock_region)
    dynamodb_resource = session.resource("dynamodb")
    cloudwatch_client = session.client("cloudwatch")

    stt = SpeechToTextService(s3_client, transcribe_client, settings.audio_uploads_bucket)
    memory_service = MemoryFeatureService(dynamodb_resource, settings.pa_memories_table)
    embedding_service = EmbeddingService(bedrock_client, settings.bedrock_embedding_model_id)
    search_service = SearchService(s3_client, dynamodb_resource, memory_service, settings.blank_forms_bucket, settings.scrape_cache_table, embedding_service=embedding_service)
    doc_download = DocumentDownloadService(s3_client, textract_client, settings.blank_forms_bucket, settings.textract_output_bucket)
    doc_pop = DocumentPopulationService(s3_client, bedrock_client, settings.blank_forms_bucket, settings.textract_output_bucket, settings.completed_forms_bucket, settings.bedrock_model_id)
    courier = PortalCourierService(s3_client, settings.completed_forms_bucket)
    self_improvement = SelfImprovementService(sqs_client=None, bedrock_client=bedrock_client, memory_service=memory_service, queue_url="", model_id=settings.bedrock_model_id)
    patient_service = PatientService(dynamodb_resource, settings.pa_patients_table)
    physician_service = PhysicianService(dynamodb_resource, settings.pa_physicians_table)

    orchestrator = PipelineOrchestrator(
        speech_to_text=stt, search_service=search_service, memory_service=memory_service,
        document_download=doc_download, document_population=doc_pop,
        document_courier=courier, self_improvement=self_improvement,
        patient_service=patient_service, physician_service=physician_service,
        dynamodb_resource=dynamodb_resource, s3_client=s3_client,
        textract_output_bucket=settings.textract_output_bucket,
        bedrock_client=bedrock_client, pa_requests_table=settings.pa_requests_table,
        model_id=settings.bedrock_model_id,
    )

    pa_table = dynamodb_resource.Table(settings.pa_requests_table)

    outcome_handler = OutcomeHandler(
        pa_table=pa_table,
        memory_service=memory_service,
        self_improvement_service=self_improvement,
        embedding_service=embedding_service,
        search_service=search_service,
        orchestrator=orchestrator,
        bedrock_client=bedrock_client,
    )

    outcome_monitor = OutcomeMonitor()

    app.state.settings = settings
    app.state.orchestrator = orchestrator
    app.state.outcome_monitor = outcome_monitor
    app.state.outcome_handler = outcome_handler
    app.state.embedding_service = embedding_service
    app.state.s3_client = s3_client
    app.state.dynamodb_resource = dynamodb_resource
    app.state.cloudwatch_client = cloudwatch_client
    app.state.doc_download = doc_download
    app.state.patient_service = patient_service
    app.state.physician_service = physician_service

    health_cache = HealthCache(ttl=30.0)
    app.state.health_cache = health_cache
    health_task = asyncio.create_task(
        health_cache.background_loop(settings, s3_client, dynamodb_resource)
    )

    outcome_monitor.start()
    logger.info("All services initialized (insurer portal active)")
    yield
    health_task.cancel()
    outcome_monitor.stop()
    logger.info("Shutting down")


app = FastAPI(title="Prior Authorization Bot", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(create_router(), prefix="/api")
app.include_router(create_insurer_router(), prefix="/api")
app.include_router(create_ws_router())

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"

if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="static")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = FRONTEND_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIR / "index.html")
