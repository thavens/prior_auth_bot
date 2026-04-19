import logging

logger = logging.getLogger(__name__)


class OutcomeMonitor:
    """Legacy SQS-based outcome monitor. Disabled -- insurer portal + OutcomeHandler replaces this."""

    def __init__(self, sqs_client=None, queue_url: str = "", dynamodb_resource=None,
                 pa_requests_table: str = "", self_improvement=None, orchestrator=None):
        pass

    def start(self):
        logger.info("OutcomeMonitor.start() is a no-op (replaced by insurer portal)")

    def stop(self):
        logger.info("OutcomeMonitor.stop() is a no-op (replaced by insurer portal)")
