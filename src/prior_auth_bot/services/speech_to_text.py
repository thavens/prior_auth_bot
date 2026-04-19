from __future__ import annotations

import json
import re
import time

from prior_auth_bot.models import TranscriptResult


FORMAT_MAP = {
    "wav": "wav",
    "mp3": "mp3",
    "m4a": "mp4",
    "ogg": "ogg",
    "flac": "flac",
    "webm": "ogg",
}


class SpeechToTextService:
    def __init__(self, s3_client, transcribe_client, bucket_name: str):
        self.s3 = s3_client
        self.transcribe_client = transcribe_client
        self.bucket = bucket_name

    def transcribe(self, pa_request_id: str, audio_bytes: bytes, audio_format: str) -> TranscriptResult:
        s3_key = f"{pa_request_id}/appointment.{audio_format}"
        self.s3.put_object(Bucket=self.bucket, Key=s3_key, Body=audio_bytes)

        job_name = re.sub(r"[^a-zA-Z0-9\-_.]", "", f"pa-{pa_request_id}")
        media_format = FORMAT_MAP.get(audio_format, audio_format)
        output_key = f"{pa_request_id}/transcript.json"

        self.transcribe_client.start_transcription_job(
            TranscriptionJobName=job_name,
            LanguageCode="en-US",
            MediaFormat=media_format,
            Media={"MediaFileUri": f"s3://{self.bucket}/{s3_key}"},
            OutputBucketName=self.bucket,
            OutputKey=output_key,
        )

        wait = 2
        elapsed = 0
        timeout = 300

        while elapsed < timeout:
            resp = self.transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
            status = resp["TranscriptionJob"]["TranscriptionJobStatus"]

            if status == "COMPLETED":
                break
            if status == "FAILED":
                reason = resp["TranscriptionJob"].get("FailureReason", "Unknown error")
                raise RuntimeError(f"Transcription job failed: {reason}")

            time.sleep(wait)
            elapsed += wait
            wait = min(wait * 2, 10)
        else:
            raise RuntimeError(f"Transcription job timed out after {timeout}s")

        obj = self.s3.get_object(Bucket=self.bucket, Key=output_key)
        transcript_data = json.loads(obj["Body"].read())

        transcript_text = transcript_data["results"]["transcripts"][0]["transcript"]

        items = transcript_data["results"]["items"]
        confidences = [
            float(item["alternatives"][0]["confidence"])
            for item in items
            if "alternatives" in item
            and item["alternatives"]
            and "confidence" in item["alternatives"][0]
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        duration = 0.0
        for item in reversed(items):
            if "end_time" in item:
                duration = float(item["end_time"])
                break

        return TranscriptResult(
            transcript_text=transcript_text,
            transcript_s3_key=output_key,
            language_code="en-US",
            confidence=avg_confidence,
            duration_seconds=duration,
        )
