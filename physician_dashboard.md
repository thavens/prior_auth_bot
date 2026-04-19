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
4. The doctor should be able to select which patient this audio file will be associated with. As a result, when this is sent downstream, the pipeline knows that this audio file and patient data are together
5. The doctor should be able to select which doctor is making the request so that they can select themselves

## Prior Authorization search (physician version)
1. The doctor should be able to search for prior authorizations based on the patient
2. The doctor should be able to search for prior authorizations based on the doctor
4. When clicking on the prior authorization, it leads to the Prior Authorization Visualizer

## Prior Authorization Visualizer (physician version)
1. This visualizer is the same as specified in [Pipeline Dashboard](pipeline_dashboard.md); however, it should return to the physicians' dashboard, of course.

## AWS Dependencies

This spec reads from:
- **DynamoDB: `pa_requests`** (owned by [Agent Pipeline](agent_pipeline.md)) — For PA search and visualization.
- **S3: `pa-completed-forms`** (owned by [Document Population](document_population.md)) — For PDF viewing in the PA Visualizer.

Audio uploads are written to:
- **S3: `pa-audio-uploads`** (owned by [Speech to Text](speech_to_text.md)) — Via the FastAPI upload endpoint.

## API Integration

Communicates with the backend via:
- **REST**: `POST /pa-requests` (upload audio + start pipeline, multipart form with audio file + patient_id + physician_id)
- **REST**: `GET /pa-requests?patient=...&physician=...` (search)
- **REST**: `GET /pa-requests/:id` (detail with full PA context)
- **REST**: `GET /pa-requests/:id/documents/:attempt_hash/:doc_number` (PDF download)
- **WebSocket**: `WS /ws/pa-status` (real-time status updates)
