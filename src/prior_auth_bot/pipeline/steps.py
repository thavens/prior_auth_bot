import json
import uuid

from prior_auth_bot.models import (
    MedicalEntity,
    NormalizedConcept,
    SnomedConcept,
    EntityExtractionResult,
    TreatmentPAResult,
    PADeterminationResult,
    SelectedForm,
    FormSelectionResult,
    TreatmentInfo,
    DocumentPopulationInput,
    DocumentPopulationResult,
    MemoryRetrievalResult,
    SubmissionResult,
    Memory,
    Patient,
    Physician,
    EarlyMemoryContext,
)
from prior_auth_bot.services.search_service import SearchService
from prior_auth_bot.services.document_population import DocumentPopulationService
from prior_auth_bot.services.document_courier import EmailCourierService

TRANSCRIPT_CHAR_LIMIT = 100_000


def _get_block_text(block: dict, block_map: dict) -> str:
    parts = []
    for rel in block.get("Relationships", []):
        if rel["Type"] == "CHILD":
            for child_id in rel["Ids"]:
                child = block_map.get(child_id)
                if child and child.get("BlockType") == "WORD":
                    parts.append(child.get("Text", ""))
    return " ".join(parts)


def _extract_textract_descriptions(textract_data: dict) -> dict[str, str]:
    blocks = textract_data.get("Blocks", [])
    block_map = {b["Id"]: b for b in blocks}
    descriptions = {}
    for block in blocks:
        if block.get("BlockType") != "KEY_VALUE_SET":
            continue
        if "KEY" not in block.get("EntityTypes", []):
            continue
        key_text = _get_block_text(block, block_map)
        if not key_text:
            continue
        value_text = ""
        for rel in block.get("Relationships", []):
            if rel["Type"] == "VALUE":
                for vid in rel["Ids"]:
                    value_block = block_map.get(vid)
                    if value_block:
                        value_text = _get_block_text(value_block, block_map)
                        break
        descriptions[key_text] = value_text
    return descriptions


def _build_form_context(
    insurance_provider: str,
    search_service: SearchService,
    s3_client,
    textract_output_bucket: str,
) -> str:
    forms = search_service.search_forms(insurance_provider)
    if not forms:
        return "No prior authorization forms found for this provider."

    parts = []
    for form in forms:
        form_key = form["s3_key"]
        textract_key = form_key.rsplit(".", 1)[0] + ".json"
        try:
            textract_data = json.loads(
                s3_client.get_object(
                    Bucket=textract_output_bucket, Key=textract_key
                )["Body"].read()
            )
            field_descs = textract_data.get("FieldDescriptions", {})
            if field_descs:
                descriptions = {v: "" for v in field_descs.values() if v}
            else:
                descriptions = _extract_textract_descriptions(textract_data)
        except Exception:
            descriptions = {}

        field_lines = []
        for field_name, field_desc in descriptions.items():
            suffix = f" — {field_desc}" if field_desc else ""
            field_lines.append(f"    - {field_name}{suffix}")

        fields_block = "\n".join(field_lines) if field_lines else "    (no field descriptions available)"
        parts.append(f"  Form: {form['form_name']}\n  Fields:\n{fields_block}")

    return "\n\n".join(parts)


def step_1_entity_extraction(
    transcript_text: str,
    insurance_provider: str,
    search_service: SearchService,
    s3_client,
    textract_output_bucket: str,
    bedrock_client,
    model_id: str,
    memory_context: EarlyMemoryContext | None = None,
) -> EntityExtractionResult:
    text = transcript_text[:TRANSCRIPT_CHAR_LIMIT]

    form_context = _build_form_context(
        insurance_provider, search_service, s3_client, textract_output_bucket
    )

    memory_block = ""
    if memory_context:
        all_memories = (memory_context.provider_memories + memory_context.treatment_memories)
        if all_memories:
            lines = []
            for m in all_memories:
                tags_str = ", ".join(m.tags) if m.tags else "none"
                lines.append(
                    f"- {m.advice} (approved {m.success_count} times, tags: [{tags_str}])"
                )
            memory_block = (
                "\nINSIGHTS FROM PAST APPLICATIONS WITH THIS PROVIDER:\n"
                + "\n".join(lines) + "\n"
                "Use these insights to focus extraction on data points important for this provider.\n"
            )

    prompt = (
        "You are a medical entity extraction specialist for prior authorization applications. "
        "Extract all medically relevant entities from the following appointment transcript.\n"
        "\n"
        "IMPORTANT: You have access to the prior authorization forms that will be filled out. "
        "Focus your extraction on information that these forms actually require. "
        "Extract entities that correspond to data needed by the form fields below.\n"
        "\n"
        f"AVAILABLE PA FORMS AND THEIR FIELDS:\n{form_context}\n"
        f"{memory_block}"
        "\n"
        f"APPOINTMENT TRANSCRIPT:\n{text}\n"
        "\n"
        'Extract entities into a JSON object with a single key "entities" '
        "containing an array of objects. Each entity object must have:\n"
        '- entity_id: sequential string like "ent_000", "ent_001", etc.\n'
        '- category: one of "MEDICATION", "TEST_TREATMENT_PROCEDURE", or "PROTECTED_HEALTH_INFORMATION"\n'
        "- text: the entity text as mentioned or as best described for the form\n"
        '- normalized: object with "rxnorm_concept" (RxNorm code string) and "rxnorm_description" '
        "(full drug description) if the entity is a medication, otherwise null\n"
        '- snomed_concepts: array of objects with "code" (SNOMED-CT code) and "description" '
        "for procedures and conditions, otherwise empty array\n"
        '- traits: array of strings like "NEGATION" (if negated) or "PAST_HISTORY" (if historical), '
        "otherwise empty array\n"
        "- confidence: float 0.0-1.0 indicating how confident you are this entity is relevant "
        "for prior authorization\n"
        "\n"
        "Guidelines:\n"
        "- Prioritize entities that match form field requirements (medications, diagnoses, procedures, "
        "patient identifiers)\n"
        "- For medications, provide accurate RxNorm codes when you can identify them\n"
        "- For procedures and diagnoses, provide SNOMED-CT codes when you can identify them\n"
        "- Mark entities with NEGATION trait if the transcript indicates they were ruled out or not given\n"
        "- Mark entities with PAST_HISTORY if they are historical context rather than current treatment\n"
        "- Include dosage, frequency, and route information as part of medication entity text when available\n"
        "- Extract patient demographic information mentioned in the transcript (PHI category)\n"
        "\n"
        "JSON:"
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    })
    response = bedrock_client.invoke_model(
        modelId=model_id,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    result = json.loads(response["body"].read())
    text_resp = result["content"][0]["text"]
    if "```json" in text_resp:
        text_resp = text_resp.split("```json")[1].split("```")[0]
    elif "```" in text_resp:
        text_resp = text_resp.split("```")[1].split("```")[0]
    data = json.loads(text_resp.strip())

    raw_entities = data.get("entities", data) if isinstance(data, dict) else data

    entities: list[MedicalEntity] = []
    for item in raw_entities:
        normalized = None
        norm_data = item.get("normalized")
        if norm_data and isinstance(norm_data, dict):
            normalized = NormalizedConcept(
                rxnorm_concept=norm_data.get("rxnorm_concept", ""),
                rxnorm_description=norm_data.get("rxnorm_description", ""),
            )

        snomed_concepts: list[SnomedConcept] = []
        for sc in item.get("snomed_concepts", []):
            snomed_concepts.append(SnomedConcept(
                code=sc.get("code", ""),
                description=sc.get("description", ""),
            ))

        entities.append(MedicalEntity(
            entity_id=item.get("entity_id", f"ent_{len(entities):03d}"),
            category=item.get("category", ""),
            text=item.get("text", ""),
            normalized=normalized,
            snomed_concepts=snomed_concepts,
            traits=item.get("traits", []),
            confidence=item.get("confidence", 0.0),
        ))

    return EntityExtractionResult(entities=entities)


def step_2_pa_determination(
    entities: EntityExtractionResult,
    patient_data: dict,
    search_service: SearchService,
    bedrock_client,
    model_id: str,
    memory_context: EarlyMemoryContext | None = None,
) -> PADeterminationResult:
    insurance_provider = patient_data.get("insurance_provider", "")

    scraped_parts = []
    seen_treatments = set()
    for ent in entities.entities:
        if ent.text.lower() not in seen_treatments:
            seen_treatments.add(ent.text.lower())
            content = search_service.check_pa_requirements(insurance_provider, ent.text)
            if content:
                scraped_parts.append(f"[{ent.text}]: {content[:2000]}")

    has_provider_data = bool(scraped_parts)

    entity_lines = "\n".join(
        f"- {e.entity_id}: {e.text} ({e.category})" for e in entities.entities
    )
    if has_provider_data:
        scraped_block = "\n".join(scraped_parts)
    else:
        scraped_block = (
            "No provider PA information available. IMPORTANT: When provider policy "
            "data is unavailable, you MUST default to requires_pa=true for all "
            "MEDICATION and TEST_TREATMENT_PROCEDURE entities. Submitting an "
            "unnecessary PA is far less harmful than skipping a required one."
        )

    memory_block = ""
    if memory_context:
        all_memories = (memory_context.provider_memories + memory_context.treatment_memories)
        if all_memories:
            lines = []
            for m in all_memories:
                lines.append(
                    f"- {m.advice} (success_count: {m.success_count}, outcome: {m.outcome or 'n/a'})"
                )
            memory_block = (
                "\nHISTORICAL PATTERNS FOR THIS PROVIDER:\n"
                + "\n".join(lines)
                + "\nUse these patterns to inform your PA determination.\n"
            )

    prompt = (
        "Given the following medical entities extracted from a doctor's appointment, "
        "determine which require prior authorization from the patient's insurance provider.\n"
        "\n"
        f"Patient Insurance: {insurance_provider}\n"
        "\n"
        f"Entities:\n{entity_lines}\n"
        "\n"
        f"Provider PA Information:\n{scraped_block}\n"
        f"{memory_block}"
        "\n"
        "For each entity, respond with a JSON array of objects with fields:\n"
        "- entity_id: the entity ID\n"
        "- treatment_text: the treatment name\n"
        "- category: the entity category\n"
        "- requires_pa: true/false\n"
        "- pa_reason: why PA is/isn't needed (brief)\n"
        "\n"
        "JSON:"
    )

    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    })
    response = bedrock_client.invoke_model(
        modelId=model_id,
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
    items = json.loads(text.strip())

    requiring = []
    not_requiring = []
    pa_relevant_categories = {"MEDICATION", "TEST_TREATMENT_PROCEDURE"}
    for item in items:
        forced = False
        if not has_provider_data and item["category"] in pa_relevant_categories and not item["requires_pa"]:
            forced = True
        treatment = TreatmentPAResult(
            entity_id=item["entity_id"],
            treatment_text=item["treatment_text"],
            category=item["category"],
            requires_pa=item["requires_pa"] or forced,
            pa_reason=item.get("pa_reason", "") if not forced else "No provider data available — defaulting to PA required",
            provider_name=insurance_provider,
        )
        if treatment.requires_pa:
            requiring.append(treatment)
        else:
            not_requiring.append(treatment)

    return PADeterminationResult(
        treatments_requiring_pa=requiring,
        treatments_not_requiring_pa=not_requiring,
    )


def step_3_form_selection(
    treatments: list[TreatmentPAResult],
    patient_data: dict,
    search_service: SearchService,
    bedrock_client,
    model_id: str,
) -> FormSelectionResult:
    selected_forms: list[SelectedForm] = []

    for treatment in treatments:
        provider = treatment.provider_name or patient_data.get("insurance_provider", "")
        forms = search_service.search_forms(provider)
        if not forms:
            continue

        if len(forms) == 1:
            chosen = forms[0]
        else:
            form_lines = "\n".join(
                f"- {f['form_name']} (s3_key: {f['s3_key']})" for f in forms
            )
            prompt = (
                f"Select the best prior authorization form for the treatment: {treatment.treatment_text} ({treatment.category})\n"
                f"PA Reason: {treatment.pa_reason}\n"
                "\n"
                f"Available forms:\n{form_lines}\n"
                "\n"
                "Respond with ONLY the s3_key of the best matching form."
            )
            body = json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 256,
                "messages": [{"role": "user", "content": prompt}],
            })
            response = bedrock_client.invoke_model(
                modelId=model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(response["body"].read())
            chosen_key = result["content"][0]["text"].strip()
            chosen = next((f for f in forms if f["s3_key"] == chosen_key), forms[0])

        form_key = chosen["s3_key"]
        textract_key = form_key.rsplit(".", 1)[0] + ".json"

        selected_forms.append(SelectedForm(
            treatment_entity_id=treatment.entity_id,
            form_s3_key=form_key,
            textract_s3_key=textract_key,
            form_name=chosen["form_name"],
            provider_name=chosen["provider_name"],
        ))

    return FormSelectionResult(selected_forms=selected_forms)


def step_4_memory_retrieval(
    treatments: list[TreatmentPAResult],
    search_service: SearchService,
) -> MemoryRetrievalResult:
    seen: dict[str, Memory] = {}

    for treatment in treatments:
        result = search_service.search_memories(treatment.provider_name, treatment.treatment_text)
        for memory in result.memories:
            if memory.memory_id not in seen:
                seen[memory.memory_id] = memory

    return MemoryRetrievalResult(memories=list(seen.values()))


def step_5_document_population(
    doc_pop_service: DocumentPopulationService,
    pop_input: DocumentPopulationInput,
) -> DocumentPopulationResult:
    return doc_pop_service.populate_form(pop_input)


def step_6_document_submission(
    courier_service: EmailCourierService,
    patient: Patient,
    physician: Physician,
    treatment_text: str,
    insurance_provider: str,
    insurance_id: str,
    completed_form_s3_key: str,
) -> SubmissionResult:
    return courier_service.send(
        patient=patient,
        physician=physician,
        treatment_text=treatment_text,
        insurance_provider=insurance_provider,
        insurance_id=insurance_id,
        completed_form_s3_key=completed_form_s3_key,
    )
