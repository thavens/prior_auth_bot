from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    aws_region: str = "us-east-1"

    # S3 Buckets (account-suffixed for global uniqueness)
    audio_uploads_bucket: str = "pa-audio-uploads-917918930878"
    blank_forms_bucket: str = "pa-blank-forms-917918930878"
    textract_output_bucket: str = "pa-textract-output-917918930878"
    completed_forms_bucket: str = "pa-completed-forms-917918930878"

    # DynamoDB Tables
    pa_requests_table: str = "pa_requests"
    pa_memories_table: str = "pa_memories"
    scrape_cache_table: str = "pa_scrape_cache"
    pa_patients_table: str = "pa_patients"
    pa_physicians_table: str = "pa_physicians"

    # SQS
    ses_responses_queue_url: str = "https://sqs.us-east-1.amazonaws.com/917918930878/pa-ses-responses"

    # SES
    ses_sender_email: str = "michael.lavery.2017@gmail.com"
    ses_recipient_email: str = "michael.lavery.2017@gmail.com"

    # LLM
    bedrock_model_id: str = "us.anthropic.claude-opus-4-6-v1"
    bedrock_region: str = "us-west-2"
    bedrock_embedding_model_id: str = "amazon.titan-embed-text-v2:0"

    model_config = {"env_prefix": "PA_BOT_"}
