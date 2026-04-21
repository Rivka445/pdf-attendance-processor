# ===== שורה בדוח Type B =====
# מרחיב את Line עם שדות ייחודיים לדוח B.
# דוח B פשוט יותר - אין פירוט אחוזים, רק שעות ותגובה אופציונלית.

from dataclasses import dataclass
from typing import Optional
from .line import Line


@dataclass
class LineB(Line):
    comment: Optional[str] = None  # הערה לשורה
    is_shabat: bool = False        # שורת שבת - ריקה, צבע כהה
