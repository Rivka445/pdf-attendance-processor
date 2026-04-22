from dataclasses import dataclass
from typing import Optional
from app.models.type import Type
from app.models.line_b import LineB


@dataclass
class TypeB(Type[LineB]):
    """Full Type B report with worker details and payment summary."""
    month: Optional[str] = None
    worker_name: Optional[str] = None
    price_per_hour: float = 0.0
    total_payment: float = 0.0
