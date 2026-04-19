# Motivation
The purpose of this specification is to design a dashboard for physicians to interact with the Prior Authorization system that is specified in [architecture.md](architecture.md). It should hide information that physicians don't need and make available information that they do. For example, physicians don't need to know the AWS diagnostics.

# Requirements
1. Submit a recording of a doctor's appointment
2. Prior Authorization Request Search
3. Prior Authorization Visualizer

## Recording submission
1. This is to kick off the start of the prior authorization automation pipeline
2. Support most common types of audio files
3. The doctor should be able to drag and drop or upload from their computer the audio file.
4. The doctor should be able to select which patient this audio file will be associated with. The patient selector is populated by querying [`pa_patients`](patient_data.md) via the `by_physician` GSI, scoped to the logged-in physician. Next to the selector is an **"Add new patient"** affordance (see Patient Creation below) for when the patient isn't already in the system. The `patient_id` chosen (or newly created) is what gets sent downstream — the pipeline hydrates the full patient snapshot from `pa_patients` at Step 0.
5. The doctor should be able to select which doctor is making the request so that they can select themselves. The physician selector is populated by querying [`pa_physicians`](physician_data.md) via the `by_name` GSI.

## Patient Creation
1. Accessed via an "Add new patient" button next to the patient selector on the Recording Submission screen.
2. Opens a form with fields: `first_name`, `last_name`, `dob`, `insurance_provider`, `insurance_id`, `address`, `phone`.
3. `primary_physician_id` is set automatically from the logged-in physician; `patient_id` is server-generated; `created_at`/`updated_at` are set server-side.
4. On submit, the dashboard POSTs to the backend, which writes a new record to [`pa_patients`](patient_data.md) and returns the new `patient_id`.
5. The patient selector refreshes and the newly created patient is auto-selected so the physician can proceed with the upload.

## Prior Authorization search (physician version)
1. The doctor should be able to search for prior authorizations based on the patient. Patient lookup queries [`pa_patients`](patient_data.md) via the `by_name` GSI for autocomplete; the resolved `patient_id` then filters `pa_requests`.
2. The doctor should be able to search for prior authorizations based on the doctor. Physician lookup queries [`pa_physicians`](physician_data.md) via the `by_name` GSI; the resolved `physician_id` then filters `pa_requests`.
4. When clicking on the prior authorization, it leads to the Prior Authorization Visualizer

## Prior Authorization Visualizer (physician version)
1. This visualizer is the same as specified in [Pipeline Dashboard](pipeline_dashboard.md); however, it should return to the physicians' dashboard, of course.

## AWS Dependencies

This spec reads from:
- **DynamoDB: `pa_requests`** (owned by [Agent Pipeline](agent_pipeline.md)) — For PA search and visualization.
- **DynamoDB: `pa_patients`** (owned by [Patient Data](patient_data.md)) — Patient selector (by_physician GSI) and patient-name search (by_name GSI).
- **DynamoDB: `pa_physicians`** (owned by [Physician Data](physician_data.md)) — Physician selector and physician-name search (by_name GSI).
- **S3: `pa-completed-forms`** (owned by [Document Population](document_population.md)) — For PDF viewing in the PA Visualizer.

This spec writes to:
- **DynamoDB: `pa_patients`** (owned by [Patient Data](patient_data.md)) — New patient records created via the Patient Creation form.

Audio uploads are written to:
- **S3: `pa-audio-uploads`** (owned by [Speech to Text](speech_to_text.md)) — Via the FastAPI upload endpoint.

## API Integration

Communicates with the backend via:
- **REST**: `POST /pa-requests` (upload audio + start pipeline, multipart form with audio file + patient_id + physician_id). Triggers pa_request creation and Step 0 hydration from `pa_patients`/`pa_physicians`.
- **REST**: `GET /pa-requests?patient=...&physician=...` (search)
- **REST**: `GET /pa-requests/:id` (detail with full PA context)
- **REST**: `GET /pa-requests/:id/documents/:attempt_hash/:doc_number` (PDF download)
- **REST**: `GET /patients?physician_id=...&q=...` (list/search patients — patient selector and patient-name autocomplete)
- **REST**: `POST /patients` (create a new patient — body: `first_name`, `last_name`, `dob`, `insurance_provider`, `insurance_id`, `address`, `phone`; `primary_physician_id` is set from the authenticated physician; returns the new `patient_id`). Writes to `pa_patients`.
- **REST**: `GET /physicians?q=...` (list/search physicians — physician selector)
- **WebSocket**: `WS /ws/pa-status` (real-time status updates)
