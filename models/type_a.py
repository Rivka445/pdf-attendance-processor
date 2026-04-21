from dataclasses import dataclass
from typing import Optional
from models.type import Type
from models.line_a import LineA


@dataclass
class TypeA(Type[LineA]):
    place: Optional[str] = None
    hours_100: int = 0
    hours_125: int = 0
    hours_150: int = 0
