from dataclasses import dataclass
from typing import Optional
from .type import Type
from .line_b import LineB


@dataclass
class TypeB(Type[LineB]):
    month: Optional[str] = None
