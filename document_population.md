# Motivation

We need a way to turn blank documents and filling information into a complete document ready for submission into the prior authorization system of the insurer. These blank pdf documents may or may not contain precoded locations for the user to fill out information.

https://code.claude.com/docs/en/agent-sdk/custom-tools

# Requirements

1. Retrieve the forms, along with the aws textract data to provide to LLM.
2. Recieve the patient data (snapshot from the pa_request, originally hydrated from [`pa_patients`](patient_data.md) at Agent Pipeline Step 0) that is used to fill in the form.
3. Generate with LLM according to a key value json schema that can be used to populate the fields.
4. use pymupdf to fill out the AcroForm fields with the right values.

# Schema

The model should respond in a json format which contains keys corresponding to "<widget_type>_\<i>" where i is the ith index of that specific widget type.

# Implementation

1. Forms will be taken from s3 bucket form data, look in [current_services](current_services.md).
2. Textract will be taken from s3 bucket as well, look in [current_services](current_services.md).
3. Combine the textract and patient data into a user prompt template.
4. Sample the llm json structured response.
5. Use python pymupdf code to populate the pdf using the key names from schema. Resample up to 3 times on error before failing.
6. Store the complete the form will a unique name in s3 completed forms bucket.
7. Return with information.

## Completed forms bucket structure

There should be directories by attempt. That means folders for each Prior Authorization session. The initial request and all follow up appeals should show in the folder. Within the folder the forms should count up starting from 1. The attempt hash will be given when calling the function.

## Pipeline Failure Modes

This pipeline should fail if there is a missing answer. This is a critical step so failure is unrecoverable and should now fail silently.

## AWS Ownership

This spec owns:
- **S3: `pa-completed-forms`** — Stores filled PA forms. Structure: `/{attempt_hash}/1.pdf, 2.pdf, ...`

This spec reads from:
- **S3: `pa-blank-forms`** (owned by [Document Download](document_download.md))
- **S3: `pa-textract-output`** (owned by [Document Download](document_download.md))

## Input Schema (from Agent Pipeline Step 5)

```json
{
  "pa_request_id": "pr_a1b2c3d4",
  "attempt_hash": "att_x7y8z9",
  "form_s3_key": "pa-blank-forms/medi-cal/Medi-Cal_Rx_PA_Request_Form.pdf",
  "textract_s3_key": "pa-textract-output/medi-cal/Medi-Cal_Rx_PA_Request_Form.json",
  "patient": {
    "patient_id": "pat_001",
    "first_name": "Jane",
    "last_name": "Doe",
    "dob": "1985-03-12",
    "insurance_provider": "medi-cal",
    "insurance_id": "MC-9876543"
  },
  "physician": {
    "physician_id": "doc_042",
    "first_name": "Robert",
    "last_name": "Chen",
    "npi": "1234567890"
  },
  "treatment": {
    "entity_id": "ent_001",
    "text": "Humira (adalimumab)",
    "category": "MEDICATION",
    "rxnorm_concept": "327361",
    "snomed_code": "391188009",
    "pa_reason": "Specialty medication requiring step therapy documentation"
  },
  "memories": [],
  "rejection_context": null
}
```

## LLM Widget Response Schema

```json
{
  "Text_0": "Doe",
  "Text_1": "Jane",
  "Text_2": "03/12/1985",
  "CheckBox_0": true,
  "CheckBox_1": false,
  "RadioButton_0": "new_request"
}
```

## Output Schema (to Agent Pipeline Step 6)

```json
{
  "completed_form_s3_key": "pa-completed-forms/att_x7y8z9/1.pdf",
  "field_fill_results": {
    "total_fields": 42,
    "filled_fields": 38,
    "skipped_fields": 4,
    "llm_attempts": 1
  }
}
```