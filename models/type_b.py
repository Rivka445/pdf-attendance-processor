from dataclasses import dataclass
from typing import Optional
from .type import Type
from .line_b import LineB


@dataclass
class TypeB(Type[LineB]):
    month: Optional[str] = None
    worker_name: Optional[str] = None
    price_per_hour: float = 0.0
    total_payment: float = 0.0
