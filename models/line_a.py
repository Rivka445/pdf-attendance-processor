from dataclasses import dataclass
from typing import Optional
from .line import Line


@dataclass
class LineA(Line):
    place: Optional[str] = None
    break_time: float = 0.0
    hours_100: float = 0.0
    hours_125: float = 0.0
    hours_150: float = 0.0
    shabat: float = 0.0