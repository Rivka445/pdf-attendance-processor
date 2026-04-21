# ===== שורה בדוח Type A =====
# מרחיב את Line עם שדות ייחודיים לדוח A:
# הפסקה, פירוט שעות לפי אחוז תשלום, ושבת.

from dataclasses import dataclass
from typing import Optional
from .line import Line


@dataclass
class LineA(Line):
    place: Optional[str] = None  # מיקום/סניף
    break_time: int = 0           # זמן הפסקה בדקות
    hours_100: int = 0            # שעות רגילות (100%) בדקות
    hours_125: int = 0            # שעות נוספות ראשונות (125%) בדקות
    hours_150: int = 0            # שעות נוספות שניות (150%) בדקות
    shabat: int = 0               # שעות שבת בדקות
