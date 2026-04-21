# ===== Rules Type B =====
import calendar
from models.type_b import TypeB
from models.line_b import LineB
from models.report_meta import ReportMeta
from rules.base_rules import _rng, get_work_days, vary_time, calc_total, BREAK_HOURS_B, day_name, to_minutes

COMMENTS = ["", "", "", "איחור קל", "", ""]


def generate_type_b(meta: ReportMeta) -> TypeB:
    rng = _rng(meta)
    report = TypeB()
    report.month = f"{meta.month:02d}/{meta.year}"

    for day_num in get_work_days(meta):
        weekday = calendar.weekday(meta.year, meta.month, day_num)
        start = vary_time(meta.typical_start, rng)
        end = vary_time(meta.typical_end, rng)
        if to_minutes(end) <= to_minutes(start):
            end = meta.typical_end

        total = calc_total(start, end, BREAK_HOURS_B)
        date_str = f"{day_num}/{meta.month}/{str(meta.year)[2:]}"

        report.lines.append(LineB(
            date=date_str,
            day=day_name(meta.year, meta.month, day_num),
            start_time=start,
            end_time=end,
            total=total,
            comment=rng.choice(COMMENTS) or None,
        ))

        # אחרי שישי (weekday==4) - הוסף שורת שבת ריקה
        if weekday == 4:
            shabat_day = day_num + 1
            shabat_date = f"{shabat_day}/{meta.month}/{str(meta.year)[2:]}"
            report.lines.append(LineB(
                date=shabat_date,
                day="שבת",
                start_time=None,
                end_time=None,
                total=None,
                comment=None,
                is_shabat=True,
            ))

    report.days = sum(1 for l in report.lines if not l.is_shabat)
    report.total_hours = sum(l.total for l in report.lines if l.total)

    return report
