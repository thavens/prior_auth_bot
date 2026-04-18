"""PDF form reading and writing utilities for prior-authorization forms."""

from __future__ import annotations

import io
import logging
import time
from typing import Any

from PyPDF2 import PdfReader
from pdfrw import PdfReader as PdfrwReader, PdfWriter as PdfrwWriter, PdfDict, PdfName

from shared.models import FieldType, FormField

logger = logging.getLogger(__name__)

# Mapping from PDF AcroForm field types to our FieldType enum.
_PDF_FIELD_TYPE_MAP: dict[str, FieldType] = {
    "/Tx": FieldType.TEXT,
    "/Btn": FieldType.CHECKBOX,
    "/Ch": FieldType.DROPDOWN,
}


class PDFFormReader:
    """Reads AcroForm fields from a PDF and converts them to FormField models."""

    @staticmethod
    def extract_fields(pdf_bytes: bytes) -> list[FormField]:
        """Parse a PDF from raw bytes and return its interactive form fields.

        Fields that cannot be parsed are silently skipped with a warning.
        """

        reader = PdfReader(io.BytesIO(pdf_bytes))
        fields = reader.get_fields()

        if not fields:
            logger.warning("PDF contains no AcroForm fields")
            return []

        result: list[FormField] = []
        for field_name, field_obj in fields.items():
            try:
                form_field = PDFFormReader._convert_field(field_name, field_obj)
                if form_field is not None:
                    result.append(form_field)
            except Exception:
                logger.warning("Skipping unparseable field: %s", field_name, exc_info=True)

        return result

    @staticmethod
    def _convert_field(
        field_name: str,
        field_obj: Any,
    ) -> FormField | None:
        """Convert a single PyPDF2 field dict into a ``FormField``."""

        # Determine field type from /FT key.
        raw_type = field_obj.get("/FT", "/Tx")
        field_type = _PDF_FIELD_TYPE_MAP.get(raw_type, FieldType.TEXT)

        # For date fields we rely on the field name as a heuristic since PDF
        # does not have a native date type.
        name_lower = field_name.lower()
        if any(kw in name_lower for kw in ("date", "dob", "birth")):
            field_type = FieldType.DATE

        # Extract tooltip / description.
        description = field_obj.get("/TU", "") or field_obj.get("/T", field_name) or ""

        # Determine if the field is required (Ff flag bit 2).
        flags = int(field_obj.get("/Ff", 0))
        required = bool(flags & (1 << 1))

        # Extract options for dropdown / choice fields.
        options: list[str] | None = None
        if field_type == FieldType.DROPDOWN:
            raw_options = field_obj.get("/Opt")
            if raw_options:
                options = [str(opt) for opt in raw_options]

        return FormField(
            field_name=field_name,
            field_type=field_type,
            description=str(description),
            required=required,
            options=options,
        )


class PDFFormWriter:
    """Fills interactive form fields in a PDF and returns the modified bytes."""

    @staticmethod
    def fill_fields(pdf_bytes: bytes, field_values: dict[str, str]) -> bytes:
        """Write values into AcroForm fields and return the resulting PDF bytes.

        Uses *pdfrw* for writing because it preserves the original PDF
        structure better than PyPDF2 for form-fill use cases.
        """

        reader = PdfrwReader(fdata=pdf_bytes)
        pages = reader.pages

        for page in pages:
            annotations = page.get("/Annots")
            if not annotations:
                continue

            for annotation in annotations:
                field = annotation.get("/T")
                if field is None:
                    continue

                # pdfrw wraps strings in parentheses; strip them.
                field_name = field.strip("()")

                if field_name not in field_values:
                    continue

                value = field_values[field_name]
                field_type = annotation.get("/FT")

                if field_type == "/Btn":
                    # Checkbox / radio: set the appearance state.
                    if value.lower() in ("yes", "true", "on", "1"):
                        annotation.update(
                            PdfDict(
                                V=PdfName("Yes"),
                                AS=PdfName("Yes"),
                            )
                        )
                    else:
                        annotation.update(
                            PdfDict(
                                V=PdfName("Off"),
                                AS=PdfName("Off"),
                            )
                        )
                else:
                    # Text, dropdown, or date: set the value string.
                    annotation.update(
                        PdfDict(V=f"({value})", AP="")
                    )

                # Set the NeedAppearances flag so viewers re-render the field.
                annotation.update(PdfDict(Ff=1))

        # Ensure the reader's AcroForm dictionary has NeedAppearances.
        if reader.Root.AcroForm:
            reader.Root.AcroForm.update(
                PdfDict(NeedAppearances=PdfName("true"))
            )

        writer = PdfrwWriter()
        writer.trailer = reader
        output = io.BytesIO()
        writer.write(output)
        return output.getvalue()

    @staticmethod
    def generate_label(patient_id: str, treatment_code: str) -> str:
        """Generate a deterministic, traceable filename for a filled PA form.

        Format: ``pa_{patient_id}_{treatment_code}_{epoch_timestamp}.pdf``
        """

        timestamp = int(time.time())
        safe_patient = patient_id.replace("/", "_").replace(" ", "_")
        safe_code = treatment_code.replace("/", "_").replace(" ", "_")
        return f"pa_{safe_patient}_{safe_code}_{timestamp}.pdf"
