from dataclasses import dataclass
from typing import Optional
from .type import Type
from .line import LineA


@dataclass
class TypeA(Type[LineA]):
    place: Optional[str] = None
    hours_100: float = 0.0
    hours_125: float = 0.0
    hours_150: float = 0.0
    bonus: float = 0.0
    nesiot: float = 0.0