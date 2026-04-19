import io
import json
import time

import boto3
import fitz
import httpx


class DocumentDownloadService:
    def __init__(
        self,
        s3_client,
        textract_client,
        blank_forms_bucket: str,
        textract_output_bucket: str,
    ):
        self.s3 = s3_client
        self.textract = textract_client
        self.blank_forms_bucket = blank_forms_bucket
        self.textract_output_bucket = textract_output_bucket

    def download_and_process(self, url: str, provider_name: str, form_name: str) -> dict:
        pdf_bytes = self._download_pdf(url)
        labeled_pdf, field_summary, field_descriptions = self._label_acroform_fields(pdf_bytes)
        form_s3_key = f"{provider_name}/{form_name}.pdf"
        self._upload_to_s3(self.blank_forms_bucket, form_s3_key, labeled_pdf, "application/pdf")
        textract_result = self._run_textract(form_s3_key)
        textract_result["FieldDescriptions"] = field_descriptions
        textract_s3_key = f"{provider_name}/{form_name}.json"
        self._upload_to_s3(
            self.textract_output_bucket,
            textract_s3_key,
            json.dumps(textract_result).encode(),
            "application/json",
        )
        return {
            "form_s3_key": f"pa-blank-forms/{form_s3_key}",
            "textract_s3_key": f"pa-textract-output/{textract_s3_key}",
            "field_count": sum(field_summary.values()),
            "field_types_summary": field_summary,
        }

    def _download_pdf(self, url: str) -> bytes:
        response = httpx.get(url, timeout=30, follow_redirects=True)
        response.raise_for_status()
        return response.content

    def _label_acroform_fields(self, pdf_bytes: bytes) -> tuple[bytes, dict[str, int], dict[str, str]]:
        field_type_map = {
            fitz.PDF_WIDGET_TYPE_TEXT: "Text",
            fitz.PDF_WIDGET_TYPE_CHECKBOX: "CheckBox",
            fitz.PDF_WIDGET_TYPE_RADIOBUTTON: "RadioButton",
            fitz.PDF_WIDGET_TYPE_COMBOBOX: "ComboBox",
            fitz.PDF_WIDGET_TYPE_LISTBOX: "ListBox",
        }
        counters: dict[str, int] = {}
        field_descriptions: dict[str, str] = {}
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            for widget in page.widgets():
                type_name = field_type_map.get(widget.field_type, "Unknown")
                counters.setdefault(type_name, 0)
                label = f"{type_name}_{counters[type_name]}"
                widget.field_name = label
                counters[type_name] += 1
                widget.update()

                nearby_text = ""
                r = widget.rect

                if type_name in ("CheckBox", "RadioButton"):
                    clip = fitz.Rect(r.x1, r.y0 - 3, r.x1 + 300, r.y1 + 3)
                    clip = clip & page.rect
                    if not clip.is_empty:
                        nearby_text = page.get_text("text", clip=clip).strip()
                    if not nearby_text:
                        clip = fitz.Rect(r.x0 - 300, r.y0 - 3, r.x0, r.y1 + 3)
                        clip = clip & page.rect
                        if not clip.is_empty:
                            nearby_text = page.get_text("text", clip=clip).strip()
                else:
                    clip = fitz.Rect(r.x0 - 200, r.y0 - 5, r.x0 - 2, r.y1 + 5)
                    clip = clip & page.rect
                    if not clip.is_empty:
                        nearby_text = page.get_text("text", clip=clip).strip()
                    if not nearby_text:
                        clip = fitz.Rect(r.x0 - 10, r.y0 - 25, r.x1 + 50, r.y0 - 1)
                        clip = clip & page.rect
                        if not clip.is_empty:
                            nearby_text = page.get_text("text", clip=clip).strip()

                if nearby_text:
                    nearby_text = " ".join(nearby_text.split())[:120]
                field_descriptions[label] = nearby_text
        labeled_bytes = doc.tobytes()
        doc.close()
        return labeled_bytes, counters, field_descriptions

    def _upload_to_s3(self, bucket: str, key: str, data: bytes, content_type: str):
        self.s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)

    def _run_textract(self, form_s3_key: str) -> dict:
        response = self.textract.start_document_analysis(
            DocumentLocation={
                "S3Object": {"Bucket": self.blank_forms_bucket, "Name": form_s3_key}
            },
            FeatureTypes=["FORMS"],
        )
        job_id = response["JobId"]
        return self._wait_for_textract(job_id)

    def _wait_for_textract(self, job_id: str, timeout: int = 300) -> dict:
        start = time.time()
        delay = 2
        while time.time() - start < timeout:
            response = self.textract.get_document_analysis(JobId=job_id)
            status = response["JobStatus"]
            if status == "SUCCEEDED":
                blocks = response.get("Blocks", [])
                while "NextToken" in response:
                    response = self.textract.get_document_analysis(
                        JobId=job_id, NextToken=response["NextToken"]
                    )
                    blocks.extend(response.get("Blocks", []))
                return {"Blocks": blocks}
            if status == "FAILED":
                raise RuntimeError(
                    f"Textract failed: {response.get('StatusMessage', 'unknown')}"
                )
            time.sleep(delay)
            delay = min(delay * 1.5, 10)
        raise TimeoutError("Textract job timed out")
