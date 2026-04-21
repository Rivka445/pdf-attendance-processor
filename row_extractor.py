# ===== Row Extractor =====
# מחלץ ערך מכל שורה לפי key מהתבנית, ומפרמט לתצוגה.

from rules.base_rules import minutes_to_str

# שדות שמכילים דקות ומוצגים כ-H:MM
MINUTE_FIELDS = {"break_time", "total", "hours_100", "hours_125", "hours_150", "shabat"}


def get_cell_value(line, key: str) -> str:
    val = getattr(line, key, None)
    if val is None:
        return ""
    if key in MINUTE_FIELDS:
        return minutes_to_str(val)  # 0 → "0:00"
    return str(val)
