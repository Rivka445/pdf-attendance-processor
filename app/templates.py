from dataclasses import dataclass


@dataclass
class ColumnDef:
    """Definition of a single report column: field name, header label, and widths."""
    key: str
    header: str
    width_cm: float
    width_xl: int


TEMPLATE_A = [
    ColumnDef("date",       "תאריך",  3.0, 12),
    ColumnDef("day",        "יום",    2.0,  8),
    ColumnDef("place",      "מקום",   3.0, 14),
    ColumnDef("start_time", "כניסה",  2.0,  8),
    ColumnDef("end_time",   "יציאה",  2.0,  8),
    ColumnDef("break_time", "הפסקה",  2.0,  8),
    ColumnDef("total",      'סה"כ',   2.0,  8),
    ColumnDef("hours_100",  "100%",   2.0,  8),
    ColumnDef("hours_125",  "125%",   2.0,  8),
    ColumnDef("hours_150",  "150%",   2.0,  8),
    ColumnDef("shabat",     "שבת",    2.0,  8),
]

TEMPLATE_B = [
    ColumnDef("date",       "תאריך",  3.0, 12),
    ColumnDef("day",        "יום",    2.0,  8),
    ColumnDef("start_time", "כניסה",  2.0,  8),
    ColumnDef("end_time",   "יציאה",  2.0,  8),
    ColumnDef("total",      'סה"כ',   2.0,  8),
    ColumnDef("comment",    "הערה",   4.0, 16),
]

TEMPLATES = {"A": TEMPLATE_A, "B": TEMPLATE_B}
