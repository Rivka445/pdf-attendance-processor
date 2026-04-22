class AttendanceProcessorError(Exception):
    """Base exception for all project errors."""

class OcrError(AttendanceProcessorError):
    """Raised when OCR extraction fails."""

class ClassificationError(AttendanceProcessorError):
    """Raised when the document type cannot be determined."""

class ParsingError(AttendanceProcessorError):
    """Raised when parsing or rules application fails."""

class RenderingError(AttendanceProcessorError):
    """Raised when output file generation fails."""

class UnsupportedFormatError(AttendanceProcessorError):
    """Raised when an unsupported output format is requested."""
