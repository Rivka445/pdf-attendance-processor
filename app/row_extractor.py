from app.processing.rules.base_rules import minutes_to_str

MINUTE_FIELDS = {"break_time", "total", "hours_100", "hours_125", "hours_150", "shabat"}


def get_cell_value(line, key: str) -> str:
    """
    Read a field from a line dataclass and return it as a display string.
    Minute-valued fields are formatted as H:MM; missing values return empty string.
    """
    val = getattr(line, key, None)
    if val is None:
        return ""
    if key in MINUTE_FIELDS:
        return minutes_to_str(val)
    return str(val)
