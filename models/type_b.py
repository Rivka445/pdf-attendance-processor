from dataclasses import dataclass
from typing import Optional
from .type import Type
from .line import LineB


@dataclass
class TypeB(Type[LineB]):
    price_hour: float = 0.0
    total: float = 0.0
    month: Optional[str] = None