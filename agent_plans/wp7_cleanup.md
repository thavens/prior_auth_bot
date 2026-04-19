# WP7: Cleanup and Documentation

**Depends on:** All other WPs complete

## Files to Modify

### 1. `src/prior_auth_bot/aws_setup.py`
- Remove or comment out SQS queue creation code (the `create_sqs_queue` function or inline SQS setup)
- Remove or comment out SES email verification code
- Keep all DynamoDB and S3 setup intact
- Note: Do NOT delete existing AWS resources - just stop provisioning new ones

### 2. `current_services.md`
- Mark SES section as DEPRECATED: "Replaced by Insurer Portal - PA requests now reviewed via web UI"
- Mark SQS section as DEPRECATED: "Replaced by Insurer Portal - decisions submitted via API"
- Add under Compute/AI Services: "AWS Bedrock Titan Embeddings v2 (amazon.titan-embed-text-v2:0) - generates 1024-dim embeddings for memory advice text, used in agentic RAG search"
- Add note about `embedding` attribute on pa_memories table: "Memories now store vector embeddings for semantic search"
- Add note about Insurer Portal: "Insurer reviews PA requests at /insurer route, decisions via POST /api/insurer/pa-requests/{id}/decide"

### 3. `src/prior_auth_bot/services/document_courier.py`
- Add a comment at the top of `EmailCourierService` class: "Deprecated: Replaced by PortalCourierService. Kept for reference."
- Keep `CourierService` ABC intact (still used by PortalCourierService)
- Keep `FaxCourierService` stub intact

## Verify
- Start server and run full integration test:
  1. Upload audio via physician portal (/)
  2. Watch pipeline progress on /pipeline
  3. After Step 6, status = pending_insurer_review
  4. Open /insurer, see pending request
  5. Click into review, see details, view PDF
  6. Approve -> memory saved, status = completed_approved
  7. Submit another PA, reject with reasons -> appeal triggers
  8. Approve appeal -> appeal memory saved
  9. Submit same provider/treatment -> memories in Steps 1, 2, 4, 5
  10. Reject 3 times -> anti-pattern memory saved
- Build frontend: `cd frontend && npm run build`
- Start server: `uv run uvicorn prior_auth_bot.main:app --host 0.0.0.0 --port 8080`

## What NOT to touch
- Do not delete existing AWS resources (SQS queue, SES identity)
- Do not remove any Python files - only add deprecation comments
- Do not change any functionality - this WP is purely cleanup/documentation
