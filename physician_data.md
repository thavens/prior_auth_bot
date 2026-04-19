# Motivation

Physician information (name, NPI, specialty, phone, fax) is required on every completed PA form and accompanies every pa_request for dashboard display and routing. This feature provides the canonical physician record store that feeds the pipeline and powers dashboard physician selection/search. For the hackathon demo, physicians are seeded with synthetic data — there is no physician CRUD surface in the application.

# Requirement

This feature owns the storage of physician records and exposes read access for pipeline hydration and dashboard selection/search.

A new pa_request hydrates a snapshot of the physician's fields at pipeline start (see [Agent Pipeline](agent_pipeline.md) Step 0). Downstream pipeline steps read the snapshot on the pa_request record, not this table.

## Access Patterns

1. Fetch a physician by `physician_id` — pipeline hydration at request creation.
2. Search physicians by last name — dashboard "who is submitting" selector.
3. Lookup by NPI — standard healthcare directory lookup.

## AWS Ownership

This spec owns:
- **DynamoDB: `pa_physicians`** — Source-of-truth physician records with 2 GSIs matching the access patterns above.

This spec is read by:
- [Agent Pipeline](agent_pipeline.md) — Step 0 hydration: reads the physician record by `physician_id` and writes a snapshot into the pa_request.
- [Physician Dashboard](physician_dashboard.md) — Physician selector ("select which doctor is making the request").
- [Pipeline Dashboard](pipeline_dashboard.md) — Physician display on PA records.

## DynamoDB Table Design (`pa_physicians`)

**Key design:**
- PK: `physician_id` (e.g. `doc_042`)
- GSI-1 `by_name`: PK `last_name` + SK `first_name` — dashboard physician selector and search
- GSI-2 `by_npi`: PK `npi` — standard NPI lookup

## Physician Schema

```json
{
  "physician_id": "doc_042",
  "first_name": "Robert",
  "last_name": "Chen",
  "npi": "1234567890",
  "specialty": "Oncology",
  "phone": "916-555-0200",
  "fax": "916-555-0201",
  "created_at": "2026-04-01T09:00:00Z",
  "updated_at": "2026-04-01T09:00:00Z"
}
```

## Hydration Output (consumed by Agent Pipeline Step 0)

The fields copied into the pa_request's `physician` snapshot:

```json
{
  "physician_id": "doc_042",
  "first_name": "Robert",
  "last_name": "Chen",
  "npi": "1234567890",
  "specialty": "Oncology",
  "phone": "916-555-0200",
  "fax": "916-555-0201"
}
```
