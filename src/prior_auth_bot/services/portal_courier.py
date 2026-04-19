from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from prior_auth_bot.models import (
    DeliveryDetails,
    Patient,
    Physician,
    SubmissionResult,
)
from prior_auth_bot.services.document_courier import CourierService


class PortalCourierService(CourierService):
    """Replaces EmailCourierService. Marks request as pending_insurer_review instead of emailing."""

    def __init__(self, s3_client, completed_forms_bucket: str):
        self.s3 = s3_client
        self.completed_forms_bucket = completed_forms_bucket

    def send(
        self,
        patient: Patient,
        physician: Physician,
        treatment_text: str,
        insurance_provider: str,
        insurance_id: str,
        completed_form_s3_key: str,
    ) -> SubmissionResult:
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
