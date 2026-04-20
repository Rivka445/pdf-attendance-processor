from dataclasses import dataclass
from typing import Optional


@dataclass
class Line:
    date: Optional[str] = None
    day: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    total: Optional[float] = None