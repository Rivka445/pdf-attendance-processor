# ===== מודל בסיס: שורה בודדת בדוח =====
# כל שורה בטבלת הנוכחות מיוצגת על ידי Line או תת-מחלקה שלו.
# שדות משותפים לכל סוגי הדוחות.

from dataclasses import dataclass
from typing import Optional


@dataclass
class Line:
    date: Optional[str] = None        # תאריך: DD/MM/YYYY או D/M/YY
    day: Optional[str] = None         # יום בשבוע: ראשון, שני...
    start_time: Optional[str] = None  # שעת כניסה: HH:MM
    end_time: Optional[str] = None    # שעת יציאה: HH:MM
    total: Optional[int] = None     # סה"כ דקות עבודה באותו יום
