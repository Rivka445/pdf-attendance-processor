from dataclasses import dataclass, field
from typing import Generic, List, Optional, TypeVar

T = TypeVar("T")


@dataclass
class Type(Generic[T]):
    """Generic base report holding a list of typed rows and summary totals."""
    doc_type: str = ""
    lines: List[T] = field(default_factory=list)
    days: Optional[int] = None
    total_hours: Optional[int] = None
