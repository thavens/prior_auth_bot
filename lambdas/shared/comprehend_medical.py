"""AWS Comprehend Medical client for medical entity extraction."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

import boto3

from shared.config import cfg
from shared.models import Treatment, TreatmentType

logger = logging.getLogger(__name__)

# Maximum text length accepted by Comprehend Medical APIs (UTF-8 bytes).
_MAX_TEXT_SIZE = 20_000


class ComprehendMedicalClient:
    """Wrapper around Amazon Comprehend Medical for medical NLP."""

    def __init__(self, region: Optional[str] = None) -> None:
        self._region = region or cfg.AWS_REGION
        self._client = boto3.client("comprehendmedical", region_name=self._region)

    # ------------------------------------------------------------------
    # Low-level API wrappers
    # ------------------------------------------------------------------

    def infer_rxnorm(self, text: str) -> list[dict[str, Any]]:
        """Call InferRxNorm and return the list of RxNorm entities."""

        try:
            response = self._client.infer_rx_norm(Text=text[:_MAX_TEXT_SIZE])
            return response.get("Entities", [])
        except Exception:
            logger.exception("InferRxNorm call failed")
            raise

    def infer_snomed(self, text: str) -> list[dict[str, Any]]:
        """Call InferSNOMEDCT and return the list of SNOMED-CT entities."""

        try:
            response = self._client.infer_snomedct(Text=text[:_MAX_TEXT_SIZE])
            return response.get("Entities", [])
        except Exception:
            logger.exception("InferSNOMEDCT call failed")
            raise

    def detect_entities(self, text: str) -> list[dict[str, Any]]:
        """Call DetectEntitiesV2 and return the list of detected entities."""

        try:
            response = self._client.detect_entities_v2(Text=text[:_MAX_TEXT_SIZE])
            return response.get("Entities", [])
        except Exception:
            logger.exception("DetectEntitiesV2 call failed")
            raise

    # ------------------------------------------------------------------
    # High-level aggregation
    # ------------------------------------------------------------------

    def extract_all_entities(self, text: str) -> dict[str, list[dict[str, Any]]]:
        """Run all three extraction APIs and merge into a single dict.

        Returns::

            {
                "medications": [...],   # from InferRxNorm + DetectEntitiesV2
                "conditions": [...],    # from DetectEntitiesV2
                "procedures": [...],    # from InferSNOMEDCT + DetectEntitiesV2
            }
        """

        rxnorm_entities = self.infer_rxnorm(text)
        snomed_entities = self.infer_snomed(text)
        detect_entities = self.detect_entities(text)

        medications: list[dict[str, Any]] = []
        conditions: list[dict[str, Any]] = []
        procedures: list[dict[str, Any]] = []

        # RxNorm entities are medications by definition.
        for entity in rxnorm_entities:
            medications.append({
                "text": entity.get("Text", ""),
                "score": entity.get("Score", 0.0),
                "rxnorm_concepts": entity.get("RxNormConcepts", []),
                "attributes": entity.get("Attributes", []),
                "source": "InferRxNorm",
            })

        # SNOMED-CT entities can be conditions or procedures.
        for entity in snomed_entities:
            category = entity.get("Category", "")
            entry = {
                "text": entity.get("Text", ""),
                "score": entity.get("Score", 0.0),
                "snomed_concepts": entity.get("SNOMEDCTConcepts", []),
                "attributes": entity.get("Attributes", []),
                "source": "InferSNOMEDCT",
            }
            if category == "MEDICAL_CONDITION":
                conditions.append(entry)
            elif category in ("TEST_TREATMENT_PROCEDURE", "PROCEDURE"):
                procedures.append(entry)
            else:
                # Best-effort: fall back to conditions for unrecognized categories.
                conditions.append(entry)

        # DetectEntitiesV2 gives us a broader sweep.
        for entity in detect_entities:
            category = entity.get("Category", "")
            entry = {
                "text": entity.get("Text", ""),
                "score": entity.get("Score", 0.0),
                "type": entity.get("Type", ""),
                "traits": entity.get("Traits", []),
                "attributes": entity.get("Attributes", []),
                "source": "DetectEntitiesV2",
            }
            if category == "MEDICATION":
                medications.append(entry)
            elif category == "MEDICAL_CONDITION":
                conditions.append(entry)
            elif category == "TEST_TREATMENT_PROCEDURE":
                procedures.append(entry)

        return {
            "medications": medications,
            "conditions": conditions,
            "procedures": procedures,
        }

    # ------------------------------------------------------------------
    # Conversion to domain models
    # ------------------------------------------------------------------

    def text_to_treatments(self, text: str) -> list[Treatment]:
        """Extract entities from free text and convert them into Treatment models.

        Each unique medication, procedure, or therapy becomes a separate
        ``Treatment``.  Duplicates (by name) are merged, keeping the
        highest-confidence code.
        """

        entities = self.extract_all_entities(text)
        seen_names: dict[str, Treatment] = {}

        # --- Medications ---------------------------------------------------
        for med in entities["medications"]:
            name = med["text"].strip()
            key = name.lower()
            if key in seen_names:
                continue

            rxnorm_code = self._best_rxnorm_code(med)
            attributes = self._attributes_map(med.get("attributes", []))

            seen_names[key] = Treatment(
                treatment_id=str(uuid.uuid4()),
                treatment_type=TreatmentType.MEDICATION,
                name=name,
                rxnorm_code=rxnorm_code,
                dosage=attributes.get("DOSAGE"),
                frequency=attributes.get("FREQUENCY"),
                duration=attributes.get("DURATION"),
                icd10_codes=[],
                confidence_score=float(med.get("score", 0.0)),
            )

        # --- Procedures / surgeries ----------------------------------------
        for proc in entities["procedures"]:
            name = proc["text"].strip()
            key = name.lower()
            if key in seen_names:
                continue

            snomed_code = self._best_snomed_code(proc)
            treatment_type = self._classify_procedure(proc)

            seen_names[key] = Treatment(
                treatment_id=str(uuid.uuid4()),
                treatment_type=treatment_type,
                name=name,
                snomed_code=snomed_code,
                icd10_codes=[],
                confidence_score=float(proc.get("score", 0.0)),
            )

        # --- Conditions -> associate ICD-10 codes with existing treatments --
        icd10_codes: list[str] = []
        for cond in entities["conditions"]:
            for concept in cond.get("snomed_concepts", []):
                code = concept.get("Code", "")
                if code:
                    icd10_codes.append(code)

        if icd10_codes:
            for treatment in seen_names.values():
                treatment.icd10_codes = list(set(icd10_codes))

        return list(seen_names.values())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _best_rxnorm_code(entity: dict[str, Any]) -> str | None:
        """Return the highest-scoring RxNorm concept code, if any."""

        concepts = entity.get("rxnorm_concepts", [])
        if not concepts:
            return None
        best = max(concepts, key=lambda c: c.get("Score", 0.0))
        return best.get("Code")

    @staticmethod
    def _best_snomed_code(entity: dict[str, Any]) -> str | None:
        """Return the highest-scoring SNOMED-CT concept code, if any."""

        concepts = entity.get("snomed_concepts", [])
        if not concepts:
            return None
        best = max(concepts, key=lambda c: c.get("Score", 0.0))
        return best.get("Code")

    @staticmethod
    def _attributes_map(attributes: list[dict[str, Any]]) -> dict[str, str]:
        """Convert Comprehend Medical attributes list to a simple dict."""

        result: dict[str, str] = {}
        for attr in attributes:
            attr_type = attr.get("Type", attr.get("type", ""))
            attr_text = attr.get("Text", attr.get("text", ""))
            if attr_type and attr_text:
                result[attr_type.upper()] = attr_text
        return result

    @staticmethod
    def _classify_procedure(entity: dict[str, Any]) -> TreatmentType:
        """Heuristically classify a procedure entity as SURGERY or THERAPY."""

        text_lower = entity.get("text", "").lower()
        surgical_keywords = {"surgery", "surgical", "excision", "resection",
                             "implant", "transplant", "arthroplasty", "ectomy",
                             "otomy", "ostomy"}
        for keyword in surgical_keywords:
            if keyword in text_lower:
                return TreatmentType.SURGERY
        return TreatmentType.THERAPY
