from dataclasses import replace
from app.models.type_b import TypeB
from app.models.line_b import LineB
from app.models.report_meta import ReportMeta
from app.processing.rules.base_rules import (
    _rng, vary_time, calc_total, BREAK_HOURS_B,
    to_minutes, get_work_days, day_name,
)

WORKER_NAMES = ["ישראל ישראלי", "משה כהן", "דוד לוי", "יעקב מזרחי", "אברהם פרץ"]
PRICES       = [28.0, 30.0, 30.65, 32.0, 35.0]
COMMENTS     = ["", "", "", "איחור קל", "", ""]


def _date_sort_key(date: str | None) -> tuple:
    """Return a (year, month, day) tuple for chronological sorting."""
    if not date:
        return (9999, 99, 99)
    try:
        parts = date.split("/")
        return (int(parts[2]) if len(parts[2]) == 4 else 2000 + int(parts[2]),
                int(parts[1]), int(parts[0]))
    except Exception:
        return (9999, 99, 99)


class RulesB:
    def apply(self, meta: ReportMeta, source: TypeB) -> TypeB:
        """Apply deterministic variation to a TypeB source report."""
        return generate_type_b(meta, source)


def generate_type_b(meta: ReportMeta, source: TypeB) -> TypeB:
    """
    Build a new TypeB report covering every work day in the month.
    Source rows are matched by day-of-month; unmatched days use typical times.
    A Shabbat placeholder row is appended after every Friday row.
    """
    rng = _rng(meta)
    report = TypeB()
    report.doc_type       = "B"
    report.month          = source.month
    report.worker_name    = rng.choice(WORKER_NAMES)
    report.price_per_hour = rng.choice(PRICES)

    # Index source lines by day-of-month for fast lookup
    source_by_day: dict[int, LineB] = {}
    for line in source.lines:
        if line.date and line.start_time and line.end_time:
            try:
                source_by_day[int(line.date.split("/")[0])] = line
            except Exception:
                pass

    seen_dates = set()

    for d in get_work_days(meta):
        date = f"{d}/{meta.month}/{meta.year}"
        day  = day_name(meta.year, meta.month, d)

        src  = source_by_day.get(d)
        base_start = src.start_time if src else meta.typical_start
        base_end   = src.end_time   if src else meta.typical_end

        new_start = vary_time(base_start, rng)
        new_end   = vary_time(base_end,   rng)
        if to_minutes(new_end) <= to_minutes(new_start):
            new_end = base_end

        total = calc_total(new_start, new_end, BREAK_HOURS_B)

        report.lines.append(LineB(
            date=date, day=day,
            start_time=new_start, end_time=new_end,
            total=total,
            comment=rng.choice(COMMENTS) or None,
            is_shabat=False,
        ))
        seen_dates.add(date)

        if day == "שישי":
            shabat_date = f"{d + 1}/{meta.month}/{meta.year}"
            if shabat_date not in seen_dates:
                report.lines.append(LineB(date=shabat_date, day="שבת", is_shabat=True))
                seen_dates.add(shabat_date)

    report.days          = sum(1 for l in report.lines if not l.is_shabat)
    report.total_hours   = sum(l.total for l in report.lines if l.total)
    report.total_payment = round(report.total_hours / 60 * report.price_per_hour, 2)

    return report
