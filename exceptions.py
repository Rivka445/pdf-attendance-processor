# ===== Exceptions =====


class AttendanceProcessorError(Exception):
    """בסיס לכל שגיאות הפרויקט."""


class OcrError(AttendanceProcessorError):
    """שגיאה בשלב ה-OCR."""


class ClassificationError(AttendanceProcessorError):
    """לא ניתן לסווג את הדוח."""


class ParsingError(AttendanceProcessorError):
    """שגיאה בפרסור הנתונים."""


class RenderingError(AttendanceProcessorError):
    """שגיאה ביצירת קובץ הפלט."""


class UnsupportedFormatError(AttendanceProcessorError):
    """פורמט פלט לא נתמך."""
