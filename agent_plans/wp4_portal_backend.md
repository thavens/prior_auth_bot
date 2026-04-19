# WP4: Insurer Portal Backend

**Depends on:** WP1 (models), can run in parallel with WP3

## New Files

### 1. `src/prior_auth_bot/services/portal_courier.py`

```python
from prior_auth_bot.services.document_courier import CourierService
from prior_auth_bot.models import SubmissionResult, DeliveryDetails

class PortalCourierService(CourierService):
    """Replaces EmailCourierService. Marks request as pending_insurer_review instead of emailing."""

    def __init__(self, s3_client, completed_forms_bucket: str):
        self.s3 = s3_client
        self.completed_forms_bucket = completed_forms_bucket

    def send(self, patient, physician, treatment_text, insurance_provider,
             insurance_id, completed_form_s3_key) -> SubmissionResult:
        submission_id = f"sub_{uuid4().hex[:8]}"
        return SubmissionResult(
            submission_id=submission_id,
            delivery_method="portal",
            delivery_details=DeliveryDetails(
                ses_message_id="",
                recipient_email="",
                sender_email="",
                subject=f"PA: {patient.first_name} {patient.last_name} - {treatment_text}",
                attachment_s3_key=completed_form_s3_key,
            ),
            submitted_at=datetime.now(timezone.utc).isoformat(),
            status="pending_insurer_review",
        )
```

### 2. `src/prior_auth_bot/pipeline/outcome_handler.py`

```python
MAX_APPEAL_ATTEMPTS = 3

class OutcomeHandler:
    """Handles PA approval/rejection. Called by insurer portal API."""

    def __init__(self, dynamodb_resource, pa_requests_table, self_improvement,
                 orchestrator, memory_service, embedding_service):
        self.table = dynamodb_resource.Table(pa_requests_table)
        self.self_improvement = self_improvement
        self.orchestrator = orchestrator
        self.memory_service = memory_service
        self.embedding_service = embedding_service

    def handle_approval(self, pa_request_id, record):
        # Update status to completed_approved, outcome to approved
        # Extract provider and treatment from record
        # If attempt_number == 1: call self_improvement.save_first_approval_memory()
        # If attempt_number > 1: call self_improvement.save_successful_appeal()
        # Find and increment success_count on matching existing memories

    def handle_rejection(self, pa_request_id, record, rejection_reasons, feedback=""):
        attempt_number = record.get("attempt_number", 1)
        if attempt_number >= MAX_APPEAL_ATTEMPTS:
            # Mark completed_rejected_exhausted
            # Call self_improvement.save_exhausted_rejection_memory()
            return {"action": "exhausted"}
        # Build RejectionMessage, call self_improvement.handle_rejection()
        # Call orchestrator.reenter_pipeline(reentry)
        return {"action": "appealing", "attempt": reentry.attempt_number}
```

### 3. `src/prior_auth_bot/api/insurer_routes.py`

```python
def create_insurer_router() -> APIRouter:
    router = APIRouter()

    @router.get("/insurer/queue")
    async def get_insurer_queue(request: Request):
        # Scan pa_requests table for status = "pending_insurer_review"
        # Return list with: pa_request_id, patient name, physician name,
        #   insurance_provider, treatment_text, attempt_number, created_at, status

    @router.get("/insurer/pa-requests/{pa_request_id}")
    async def get_insurer_pa_request(pa_request_id: str, request: Request):
        # Same as existing get_pa_request - return full record

    @router.post("/insurer/pa-requests/{pa_request_id}/decide")
    async def decide_pa_request(pa_request_id: str, request: Request, background_tasks: BackgroundTasks):
        body = await request.json()
        decision = body.get("decision")
        rejection_reasons = body.get("rejection_reasons", [])
        feedback = body.get("feedback", "")

        # Validate PA exists and is pending_insurer_review
        # Get record from DynamoDB

        outcome_handler = request.app.state.outcome_handler

        if decision == "approved":
            outcome_handler.handle_approval(pa_request_id, record)
            new_status = "completed_approved"
        elif decision == "rejected":
            # Run in background to avoid timeout
            background_tasks.add_task(
                outcome_handler.handle_rejection,
                pa_request_id, record, rejection_reasons, feedback
            )
            new_status = "appealing"

        # Broadcast WebSocket update
        from prior_auth_bot.api.websocket import manager
        await manager.broadcast({...})

        return {"status": "ok", "decision": decision}
```

## Modified Files

### 4. `src/prior_auth_bot/pipeline/outcome_monitor.py`
- Replace class body with no-ops:
  - `start()`: pass
  - `stop()`: pass
  - `_run()`: pass
  - `_poll_once()`: pass
- Keep the class for backward compatibility with main.py lifespan init

### 5. `src/prior_auth_bot/main.py`

**Key changes:**
- Import `PortalCourierService` instead of `EmailCourierService`
- Import `create_insurer_router` from `insurer_routes`
- Import `OutcomeHandler` from `outcome_handler`
- Import `EmbeddingService` from `embedding_service`
- Remove `ses_client` creation (comment out or remove the boto3 client call)
- Remove `sqs_client` creation
- Create `EmbeddingService(bedrock_client, settings.bedrock_embedding_model_id)`
- Pass `embedding_service` to `SearchService` constructor
- Pass `embedding_service` to `PipelineOrchestrator` constructor
- Create `PortalCourierService(s3_client, settings.completed_forms_bucket)` instead of EmailCourierService
- Create `OutcomeHandler(dynamodb_resource, settings.pa_requests_table, self_improvement, orchestrator, memory_service, embedding_service)`
- Store `outcome_handler` on `app.state`
- Store `embedding_service` on `app.state`
- Include insurer router: `app.include_router(create_insurer_router(), prefix="/api")`
- Make `outcome_monitor.start()` a no-op or remove it

### 6. `src/prior_auth_bot/api/routes.py`
- Remove `POST /test/simulate-rejection` endpoint
- In `GET /aws/health`: remove or skip SQS queue check, remove SES check

## Verify
```bash
uv run uvicorn prior_auth_bot.main:app --host 0.0.0.0 --port 8080
# Run a pipeline, check status becomes pending_insurer_review
curl http://localhost:8080/api/insurer/queue
curl -X POST http://localhost:8080/api/insurer/pa-requests/{id}/decide -d '{"decision":"approved"}'
```

## What NOT to touch
- Do not modify frontend files (that's WP5)
- Do not modify steps.py or document_population.py (that's WP3)
- Do not modify self_improvement.py internals (that's WP6) - only call its methods
