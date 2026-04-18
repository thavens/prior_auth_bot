"""Step 2 -- Determine which treatments require prior authorization.

Invoked by Step Functions with extracted treatments and patient data.
Checks a DynamoDB cache first; on a miss, uses Bedrock to determine PA
requirements.  Results are cached with a 7-day TTL.
"""

from __future__ import annotations

import logging
from typing import Any

from shared.config import Config
from shared.models import Patient, Treatment, PARequirement
from shared.bedrock_client import BedrockClient
from shared.dynamo_client import DynamoClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

cfg = Config()

bedrock = BedrockClient()
dynamo = DynamoClient()

_CACHE_TTL_DAYS = 7


def _treatment_code(treatment: Treatment) -> str:
    """Derive a cache key code for a treatment.

    Prefer RxNorm or SNOMED codes when available; fall back to a
    normalised version of the treatment name.
    """
    if treatment.rxnorm_code:
        return f"rx:{treatment.rxnorm_code}"
    if treatment.snomed_code:
        return f"sn:{treatment.snomed_code}"
    return f"name:{treatment.name.lower().replace(' ', '_')}"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Check PA requirements for each treatment.

    Expected event::

        {
            "treatments": [ { ... }, ... ],
            "patient": { ... },
            "transcript_text": "..."
        }
    """

    patient_data: dict[str, Any] = event["patient"]
    patient = Patient(**patient_data)
    provider_id: str = patient.insurance_provider

    raw_treatments: list[dict[str, Any]] = event["treatments"]
    treatments = [Treatment(**t) for t in raw_treatments]

    logger.info(
        "Checking PA requirements for %d treatment(s), provider=%s",
        len(treatments),
        provider_id,
    )

    # Partition treatments into cache-hits and cache-misses.
    cached_requirements: list[PARequirement] = []
    uncached_treatments: list[Treatment] = []

    for treatment in treatments:
        code = _treatment_code(treatment)
        cached = dynamo.get_cache(
            table_name=cfg.CACHE_TABLE,
            provider_id=provider_id,
            treatment_code=code,
        )

        if cached is not None:
            logger.info("Cache hit for %s / %s", provider_id, code)
            # Reconstruct PARequirement from the cached dict.
            cached_req = PARequirement(
                treatment=treatment,
                pa_required=cached["pa_required"],
                requirements_text=cached.get("requirements_text", ""),
                provider_id=cached.get("provider_id", provider_id),
                source_url=cached.get("source_url", ""),
                cached=True,
            )
            cached_requirements.append(cached_req)
        else:
            logger.info("Cache miss for %s / %s", provider_id, code)
            uncached_treatments.append(treatment)

    # Call Bedrock for any uncached treatments.
    fresh_requirements: list[PARequirement] = []
    if uncached_treatments:
        provider_info = {
            "provider_id": provider_id,
            "provider_name": provider_id,
        }

        fresh_requirements = bedrock.determine_pa_requirements(
            treatments=uncached_treatments,
            patient=patient,
            provider_info=provider_info,
        )

        # Cache each fresh result.
        for req in fresh_requirements:
            code = _treatment_code(req.treatment)
            dynamo.put_cache(
                table_name=cfg.CACHE_TABLE,
                provider_id=provider_id,
                treatment_code=code,
                data={
                    "pa_required": req.pa_required,
                    "requirements_text": req.requirements_text,
                    "provider_id": req.provider_id,
                    "source_url": req.source_url,
                },
                ttl_days=_CACHE_TTL_DAYS,
            )
            logger.info(
                "Cached PA requirement for %s / %s (pa_required=%s)",
                provider_id,
                code,
                req.pa_required,
            )

    # Merge and filter to treatments that actually need PA.
    all_requirements = cached_requirements + fresh_requirements

    pa_required_treatments: list[dict[str, Any]] = []
    for req in all_requirements:
        if req.pa_required:
            pa_required_treatments.append({
                "treatment": req.treatment.model_dump(),
                "pa_required": req.pa_required,
                "requirements_text": req.requirements_text,
                "provider_id": req.provider_id,
                "source_url": req.source_url,
                "cached": req.cached,
            })

    logger.info(
        "%d of %d treatment(s) require prior authorization",
        len(pa_required_treatments),
        len(treatments),
    )

    return {
        "pa_required_treatments": pa_required_treatments,
        "patient": patient_data,
    }
