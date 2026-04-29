"""
tests/unit/test_errors.py
==========================
Unit tests for errors.py — every custom exception class.

Covers:
  - Correct message and context stored on each exception.
  - __str__ includes context key=value pairs.
  - Inheritance hierarchy is correct (isinstance checks).
  - Subclass-specific attributes are set properly.
"""

import pytest

from errors import (
    AttendanceProcessorError,
    ClassificationError,
    ExtractionError,
    InvalidClockError,
    LowConfidenceError,
    MissingRendererError,
    NoRowsError,
    OCRError,
    OutputDirectoryError,
    ParseError,
    PDFOpenError,
    RenderingError,
    RulesViolationError,
    TransformationError,
    UnknownReportTypeError,
)
from pathlib import Path


# ---------------------------------------------------------------------------
# Root exception
# ---------------------------------------------------------------------------

class TestAttendanceProcessorError:
    def test_message_stored(self):
        exc = AttendanceProcessorError("something went wrong")
        assert exc.message == "something went wrong"
        assert str(exc) == "something went wrong"

    def test_context_stored(self):
        exc = AttendanceProcessorError("oops", context={"key": "val"})
        assert exc.context == {"key": "val"}

    def test_str_includes_context(self):
        exc = AttendanceProcessorError("oops", context={"a": 1, "b": "x"})
        s = str(exc)
        assert "a=" in s
        assert "b=" in s

    def test_empty_context_default(self):
        exc = AttendanceProcessorError("msg")
        assert exc.context == {}


# ---------------------------------------------------------------------------
# Ingestion layer
# ---------------------------------------------------------------------------

class TestPDFOpenError:
    def test_attributes(self):
        p = Path("/tmp/report.pdf")
        exc = PDFOpenError(p, reason="corrupt")
        assert exc.pdf_path == p
        assert "corrupt" in str(exc)
        assert isinstance(exc, ExtractionError)
        assert isinstance(exc, AttendanceProcessorError)

    def test_reason_optional(self):
        exc = PDFOpenError(Path("x.pdf"))
        assert isinstance(exc, PDFOpenError)


class TestOCRError:
    def test_attributes(self):
        p = Path("report.pdf")
        exc = OCRError(p, page_index=2, reason="timeout")
        assert exc.pdf_path == p
        assert exc.page_index == 2
        assert "2" in str(exc)
        assert isinstance(exc, ExtractionError)


# ---------------------------------------------------------------------------
# Classification layer
# ---------------------------------------------------------------------------

class TestLowConfidenceError:
    def test_attributes(self):
        exc = LowConfidenceError(score_a=1.0, score_b=1.0, confidence=0.0, threshold=0.25)
        assert exc.score_a == 1.0
        assert exc.score_b == 1.0
        assert exc.confidence == 0.0
        assert exc.threshold == 0.25
        assert isinstance(exc, ClassificationError)

    def test_str_contains_percentage(self):
        exc = LowConfidenceError(0.0, 0.0, 0.1, 0.25)
        assert "%" in str(exc)


# ---------------------------------------------------------------------------
# Parser layer
# ---------------------------------------------------------------------------

class TestParseError:
    def test_basic(self):
        exc = ParseError("bad field", field="clock", snippet="08:00 07:00")
        assert exc.field == "clock"
        assert "clock" in str(exc)
        assert isinstance(exc, AttendanceProcessorError)

    def test_snippet_truncated_to_80(self):
        exc = ParseError("msg", snippet="x" * 100)
        assert len(exc.snippet) == 100  # attribute stores original
        assert len(exc.context["near"]) <= 80


class TestNoRowsError:
    def test_attributes(self):
        exc = NoRowsError("TYPE_A")
        assert exc.report_type == "TYPE_A"
        assert isinstance(exc, ParseError)


class TestInvalidClockError:
    def test_attributes(self):
        exc = InvalidClockError("TYPE_B")
        assert exc.report_type == "TYPE_B"
        assert isinstance(exc, ParseError)


# ---------------------------------------------------------------------------
# Transformation layer
# ---------------------------------------------------------------------------

class TestUnknownReportTypeError:
    def test_attributes(self):
        exc = UnknownReportTypeError("TYPE_X", ["TYPE_A", "TYPE_B"])
        assert exc.report_type == "TYPE_X"
        assert exc.registry_keys == ["TYPE_A", "TYPE_B"]
        assert isinstance(exc, TransformationError)

    def test_str_contains_type(self):
        exc = UnknownReportTypeError("TYPE_X", [])
        assert "TYPE_X" in str(exc)


class TestRulesViolationError:
    def test_attributes(self):
        violations = ["entry before 07:00", "exit after 19:00"]
        exc = RulesViolationError(violations)
        assert exc.violations == violations
        assert exc.context["count"] == 2
        assert isinstance(exc, TransformationError)


# ---------------------------------------------------------------------------
# Rendering layer
# ---------------------------------------------------------------------------

class TestOutputDirectoryError:
    def test_attributes(self):
        p = Path("/nonexistent/dir")
        exc = OutputDirectoryError(p, reason="not writable")
        assert exc.path == p
        assert isinstance(exc, RenderingError)


class TestMissingRendererError:
    def test_attributes(self):
        exc = MissingRendererError("TYPE_X", ["TYPE_A", "TYPE_B"])
        assert exc.report_type == "TYPE_X"
        assert exc.registered == ["TYPE_A", "TYPE_B"]
        assert isinstance(exc, RenderingError)
