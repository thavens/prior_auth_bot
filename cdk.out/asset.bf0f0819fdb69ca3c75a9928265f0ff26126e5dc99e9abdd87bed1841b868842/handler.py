"""Step 6 -- Document Courier Handler.

Delivers the filled PA form to the insurance provider via the configured
delivery channel (email/SES by default), updates tracking status, and
publishes an SNS notification.
"""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import boto3

from shared.config import Config
from shared.dynamo_client import DynamoClient
from shared.models import Patient, Treatment
from shared.s3_client import S3Client

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

cfg = Config()
dynamo = DynamoClient()
s3 = S3Client()


# =====================================================================
# Courier abstraction
# =====================================================================


class CourierService(ABC):
    """Abstract base class for PA form delivery channels."""

    @abstractmethod
    def send(
        self,
        pdf_bytes: bytes,
        patient: Patient,
        treatment: Treatment,
    ) -> str:
        """Send the filled PDF form and return a message/tracking identifier."""

    @abstractmethod
    def check_response(self, message_id: str) -> dict[str, Any]:
        """Check the delivery status of a previously sent form."""


class EmailCourier(CourierService):
    """Delivers PA forms via Amazon SES as email attachments."""

    def __init__(self) -> None:
        self._ses = boto3.client("ses", region_name=cfg.AWS_REGION)

    def send(
        self,
        pdf_bytes: bytes,
        patient: Patient,
        treatment: Treatment,
    ) -> str:
        subject = (
            f"Prior Authorization Request - {patient.name} - {treatment.name}"
        )

        body_text = (
            "Dear Prior Authorization Department,\n\n"
            "Please find attached a Prior Authorization request for the "
            f"following patient and treatment:\n\n"
            f"  Patient:   {patient.name}\n"
            f"  DOB:       {patient.date_of_birth}\n"
            f"  Insurance: {patient.insurance_provider} (ID: {patient.insurance_id})\n"
            f"  Treatment: {treatment.name}\n\n"
            "This request has been prepared with all required clinical "
            "documentation to support medical necessity. We kindly request "
            "a timely review and determination.\n\n"
            "If you require any additional information, please do not "
            "hesitate to contact our office.\n\n"
            "Thank you for your prompt attention to this matter.\n\n"
            "Sincerely,\n"
            "Prior Authorization Processing System"
        )

        # Build MIME multipart message
        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = cfg.SES_FROM_EMAIL
        msg["To"] = cfg.SES_TO_EMAIL

        # Body
        body_part = MIMEText(body_text, "plain")
        msg.attach(body_part)

        # PDF attachment
        attachment = MIMEApplication(pdf_bytes, _subtype="pdf")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=f"PA_Request_{patient.name.replace(' ', '_')}.pdf",
        )
        msg.attach(attachment)

        # Send via SES
        response = self._ses.send_raw_email(
            Source=cfg.SES_FROM_EMAIL,
            Destinations=[cfg.SES_TO_EMAIL],
            RawMessage={"Data": msg.as_string()},
        )

        message_id = response["MessageId"]
        logger.info("Email sent via SES, MessageId: %s", message_id)
        return message_id

    def check_response(self, message_id: str) -> dict[str, Any]:
        """SES does not provide synchronous response checking.

        Delivery/bounce/complaint notifications are handled asynchronously
        via SES event publishing (SNS/EventBridge).
        """
        return {
            "message_id": message_id,
            "status": "DELIVERY_TRACKING_ASYNC",
        }


class FaxCourier(CourierService):
    """Placeholder courier for fax-based PA submission."""

    def send(
        self,
        pdf_bytes: bytes,
        patient: Patient,
        treatment: Treatment,
    ) -> str:
        raise NotImplementedError(
            "Fax delivery is not yet implemented. "
            "Configure an eFax or HIPAA-compliant fax API integration."
        )

    def check_response(self, message_id: str) -> dict[str, Any]:
        raise NotImplementedError("Fax response checking is not yet implemented.")


def get_courier(channel: str = "email") -> CourierService:
    """Factory function to obtain the appropriate courier implementation."""

    couriers: dict[str, type[CourierService]] = {
        "email": EmailCourier,
        "fax": FaxCourier,
    }

    courier_cls = couriers.get(channel.lower())
    if courier_cls is None:
        raise ValueError(
            f"Unsupported courier channel '{channel}'. "
            f"Supported: {list(couriers.keys())}"
        )
    return courier_cls()


# =====================================================================
# Lambda handler
# =====================================================================


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Send the filled PA form via the configured delivery channel.

    Event keys:
        pa_request_id      -- tracking ID from document population step
        filled_form_s3_key -- S3 key of the filled PDF
        treatment          -- serialized Treatment
        patient            -- serialized Patient
    """

    pa_request_id: str = event["pa_request_id"]
    filled_form_s3_key: str = event["filled_form_s3_key"]
    treatment = Treatment(**event["treatment"])
    patient = Patient(**event["patient"])

    # -----------------------------------------------------------------
    # Download the filled PDF
    # -----------------------------------------------------------------
    logger.info("Downloading filled form: %s", filled_form_s3_key)
    pdf_bytes = s3.read_bytes(filled_form_s3_key)

    # -----------------------------------------------------------------
    # Send via courier
    # -----------------------------------------------------------------
    courier = get_courier("email")
    message_id = courier.send(pdf_bytes, patient, treatment)

    # -----------------------------------------------------------------
    # Update tracking status to SUBMITTED
    # -----------------------------------------------------------------
    dynamo.update_tracking_status(
        cfg.TRACKING_TABLE,
        pa_request_id,
        status="SUBMITTED",
        submitted_at=int(time.time()),
        message_id=message_id,
    )
    logger.info("Tracking record %s updated to SUBMITTED", pa_request_id)

    # -----------------------------------------------------------------
    # Publish SNS notification
    # -----------------------------------------------------------------
    if cfg.SNS_TOPIC_ARN:
        sns = boto3.client("sns", region_name=cfg.AWS_REGION)
        sns.publish(
            TopicArn=cfg.SNS_TOPIC_ARN,
            Subject=f"PA Submitted: {patient.name} - {treatment.name}",
            Message=json.dumps(
                {
                    "event": "PA_SUBMITTED",
                    "pa_request_id": pa_request_id,
                    "patient_name": patient.name,
                    "treatment_name": treatment.name,
                    "message_id": message_id,
                },
                default=str,
            ),
        )
        logger.info("SNS notification published for PA submission")

    return {
        "pa_request_id": pa_request_id,
        "message_id": message_id,
        "status": "SUBMITTED",
        "outcome": "PENDING",
    }
