# Motivation
We need a way to turn blank documents and filling information into a complete document ready for submission into the prior authorization system of the insurer. These blank pdf documents may or may not contain precoded locations for the user to fill out information.

https://code.claude.com/docs/en/agent-sdk/custom-tools

# Requirements
1. Retrieve the forms, along with the aws textract data to provide to LLM.
2. Recieve the patient data that is used to fill in the form.
3. Generate with LLM according to a key value json schema that can be used to populate the fields.
4. use pymupdf to fill out the AcroForm fields with the right values.

# Schema
The model should respond in a json format which contains keys corresponding to "<widget_type>_<i>" where i is the ith index of that specific widget type.

# Implementation
1. Forms will be taken from s3 bucket form data, look in (readme)[README.md].
2. Textract will be taken from s3 bucket as well, look in (readme)[README.md].
3. Combine the textract and patient data into a user prompt template.
4. Sample the llm json structured response.
5. Use python pymupdf code to populate the pdf using the key names from schema. Resample up to 3 times on error before failing.
6. Store the complete the form will a unique name in s3 completed forms bucket.
7. Return with information.

## Completed forms bucket structure
There should be directories by attempt. That means folders for each Prior Authorization session. The initial request and all follow up appeals should show in the folder. Within the folder the forms should count up starting from 1. The attempt hash will be given when calling the function.

## Pipeline Failure Modes
This pipeline should fail if there is a missing answer. This is a critical step so failure is unrecoverable and should now fail silently.