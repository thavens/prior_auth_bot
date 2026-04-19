# Motivation

Patient information (name, date of birth, insurance, address, phone) is required at nearly every stage of the prior authorization pipeline — entity extraction, PA determination, form population, email subject lines, and dashboard displays. Without a source-of-truth store, these fields would be stitched together per request with no way for physicians to reuse patient records across appointments or search for a patient by name. This feature provides the canonical patient record store that feeds the pipeline and powers dashboard patient selection/search.

# Requirement

This feature owns the storage of patient records. It exposes read access for pipeline hydration and dashboard selection/search, and write access for physicians creating new patient records via the [Physician Dashboard](physician_dashboard.md).

A new pa_request hydrates a snapshot of the patient's fields at pipeline start (see [Agent Pipeline](agent_pipeline.md) Step 0). Downstream pipeline steps read the snapshot on the pa_request record, not this table — this protects in-flight requests from mid-pipeline edits to the source record.

## Access Patterns

1. Fetch a patient by `patient_id` — pipeline hydration at request creation.
2. List patients for a given physician — dashboard patient-selection dropdown, scoped to the logged-in physician.
3. Search patients by last name — dashboard autocomplete for patient-based PA search.
4. Create a new patient — physician dashboard "Add new patient" form.

## AWS Ownership

This spec owns:
- **DynamoDB: `pa_patients`** — Source-of-truth patient records with 2 GSIs matching the access patterns above.

This spec is written by:
- [Physician Dashboard](physician_dashboard.md) — Creates a new patient record when a physician submits the "Add new patient" form.

This spec is read by:
- [Agent Pipeline](agent_pipeline.md) — Step 0 hydration: reads the patient record by `patient_id` and writes a snapshot into the pa_request.
- [Physician Dashboard](physician_dashboard.md) — Patient-selection dropdown (by physician) and patient-name search.
- [Pipeline Dashboard](pipeline_dashboard.md) — Patient-name search for in-flight PA requests.

## DynamoDB Table Design (`pa_patients`)

**Key design:**
- PK: `patient_id` (e.g. `pat_001`)
- GSI-1 `by_physician`: PK `primary_physician_id` + SK `last_name` — "patients for this physician, alphabetical"
- GSI-2 `by_name`: PK `last_name` + SK `first_name` — "find patient by name"

## Patient Schema

```json
{
  "patient_id": "pat_001",
  "first_name": "Jane",
  "last_name": "Doe",
  "dob": "1985-03-12",
  "insurance_provider": "medi-cal",
  "insurance_id": "MC-9876543",
  "address": "123 Main St, Sacramento, CA 95814",
  "phone": "916-555-0100",
  "primary_physician_id": "doc_042",
  "created_at": "2026-04-19T14:28:00Z",
  "updated_at": "2026-04-19T14:28:00Z"
}
```

## Hydration Output (consumed by Agent Pipeline Step 0)

The fields copied into the pa_request's `patient` snapshot:

```json
{
  "patient_id": "pat_001",
  "first_name": "Jane",
  "last_name": "Doe",
  "dob": "1985-03-12",
  "insurance_provider": "medi-cal",
  "insurance_id": "MC-9876543",
  "address": "123 Main St, Sacramento, CA 95814",
  "phone": "916-555-0100"
}
```
