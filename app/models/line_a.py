from dataclasses import dataclass
from typing import Optional
from app.models.line import Line


@dataclass
class LineA(Line):
    """Attendance row for Type A reports, including pay-rate breakdown."""
    place: Optional[str] = None
    break_time: int = 0
    hours_100: int = 0
    hours_125: int = 0
    hours_150: int = 0
    shabat: int = 0
