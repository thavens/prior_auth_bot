import io
import json

import fitz

from prior_auth_bot.models import (
    DocumentPopulationInput,
    DocumentPopulationResult,
    FieldFillResults,
)


class DocumentPopulationService:
    def __init__(
        self,
        s3_client,
        bedrock_client,
        blank_forms_bucket: str,
        textract_output_bucket: str,
        completed_forms_bucket: str,
        model_id: str = "anthropic.claude-sonnet-4-6",
    ):
        self.s3 = s3_client
        self.bedrock = bedrock_client
        self.blank_forms_bucket = blank_forms_bucket
        self.textract_output_bucket = textract_output_bucket
        self.completed_forms_bucket = completed_forms_bucket
        self.model_id = model_id

    def populate_form(self, input_data: DocumentPopulationInput) -> DocumentPopulationResult:
        pdf_bytes = self.s3.get_object(
            Bucket=self.blank_forms_bucket, Key=input_data.form_s3_key
        )["Body"].read()

        textract_data = json.loads(
            self.s3.get_object(
                Bucket=self.textract_output_bucket, Key=input_data.textract_s3_key
            )["Body"].read()
        )

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        fields = []
        for page in doc:
            for widget in page.widgets():
                fields.append({"name": widget.field_name, "type": widget.field_type_string})
        doc.close()

        prompt = self._build_prompt(fields, textract_data, input_data)

        last_error = None
        widget_values = None
        filled_pdf = None
        attempt = 0
        for attempt in range(1, 4):
            try:
                call_prompt = prompt if attempt == 1 else prompt + f"\n\nPrevious attempt failed with: {last_error}. Fix the JSON."
                widget_values = self._call_llm(call_prompt)
                filled_pdf = self._fill_pdf(pdf_bytes, widget_values)
                break
            except (json.JSONDecodeError, KeyError, Exception) as e:
                last_error = str(e)
                if attempt == 3:
                    raise RuntimeError(f"Document population failed after 3 attempts: {last_error}")

        filled = sum(1 for v in widget_values.values() if v is not None)
        skipped = len(fields) - filled

        s3_prefix = f"{input_data.attempt_hash}/"
        existing = self.s3.list_objects_v2(
            Bucket=self.completed_forms_bucket, Prefix=s3_prefix
        )
        doc_number = len(existing.get("Contents", [])) + 1
        output_key = f"{input_data.attempt_hash}/{doc_number}.pdf"

        self.s3.put_object(
            Bucket=self.completed_forms_bucket,
            Key=output_key,
            Body=filled_pdf,
            ContentType="application/pdf",
        )

        return DocumentPopulationResult(
            completed_form_s3_key=f"pa-completed-forms/{output_key}",
            field_fill_results=FieldFillResults(
                total_fields=len(fields),
                filled_fields=filled,
                skipped_fields=skipped,
                llm_attempts=attempt,
            ),
        )

    def _build_prompt(
        self,
        fields: list[dict],
        textract_data: dict,
        input_data: DocumentPopulationInput,
    ) -> str:
        field_descriptions = textract_data.get("FieldDescriptions", {})
        textract_kv_pairs = self._extract_textract_descriptions(textract_data)

        field_lines = []
        for f in fields:
            desc = field_descriptions.get(f["name"], "")
            suffix = f" - {desc}" if desc else ""
            field_lines.append(f"- {f['name']}: {f['type']}{suffix}")
        fields_block = "\n".join(field_lines)

        p = input_data.patient
        ph = input_data.physician
        t = input_data.treatment

        parts = [
            "You are filling out a prior authorization form. Based on the patient data, physician data, treatment information, and any advice from past applications, provide values for each form field.",
            f"\nFORM FIELDS:\n{fields_block}",
            f"\nPATIENT DATA:\nName: {p.first_name} {p.last_name}\nDOB: {p.dob}\nInsurance: {p.insurance_provider} - {p.insurance_id}\nAddress: {p.address}\nPhone: {p.phone}",
            f"\nPHYSICIAN DATA:\nName: {ph.first_name} {ph.last_name}\nNPI: {ph.npi}\nSpecialty: {ph.specialty}\nPhone: {ph.phone}\nFax: {ph.fax}",
            f"\nTREATMENT:\n{t.text} ({t.category})\nRxNorm: {t.rxnorm_concept}\nSNOMED: {t.snomed_code}\nPA Reason: {t.pa_reason}",
        ]

        if textract_kv_pairs:
            kv_lines = [f"- {k}: {v}" for k, v in textract_kv_pairs.items() if k.strip()]
            if kv_lines:
                parts.append(
                    "\nADDITIONAL FORM CONTEXT (labels visible on the form):\n"
                    + "\n".join(kv_lines)
                )

        if input_data.memories:
            advice_lines = []
            for m in input_data.memories:
                outcome = m.outcome or ""
                tags_str = ", ".join(m.tags) if m.tags else "none"
                if "rejected" in outcome.lower() or "exhausted" in outcome.lower():
                    prefix = "ANTI-PATTERN:"
                elif m.success_count >= 2:
                    prefix = "PROVEN APPROACH:"
                else:
                    prefix = ""
                line = f"- {prefix} {m.advice}".strip() if prefix else f"- {m.advice}"
                line += f" (outcome: {outcome or 'n/a'}, success_count: {m.success_count}, tags: [{tags_str}])"
                advice_lines.append(line)
            parts.append("\nADVICE FROM PAST APPLICATIONS:\n" + "\n".join(advice_lines))

        if input_data.rejection_context:
            rc = input_data.rejection_context
            parts.append(
                f"\nPREVIOUS REJECTION FEEDBACK:\nReasons: {rc.get('rejection_reasons', '')}\nProposed fixes: {rc.get('proposed_fixes', '')}"
            )

        parts.append(
            '\nRESPONSE FORMAT:\n'
            'Respond with ONLY a JSON object. Keys must be the EXACT field names listed above.\n'
            '\nValue rules by field type:\n'
            '- Text fields: string value (e.g., "Jane Doe", "1985-03-12")\n'
            '- CheckBox fields: boolean value ONLY — true or false. '
            'true = checked, false = unchecked. '
            'Default to false unless the data clearly indicates the box should be checked.\n'
            '- RadioButton fields: string matching one of the radio group options\n'
            '- Leave a field as null if you genuinely cannot determine the value.\n'
            '\nIMPORTANT CHECKBOX GUIDANCE:\n'
            '- Do NOT check all checkboxes. Most checkboxes on a PA form should remain unchecked.\n'
            '- Only check a checkbox if the patient data, treatment, or physician data specifically justifies it.\n'
            '- If the form has mutually exclusive options (e.g., "New Request" vs "Reauthorization"), only check ONE.\n'
            '\nExample response:\n'
            '{"Text_0": "Jane Doe", "Text_1": "1985-03-12", "CheckBox_0": true, "CheckBox_1": false, "RadioButton_0": "Option A"}\n'
            '\nJSON:'
        )

        return "\n".join(parts)

    def _extract_textract_descriptions(self, textract_data: dict) -> dict[str, str]:
        blocks = textract_data.get("Blocks", [])
        block_map = {b["Id"]: b for b in blocks}
        descriptions = {}

        for block in blocks:
            if block.get("BlockType") != "KEY_VALUE_SET":
                continue
            if "KEY" not in block.get("EntityTypes", []):
                continue

            key_text = self._get_block_text(block, block_map)
            if not key_text:
                continue

            value_text = ""
            for rel in block.get("Relationships", []):
                if rel["Type"] == "VALUE":
                    for vid in rel["Ids"]:
                        value_block = block_map.get(vid)
                        if value_block:
                            value_text = self._get_block_text(value_block, block_map)
                            break

            descriptions[key_text] = value_text

        return descriptions

    def _get_block_text(self, block: dict, block_map: dict) -> str:
        parts = []
        for rel in block.get("Relationships", []):
            if rel["Type"] == "CHILD":
                for child_id in rel["Ids"]:
                    child = block_map.get(child_id)
                    if child and child.get("BlockType") == "WORD":
                        parts.append(child.get("Text", ""))
        return " ".join(parts)

    def _call_llm(self, prompt: str) -> dict:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": prompt}],
        })
        response = self.bedrock.invoke_model(
            modelId=self.model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(response["body"].read())
        text = result["content"][0]["text"]
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())

    @staticmethod
    def _coerce_checkbox_value(value) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "yes", "checked", "on", "1")
        if isinstance(value, (int, float)):
            return bool(value)
        return False

    def _fill_pdf(self, pdf_bytes: bytes, widget_values: dict) -> bytes:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            for widget in page.widgets():
                field_name = widget.field_name
                if field_name not in widget_values or widget_values[field_name] is None:
                    continue
                value = widget_values[field_name]
                if widget.field_type == fitz.PDF_WIDGET_TYPE_TEXT:
                    widget.field_value = str(value)
                elif widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                    checked = self._coerce_checkbox_value(value)
                    widget.field_value = widget.on_state() if checked else "Off"
                elif widget.field_type == fitz.PDF_WIDGET_TYPE_RADIOBUTTON:
                    widget.field_value = str(value)
                widget.update()
        result = doc.tobytes()
        doc.close()
        return result
