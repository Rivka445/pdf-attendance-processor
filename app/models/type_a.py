from dataclasses import dataclass
from typing import Optional
from app.models.type import Type
from app.models.line_a import LineA


@dataclass
class TypeA(Type[LineA]):
    """Full Type A report with pay-rate totals, bonus, and travel expenses."""
    place: Optional[str] = None
    hours_100: int = 0
    hours_125: int = 0
    hours_150: int = 0
    shabat_total: int = 0
    bonus: float = 0.0
    nesiot: float = 0.0
