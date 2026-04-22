import calendar
from dataclasses import replace
from app.models.type_a import TypeA
from app.models.report_meta import ReportMeta
from app.processing.rules.base_rules import (
    _rng, vary_time, calc_total, BREAK_HOURS_A,
    to_minutes, get_work_days, day_name,
)

PLACES = ["סניף מרכז", "סניף צפון", "סניף דרום", "משרד ראשי"]


class RulesA:
    def apply(self, meta: ReportMeta, source: TypeA) -> TypeA:
        """Apply deterministic variation to a TypeA source report."""
        return generate_type_a(meta, source)


def _date_sort_key(date: str | None) -> tuple:
    """Return a (year, month, day) tuple for chronological sorting."""
    if not date:
        return (9999, 99, 99)
    try:
        parts = date.split("/")
        return (int(parts[2]), int(parts[1]), int(parts[0]))
    except Exception:
        return (9999, 99, 99)


def generate_type_a(meta: ReportMeta, source: TypeA) -> TypeA:
    """
    Build a new TypeA report by applying ±15-minute time variation to each
    source row. Missing dates and day names are reconstructed from meta.
    Rows are sorted chronologically before output.
    """
    rng = _rng(meta)
    report = TypeA()
    report.doc_type = "A"
    report.place    = rng.choice(PLACES)

    work_days = get_work_days(meta)

    for i, line in enumerate(source.lines):
        if not line.start_time or not line.end_time:
            report.lines.append(line)
            continue

        new_start = vary_time(line.start_time, rng)
        new_end   = vary_time(line.end_time,   rng)
        if to_minutes(new_end) <= to_minutes(new_start):
            new_end = line.end_time

        total = calc_total(new_start, new_end, BREAK_HOURS_A)

        date = line.date
        day  = line.day
        if not date and i < len(work_days):
            d    = work_days[i]
            date = f"{d:02d}/{meta.month:02d}/{meta.year}"
            day  = day_name(meta.year, meta.month, d)
        elif date and not day:
            try:
                d, m, y = map(int, date.split("/"))
                day = day_name(y, m, d)
            except Exception:
                pass

        weekday = None
        if date:
            try:
                d, m, y = map(int, date.split("/"))
                weekday = calendar.weekday(y, m, d)
            except Exception:
                pass

        is_overtime = meta.has_overtime and weekday == 2
        h100 = max(0, total - 120) if is_overtime else total
        h125 = 120 if is_overtime else 0

        report.lines.append(replace(line,
            date=date, day=day, place=report.place,
            start_time=new_start, end_time=new_end,
            break_time=int(BREAK_HOURS_A * 60),
            total=total, hours_100=h100, hours_125=h125, hours_150=0, shabat=0,
        ))

    report.lines.sort(key=lambda l: _date_sort_key(l.date))

    report.days         = len(report.lines)
    report.total_hours  = sum(l.total or 0 for l in report.lines)
    report.hours_100    = sum(l.hours_100 for l in report.lines)
    report.hours_125    = sum(l.hours_125 for l in report.lines)
    report.hours_150    = sum(l.hours_150 for l in report.lines)
    report.shabat_total = 0
    report.bonus        = 0.0
    report.nesiot       = round(rng.choice([0, 0, 0, 150, 200, 250]), 2)

    return report
