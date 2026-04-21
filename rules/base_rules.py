# ===== Rules - יצירת דוח חדש הגיוני =====
# מקבל ReportMeta ומייצר דוח חדש עם נתונים אמינים.
#
# עקרונות:
# - תאריכים: ימי עבודה אמיתיים בחודש (ללא שישי/שבת)
# - שעות: וריאציה קטנה סביב typical_start/end (±15 דקות)
# - וריאציה דטרמיניסטית: seed לפי שם הקובץ → אותו seed = אותה תוצאה
# - הפסקה: 30 דקות קבוע
# - סה"כ = end - start - break
# - שעות נוספות (A בלבד): אם has_overtime, יום אחד בשבוע מסתיים שעה מאוחר יותר

import calendar
import random
from models.report_meta import ReportMeta


BREAK_HOURS_A = 0.5   # 30 דקות הפסקה - דוח A
BREAK_HOURS_B = 0.0   # דוח B - אין הפסקה מפורשת בדוח
VARIATION_MINUTES = [-15, -10, -5, 0, 0, 0, 5, 10, 15]  # התפלגות סביב 0


def _rng(meta: ReportMeta) -> random.Random:
    """Random דטרמיניסטי לפי seed = שם הקובץ."""
    return random.Random(meta.seed)


def get_work_days(meta: ReportMeta) -> list[int]:
    """
    מחזיר רשימת ימי עבודה בחודש.
    דוח A: ראשון-חמישי (weekday 6,0,1,2,3), ללא שישי/שבת
    דוח B: שני-שישי (weekday 0-4)
    """
    _, days_in_month = calendar.monthrange(meta.year, meta.month)
    if meta.doc_type == "A":
        # ראשון(6), שני(0), שלישי(1), רביעי(2), חמישי(3)
        valid = {0, 1, 2, 3, 6}
    else:
        # ראשון(6), שני(0), שלישי(1), רביעי(2), חמישי(3), שישי(4)
        valid = {0, 1, 2, 3, 4, 6}
    candidates = [
        d for d in range(1, days_in_month + 1)
        if calendar.weekday(meta.year, meta.month, d) in valid
    ]
    return candidates[:meta.work_days]


def vary_time(base_time: str, rng: random.Random) -> str:
    """
    מוסיף וריאציה קטנה לשעה: ±15 דקות דטרמיניסטי.
    base_time: "HH:MM"
    מחזיר: "HH:MM" חדש
    """
    h, m = map(int, base_time.split(":"))
    delta = rng.choice(VARIATION_MINUTES)
    total = h * 60 + m + delta
    total = max(0, min(total, 23 * 60 + 59))
    return f"{total // 60:02d}:{total % 60:02d}"


# calendar.weekday: 0=Monday...4=Friday, 5=Saturday, 6=Sunday
# בעברית: 0=שני, 1=שלישי, 2=רביעי, 3=חמישי, 4=שישי, 5=שבת, 6=ראשון
DAYS_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]


def day_name(year: int, month: int, day: int) -> str:
    """מחזיר שם יום בעברית."""
    return DAYS_HE[calendar.weekday(year, month, day)]


def to_minutes(t: str) -> int:
    """ממיר שעה HH:MM או H:MM למספר דקות מחצות."""
    h, m = map(int, t.split(":"))
    return h * 60 + m


def calc_total(start: str, end: str, break_hours: float = BREAK_HOURS_A) -> float:
    """מחשב סה"כ דקות = end - start - הפסקה. מחזיר דקות שלמות."""
    diff_minutes = (to_minutes(end) - to_minutes(start)) - int(break_hours * 60)
    return max(0, diff_minutes)


def minutes_to_str(minutes) -> str:
    """ממיר דקות לפורמט H:MM. לדוגמה 190 → '3:10'."""
    minutes = int(minutes)
    return f"{minutes // 60}:{minutes % 60:02d}"
