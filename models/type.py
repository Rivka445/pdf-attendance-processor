from dataclasses import dataclass, field
from typing import Generic, List, Optional, TypeVar


T = TypeVar("T")


@dataclass
class Type(Generic[T]):
    lines: List[T] = field(default_factory=list)
    days: Optional[int] = None
    total_hours: Optional[float] = None