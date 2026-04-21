# ===== Rules Type A =====
import calendar
from models.type_a import TypeA
from models.line_a import LineA
from models.report_meta import ReportMeta
from rules.base_rules import _rng, get_work_days, vary_time, calc_total, BREAK_HOURS_A, day_name, to_minutes

PLACES = ["סניף מרכז", "סניף צפון", "סניף דרום", "משרד ראשי"]


def generate_type_a(meta: ReportMeta) -> TypeA:
    rng = _rng(meta)
    report = TypeA()
    report.place = rng.choice(PLACES)

    for day_num in get_work_days(meta):
        start = vary_time(meta.typical_start, rng)
        weekday = calendar.weekday(meta.year, meta.month, day_num)
        # get_work_days מסנן שבת (weekday==5), אז כאן weekday תמיד 0-4 (שני-שישי)
        # עמודת שבת בדוח A היא תמיד 0 - שבת לא עובדים
        is_overtime_day = meta.has_overtime and weekday == 2  # רביעי

        end_base = _add_hour(meta.typical_end) if is_overtime_day else meta.typical_end
        end = vary_time(end_base, rng)
        if to_minutes(end) <= to_minutes(start):
            end = _add_hour(start)

        total = calc_total(start, end, BREAK_HOURS_A)
        h100 = max(0, total - 120) if is_overtime_day else total
        h125 = 120 if is_overtime_day else 0
        h150 = 0
        shabat = 0  # שבת לא עובדים - עמודת שבת תמיד 0

        report.lines.append(LineA(
            date=f"{day_num:02d}/{meta.month:02d}/{meta.year}",
            day=day_name(meta.year, meta.month, day_num),
            start_time=start,
            end_time=end,
            break_time=int(BREAK_HOURS_A * 60),
            total=total,
            place=report.place,
            hours_100=h100,
            hours_125=h125,
            hours_150=h150,
            shabat=shabat,
        ))

    report.days = len(report.lines)
    report.total_hours = sum(l.total for l in report.lines)
    report.hours_100 = sum(l.hours_100 for l in report.lines)
    report.hours_125 = sum(l.hours_125 for l in report.lines)
    report.hours_150 = sum(l.hours_150 for l in report.lines)

    return report


def _add_hour(time_str: str) -> str:
    h, m = map(int, time_str.split(":"))
    return f"{min(h + 1, 23):02d}:{m:02d}"
