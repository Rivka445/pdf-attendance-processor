import calendar
import random
from app.models.report_meta import ReportMeta

BREAK_HOURS_A     = 0.5
BREAK_HOURS_B     = 0.0
VARIATION_MINUTES = [-15, -10, -5, 0, 0, 0, 5, 10, 15]
DAYS_HE           = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]


def _rng(meta: ReportMeta) -> random.Random:
    """Return a seeded Random instance for deterministic variant generation."""
    return random.Random(meta.seed)


def get_work_days(meta: ReportMeta) -> list[int]:
    """
    Return an ordered list of calendar day numbers that are valid work days
    for the given month. Type A excludes Friday and Saturday; Type B excludes Saturday only.
    The list is capped at meta.work_days entries.
    """
    _, days_in_month = calendar.monthrange(meta.year, meta.month)
    valid = {0, 1, 2, 3, 6} if meta.doc_type == "A" else {0, 1, 2, 3, 4, 6}
    candidates = [
        d for d in range(1, days_in_month + 1)
        if calendar.weekday(meta.year, meta.month, d) in valid
    ]
    return candidates[:meta.work_days]


def vary_time(base_time: str, rng: random.Random) -> str:
    """Apply a small deterministic offset (±15 min) to a HH:MM time string."""
    h, m = map(int, base_time.split(":"))
    delta = rng.choice(VARIATION_MINUTES)
    total = max(0, min(h * 60 + m + delta, 23 * 60 + 59))
    return f"{total // 60:02d}:{total % 60:02d}"


def day_name(year: int, month: int, day: int) -> str:
    """Return the Hebrew weekday name for the given date."""
    return DAYS_HE[calendar.weekday(year, month, day)]


def to_minutes(t: str) -> int:
    """Convert H:MM or HH:MM to total minutes from midnight."""
    h, m = map(int, t.split(":"))
    return h * 60 + m


def calc_total(start: str, end: str, break_hours: float = BREAK_HOURS_A) -> float:
    """Compute net work minutes as (end - start) minus the break duration."""
    diff_minutes = (to_minutes(end) - to_minutes(start)) - int(break_hours * 60)
    return max(0, diff_minutes)


def minutes_to_str(minutes) -> str:
    """Format an integer minute count as H:MM (e.g. 190 -> '3:10')."""
    minutes = int(minutes)
    return f"{minutes // 60}:{minutes % 60:02d}"
