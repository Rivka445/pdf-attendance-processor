from dataclasses import dataclass
from typing import Optional
from app.models.line import Line


@dataclass
class LineB(Line):
    """Attendance row for Type B reports, with optional comment and Shabbat flag."""
    comment: Optional[str] = None
    is_shabat: bool = False
