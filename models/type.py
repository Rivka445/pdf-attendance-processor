# ===== מודל בסיס: דוח שלם =====
# מחזיק את כל השורות של הדוח + נתוני סיכום.
# Generic[T] מאפשר ל-TypeA להחזיק List[LineA] ול-TypeB להחזיק List[LineB].

from dataclasses import dataclass, field
from typing import Generic, List, Optional, TypeVar

T = TypeVar("T")


@dataclass
class Type(Generic[T]):
    lines: List[T] = field(default_factory=list)  # כל שורות הנוכחות
    days: Optional[int] = None                     # מספר ימי עבודה
    total_hours: Optional[int] = None            # סה"כ דקות בחודש
