"""Unit tests for PDFFormWriter.generate_label() in lambdas/shared/pdf_utils.py."""

import re
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Make the shared layer importable without installing it as a package.
# ---------------------------------------------------------------------------
_LAMBDAS_DIR = str(Path(__file__).resolve().parents[2] / "lambdas")
_SHARED_DIR = str(Path(__file__).resolve().parents[2] / "lambdas" / "shared")
for _p in (_LAMBDAS_DIR, _SHARED_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from pdf_utils import PDFFormWriter  # noqa: E402


class TestGenerateLabel:
    """Tests for PDFFormWriter.generate_label()."""

    # Expected pattern: pa_{patient_id}_{treatment_code}_{integer_timestamp}.pdf
    LABEL_PATTERN = re.compile(r"^pa_.+_.+_\d+\.pdf$")

    def test_basic_format(self):
        """Label should follow pa_{patient_id}_{treatment_code}_{timestamp}.pdf."""
        label = PDFFormWriter.generate_label("P001", "RX327361")
        assert self.LABEL_PATTERN.match(label), f"Label '{label}' does not match expected format"

    def test_contains_patient_id(self):
        label = PDFFormWriter.generate_label("PATIENT123", "CODE456")
        assert "PATIENT123" in label

    def test_contains_treatment_code(self):
        label = PDFFormWriter.generate_label("P001", "HUMIRA40MG")
        assert "HUMIRA40MG" in label

    def test_ends_with_pdf(self):
        label = PDFFormWriter.generate_label("P001", "RX001")
        assert label.endswith(".pdf")

    def test_starts_with_pa_prefix(self):
        label = PDFFormWriter.generate_label("P001", "RX001")
        assert label.startswith("pa_")

    def test_timestamp_is_integer_epoch(self):
        """The timestamp portion should be a valid integer (epoch seconds)."""
        label = PDFFormWriter.generate_label("P001", "RX001")
        # Extract the timestamp: everything between the last _ and .pdf
        timestamp_str = label.rsplit("_", 1)[-1].replace(".pdf", "")
        timestamp = int(timestamp_str)
        # Should be a reasonable epoch (after 2024-01-01)
        assert timestamp > 1_704_067_200

    def test_timestamp_reflects_current_time(self):
        """Timestamp should be close to the current epoch time."""
        before = int(time.time())
        label = PDFFormWriter.generate_label("P001", "RX001")
        after = int(time.time())

        timestamp_str = label.rsplit("_", 1)[-1].replace(".pdf", "")
        timestamp = int(timestamp_str)
        assert before <= timestamp <= after

    @patch("pdf_utils.time")
    def test_deterministic_with_mocked_time(self, mock_time):
        """With a fixed timestamp, the label should be fully deterministic."""
        mock_time.time.return_value = 1700000000
        label = PDFFormWriter.generate_label("P001", "RX001")
        assert label == "pa_P001_RX001_1700000000.pdf"

    # ---------------------------------------------------------------
    # Special characters in IDs
    # ---------------------------------------------------------------

    def test_slashes_replaced_with_underscores(self):
        """Forward slashes in patient_id or treatment_code should be sanitized."""
        label = PDFFormWriter.generate_label("P/001", "RX/327")
        assert "/" not in label
        assert "P_001" in label
        assert "RX_327" in label

    def test_spaces_replaced_with_underscores(self):
        """Spaces should be replaced with underscores."""
        label = PDFFormWriter.generate_label("P 001", "RX 327")
        assert " " not in label
        assert "P_001" in label
        assert "RX_327" in label

    def test_mixed_special_characters(self):
        """Both slashes and spaces in the same ID should be handled."""
        label = PDFFormWriter.generate_label("P/00 1", "RX/ 327")
        assert "/" not in label
        assert " " not in label
        assert self.LABEL_PATTERN.match(label)

    def test_already_clean_ids_unchanged(self):
        """IDs without special characters should pass through as-is."""
        label = PDFFormWriter.generate_label("P001", "RX327361")
        parts = label.split("_")
        # pa, P001, RX327361, <timestamp>.pdf
        assert parts[0] == "pa"
        assert parts[1] == "P001"
        assert parts[2] == "RX327361"

    def test_numeric_ids(self):
        """Purely numeric IDs should work fine."""
        label = PDFFormWriter.generate_label("12345", "67890")
        assert "12345" in label
        assert "67890" in label
        assert self.LABEL_PATTERN.match(label)

    def test_empty_strings(self):
        """Empty patient_id and treatment_code should still produce a valid label."""
        label = PDFFormWriter.generate_label("", "")
        assert label.startswith("pa_")
        assert label.endswith(".pdf")

    def test_long_ids(self):
        """Very long IDs should be handled without error."""
        long_patient = "P" * 200
        long_code = "RX" * 100
        label = PDFFormWriter.generate_label(long_patient, long_code)
        assert long_patient in label
        assert long_code in label
        assert self.LABEL_PATTERN.match(label)

    @patch("pdf_utils.time")
    def test_different_inputs_produce_different_labels(self, mock_time):
        """Different inputs should produce different labels (same timestamp)."""
        mock_time.time.return_value = 1700000000
        label_a = PDFFormWriter.generate_label("P001", "RX001")
        label_b = PDFFormWriter.generate_label("P002", "RX002")
        assert label_a != label_b

    def test_hyphenated_ids(self):
        """Hyphens (common in medical IDs) should be preserved."""
        label = PDFFormWriter.generate_label("P-001-A", "RX-327-361")
        assert "P-001-A" in label
        assert "RX-327-361" in label
