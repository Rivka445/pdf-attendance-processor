"""
errors.py
=========
Central exception registry for the entire attendance-processor system.

All custom exceptions live here so that any module can do::

    from errors import ExtractionError, ClassificationError, ...

without creating circular imports.  Every exception carries at least a
human-readable ``message`` and an optional ``context`` dict for structured
logging.

Hierarchy
---------
AttendanceProcessorError            — project root
├── ExtractionError                 — ingestion / OCR layer
│   ├── PDFOpenError                — fitz could not open the file
│   └── OCRError                    — tesseract failed on a page
├── ClassificationError             — classification layer
│   └── LowConfidenceError          — score below threshold → UNKNOWN
├── ParseError                      — parser layer
│   ├── NoRowsError                 — no data rows extracted
│   └── InvalidClockError           — exit ≤ entry for all rows
├── TransformationError             — transformation layer
│   ├── UnknownReportTypeError      — no strategy / rules for this type
│   └── RulesViolationError         — collected validation violations
└── RenderingError                  — generation / output layer
    ├── OutputDirectoryError        — destination is not writable
    └── MissingRendererError        — no renderer registered for type
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Root
# ---------------------------------------------------------------------------

class AttendanceProcessorError(Exception):
    """
    Base class for every custom exception in this project.

    Attributes:
        message: Human-readable description of the failure.
        context: Optional dict of structured key-value pairs (for logging).
    """

    def __init__(self, message: str, context: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message: str              = message
        self.context: dict[str, Any]   = context or {}

    def __str__(self) -> str:
        if self.context:
            ctx = "  |  ".join(f"{k}={v!r}" for k, v in self.context.items())
            return f"{self.message}  [{ctx}]"
        return self.message


# ---------------------------------------------------------------------------
# Ingestion / extraction layer
# ---------------------------------------------------------------------------

class ExtractionError(AttendanceProcessorError):
    """Raised when the PDF→text pipeline fails."""


class PDFOpenError(ExtractionError):
    """PyMuPDF could not open the PDF file."""

    def __init__(self, pdf_path: Path, reason: str = "") -> None:
        super().__init__(
            f"Cannot open PDF: {pdf_path}",
            context={"path": str(pdf_path), "reason": reason},
        )
        self.pdf_path = pdf_path


class OCRError(ExtractionError):
    """Tesseract returned an error or empty result for a page."""

    def __init__(self, pdf_path: Path, page_index: int, reason: str = "") -> None:
        super().__init__(
            f"OCR failed on page {page_index} of {pdf_path}",
            context={"path": str(pdf_path), "page": page_index, "reason": reason},
        )
        self.pdf_path   = pdf_path
        self.page_index = page_index


# ---------------------------------------------------------------------------
# Classification layer
# ---------------------------------------------------------------------------

class ClassificationError(AttendanceProcessorError):
    """Raised when the classifier cannot produce a usable result."""


class LowConfidenceError(ClassificationError):
    """Confidence score is below the configured threshold → result is UNKNOWN."""

    def __init__(self, score_a: float, score_b: float, confidence: float, threshold: float) -> None:
        super().__init__(
            f"Classification confidence {confidence:.2%} is below threshold {threshold:.2%}",
            context={
                "score_a":    score_a,
                "score_b":    score_b,
                "confidence": confidence,
                "threshold":  threshold,
            },
        )
        self.score_a    = score_a
        self.score_b    = score_b
        self.confidence = confidence
        self.threshold  = threshold


# ---------------------------------------------------------------------------
# Parser layer
# ---------------------------------------------------------------------------

class ParseError(AttendanceProcessorError):
    """Raised when a parser cannot extract a required field."""

    def __init__(
        self,
        message: str,
        field:   str = "",
        snippet: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        ctx = dict(context or {})
        if field:
            ctx["field"] = field
        if snippet:
            ctx["near"] = snippet[:80]
        super().__init__(message, context=ctx)
        self.field   = field
        self.snippet = snippet


class NoRowsError(ParseError):
    """No data rows could be extracted from the document."""

    def __init__(self, report_type: str) -> None:
        super().__init__(
            f"{report_type}: no data rows could be parsed",
            field="rows",
            context={"report_type": report_type},
        )
        self.report_type = report_type


class InvalidClockError(ParseError):
    """All candidate rows had invalid (exit ≤ entry) clock pairs."""

    def __init__(self, report_type: str) -> None:
        super().__init__(
            f"{report_type}: all rows had invalid clock pairs (exit ≤ entry)",
            field="clock",
            context={"report_type": report_type},
        )
        self.report_type = report_type


# ---------------------------------------------------------------------------
# Transformation layer
# ---------------------------------------------------------------------------

class TransformationError(AttendanceProcessorError):
    """Raised when the transformation layer encounters an unrecoverable error."""


class UnknownReportTypeError(TransformationError):
    """No strategy or rules are registered for the given report_type."""

    def __init__(self, report_type: str, registry_keys: list[str]) -> None:
        super().__init__(
            f"No handler registered for report_type={report_type!r}",
            context={"report_type": report_type, "known_types": registry_keys},
        )
        self.report_type   = report_type
        self.registry_keys = registry_keys


class RulesViolationError(TransformationError):
    """One or more business-rule violations were found in the report."""

    def __init__(self, violations: list[str]) -> None:
        bullet_list = "; ".join(violations)
        super().__init__(
            f"Rules violations detected: {bullet_list}",
            context={"violations": violations, "count": len(violations)},
        )
        self.violations = violations


# ---------------------------------------------------------------------------
# Rendering / generation layer
# ---------------------------------------------------------------------------

class RenderingError(AttendanceProcessorError):
    """Base class for all rendering failures."""


class OutputDirectoryError(RenderingError):
    """The output directory is missing or not writable."""

    def __init__(self, path: Path, reason: str = "") -> None:
        super().__init__(
            f"Output path is not writable: {path}",
            context={"path": str(path), "reason": reason},
        )
        self.path = path


class MissingRendererError(RenderingError):
    """No renderer is registered for the given report_type."""

    def __init__(self, report_type: str, registered: list[str]) -> None:
        super().__init__(
            f"No renderer registered for report_type={report_type!r}",
            context={"report_type": report_type, "registered": registered},
        )
        self.report_type = report_type
        self.registered  = registered
