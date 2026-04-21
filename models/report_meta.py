# ===== מטא-דטה שהפרסור מחלץ מהדוח המקורי =====
# זה מה שה-Rules מקבל כקלט כדי לייצר דוח חדש הגיוני.
# לא מכיל את הנתונים עצמם - רק את המאפיינים הכלליים.

from dataclasses import dataclass


@dataclass
class ReportMeta:
    doc_type: str           # "A" או "B"
    month: int              # 1-12
    year: int               # לדוגמה 2022
    work_days: int          # כמה ימי עבודה בחודש
    typical_start: str      # שעת כניסה אופיינית, לדוגמה "08:00"
    typical_end: str        # שעת יציאה אופיינית, לדוגמה "15:00"
    has_overtime: bool      # האם יש שעות נוספות (125%/150%) - רלוונטי ל-A
    seed: str               # שם הקובץ המקורי - לוריאציה דטרמיניסטית
