from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from uuid import uuid4

from prior_auth_bot.models import (
    DeliveryDetails,
    Patient,
    Physician,
    SubmissionResult,
)


class CourierService(ABC):
    @abstractmethod
    def send(
        self,
        patient: Patient,
        physician: Physician,
        treatment_text: str,
        insurance_provider: str,
        insurance_id: str,
        completed_form_s3_key: str,
    ) -> SubmissionResult: ...

    @staticmethod
    def create(delivery_method: str, **kwargs) -> CourierService:
        if delivery_method == "email":
            return EmailCourierService(**kwargs)
        if delivery_method == "fax":
            return FaxCourierService(**kwargs)
        raise ValueError(f"Unknown delivery method: {delivery_method}")


class EmailCourierService(CourierService):
    """Deprecated: Replaced by PortalCourierService. Kept for reference."""
    def __init__(
        self,
        s3_client,
        ses_client,
        completed_forms_bucket: str,
        sender_email: str,
        recipient_email: str,
    ):
        self.s3 = s3_client
        self.ses = ses_client
        self.completed_forms_bucket = completed_forms_bucket
        self.sender_email = sender_email
        self.recipient_email = recipient_email

    def send(
        self,
        patient: Patient,
        physician: Physician,
        treatment_text: str,
        insurance_provider: str,
        insurance_id: str,
        completed_form_s3_key: str,
    ) -> SubmissionResult:
        pdf_obj = self.s3.get_object(
            Bucket=self.completed_forms_bucket, Key=completed_form_s3_key
        )
        pdf_bytes = pdf_obj["Body"].read()

        subject = (
            f"Prior Authorization Request - "
            f"{patient.first_name} {patient.last_name} - "
            f"{insurance_id} - {treatment_text}"
        )

        body_text = (
            f"Prior Authorization Request\n"
            f"\n"
            f"Patient: {patient.first_name} {patient.last_name}\n"
            f"Provider: {insurance_provider}\n"
            f"Insurance ID: {insurance_id}\n"
            f"Physician: Dr. {physician.first_name} {physician.last_name} (NPI: {physician.npi})\n"
            f"Treatment: {treatment_text}\n"
            f"\n"
            f"Please find the attached prior authorization form for review."
        )

        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = self.sender_email
        msg["To"] = self.recipient_email

        body = MIMEText(body_text, "plain")
        msg.attach(body)

        attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
        attachment.add_header(
            "Content-Disposition", "attachment", filename="prior_authorization.pdf"
        )
        msg.attach(attachment)

        response = self.ses.send_raw_email(
            Source=self.sender_email,
            Destinations=[self.recipient_email],
            RawMessage={"Data": msg.as_string()},
        )

        submission_id = f"sub_{uuid4().hex[:8]}"

        return SubmissionResult(
            submission_id=submission_id,
            delivery_method="email",
            delivery_details=DeliveryDetails(
                ses_message_id=response["MessageId"],
                recipient_email=self.recipient_email,
                sender_email=self.sender_email,
                subject=subject,
                attachment_s3_key=completed_form_s3_key,
            ),
            submitted_at=datetime.now(timezone.utc).isoformat(),
            status="sent",
        )


class FaxCourierService(CourierService):
    def send(
        self,
        patient: Patient,
        physician: Physician,
        treatment_text: str,
        insurance_provider: str,
        insurance_id: str,
        completed_form_s3_key: str,
    ) -> SubmissionResult:
        raise NotImplementedError("Fax delivery is not yet supported.")
