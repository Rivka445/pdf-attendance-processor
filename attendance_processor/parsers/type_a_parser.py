"""parsers/type_a_parser.py — TYPE_A attendance report parser."""

from __future__ import annotations

import logging
import re
from datetime import date, time as dt_time

from domain.models import (
    AttendanceRow, BreakRecord,
    OvertimeBuckets, ReportSummary, TimeRange,
)
from parsers.base_parser import BaseParser

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_SKIP = re.compile(
    r"נ\.ע\.|הנשר|כח\s+אדם"
    r"|תאריך"
    r"|^[-=|─\s]{3,}$"
    r"|ימים\s*$"
    r"|סה.כ\s+שעות\s*$"
    r"|שעות\s+(?:100|125|150)%\s*$"
    r"|(?:100|125|150)%\s*שעות"
    r"|Is\s*$",
    re.UNICODE,
)

_NUM = r"(\d{1,2}(?::\d{2}|[.,]\d+)?|\d{3,4})"

_ROW_RTL = re.compile(
    r"(?:^|\s)[^\d]*"
    + _NUM + r"\s+"
    + _NUM + r"\s+"
    + _NUM + r"\s+"
    + _NUM + r"\s+"
    + _NUM + r"\s+"
    + _NUM + r"\s+"
    + r"(\d{1,2}:\d{2})\s+"
    + r"(\d{1,2}:\d{2})"
    + r"(.*)",
    re.UNICODE,
)

_ROW_LTR = re.compile(
    r"(\d{1,2}/\d{1,2}/\d{2,4})"
    r"[^\d:]*"
    r"(\d{1,2}:\d{2})\s+"
    r"(\d{1,2}:\d{2})\s+"
    + _NUM + r"\s+"
    + _NUM + r"\s+"
    + _NUM + r"\s+"
    + _NUM + r"\s+"
    + _NUM + r"\s+"
    + _NUM,
    re.UNICODE,
)

_DATE_IN_LINE     = re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4})")
_TRAILING_DAY_NUM = re.compile(r"\b([12]?\d|3[01])\s*$")
_HEBREW_WORD      = re.compile(r"[\u05d0-\u05ea]{2,}", re.UNICODE)
_HEBREW_DAY_WORDS = frozenset({"ראשון","שני","שלישי","רביעי","חמישי","שישי","יום"})

_SENTINEL_YEAR = 1

_FOOTER_LINE  = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$"
)
_FOOTER_TRVL  = re.compile(r"נסיעות\s+([\d.]+)|([\d.]+)\s*\|?\s*נסיעות", re.UNICODE)
_FOOTER_BONUS = re.compile(r"בונוס\s+([\d.]+)|([\d.]+)\s*\|?\s*בונוס",   re.UNICODE)
_COMPANY_RE   = re.compile(r"(?:הנשר|נ\.ע\.|כח\s+אדם)[^\n]*", re.UNICODE)


def _preprocess(line: str) -> str:
    return re.sub(r"(?<![\d:])00(?=\s)", "0", line)


def _location_from(text: str) -> str | None:
    word = next((w for w in _HEBREW_WORD.findall(text) if w not in _HEBREW_DAY_WORDS), "")
    return word or None


class TypeAParser(BaseParser):
    """Parses TYPE_A scanned attendance reports."""

    @property
    def report_type(self) -> str:
        return "TYPE_A"

    def _is_header_line(self, line: str) -> bool:
        return bool(_SKIP.search(line))

    def _parse_row(self, line: str) -> AttendanceRow | None:
        line = _preprocess(line)
        fields = self._extract_row_fields(line)
        if fields is None:
            return None

        raw_date, location, entry_s, exit_s, brk_s, total_s, p100, p125, p150, pshab = fields

        clock = self._safe_clock(self._parse_time(entry_s), self._parse_time(exit_s))
        if clock is None:
            return None

        if raw_date.startswith("__day__"):
            try:
                day_hint = int(raw_date[7:])
                row_date = date(_SENTINEL_YEAR, 1, max(1, min(day_hint, 31)))
            except ValueError:
                row_date = date(_SENTINEL_YEAR, 1, 1)
        else:
            row_date = self._parse_date(raw_date) or date(_SENTINEL_YEAR, 1, 1)

        return AttendanceRow(
            row_date    = row_date,
            day_name    = "—",
            clock       = clock,
            total_hours = self._hhmm_to_hours(total_s or ""),
            location    = location,
            break_rec   = self._make_break(brk_s, clock),
            overtime    = self._make_overtime(p100, p125, p150, pshab),
        )

    def _parse_summary(self, lines: list[str]) -> ReportSummary:
        company_name = days = total_h = None
        p100 = p125 = p150 = pshab = travel = bonus = None

        for line in lines:
            stripped = line.strip()
            if company_name is None and _COMPANY_RE.search(stripped):
                company_name = re.sub(r"\s+ND\s*", " ", stripped).strip()
            fm = _FOOTER_LINE.match(stripped)
            if fm and days is None:
                days, total_h = int(fm.group(1)), float(fm.group(3))
                p100, p125, p150, pshab = (float(fm.group(i)) for i in (4, 5, 6, 7))
            tm = _FOOTER_TRVL.search(stripped)
            if tm and travel is None:
                travel = float(tm.group(1) or tm.group(2))
            bm = _FOOTER_BONUS.search(stripped)
            if bm and bonus is None:
                bonus = float(bm.group(1) or bm.group(2))

        return ReportSummary(
            company_name=company_name, total_days=days, total_hours=total_h,
            ot_100=p100, ot_125=p125, ot_150=p150, ot_shabbat=pshab,
            travel_allowance=travel, bonus=bonus,
        )

    # ── helpers ──────────────────────────────────────────────────────────

    def _extract_row_fields(self, line: str):
        m = _ROW_LTR.search(line)
        if m:
            raw_date, entry_s, exit_s, brk_s, total_s, p100, p125, p150, pshab = m.groups()
            prefix = line[m.start(1) + len(raw_date): m.start(2)]
            return raw_date, _location_from(prefix), entry_s, exit_s, brk_s, total_s, p100, p125, p150, pshab

        m = _ROW_RTL.search(line)
        if not m:
            return None
        g      = m.groups()
        suffix = g[8] or ""
        dm     = _DATE_IN_LINE.search(line)

        if dm:
            raw_date = dm.group(1)
        else:
            tn = _TRAILING_DAY_NUM.search(suffix) or _TRAILING_DAY_NUM.search(line)
            raw_date = f"__day__{tn.group(1)}" if tn else ""

        return (
            raw_date, _location_from(suffix),
            g[7], g[6], g[5], g[4], g[3], g[2], g[1], g[0],
        )

    def _make_break(self, brk_s: str, clock: TimeRange) -> BreakRecord | None:
        brk_time = self._parse_time(brk_s)
        if not brk_time:
            return None
        dur_min = brk_time.hour * 60 + brk_time.minute
        if dur_min <= 0:
            return None
        end_min = clock.entry.hour * 60 + clock.entry.minute + dur_min
        return BreakRecord(
            clock        = TimeRange(entry=clock.entry, exit=dt_time(end_min // 60, end_min % 60)),
            duration_min = dur_min,
        )

    def _make_overtime(self, p100, p125, p150, pshab) -> OvertimeBuckets:
        h = [self._hhmm_to_hours(v or "") for v in (p100, p125, p150, pshab)]
        return OvertimeBuckets(
            regular_ot=round(h[0], 2), band_125=round(h[1], 2),
            band_150=round(h[2], 2),   weekend_ot=round(h[3], 2),
        )

    def _post_process_rows(self, rows: list[AttendanceRow]) -> list[AttendanceRow]:
        from collections import Counter
        import calendar

        real_dates = [r.row_date for r in rows if r.row_date.year != _SENTINEL_YEAR]
        if not real_dates:
            return rows

        ref_year, ref_month = Counter(
            (d.year, d.month) for d in real_dates
        ).most_common(1)[0][0]

        # fill sentinel rows that have a valid day hint
        used_days = {d.day for d in real_dates}
        fixed: list[AttendanceRow] = []
        for row in rows:
            if row.row_date.year != _SENTINEL_YEAR:
                fixed.append(row)
                continue
            try:
                new_date = date(ref_year, ref_month, row.row_date.day)
                if new_date.day in used_days:
                    raise ValueError("duplicate")
                used_days.add(new_date.day)
                fixed.append(self._replace_date(row, new_date))
            except (ValueError, OverflowError):
                fixed.append(row)

        # sequential interpolation for any remaining sentinels
        days_in_month = calendar.monthrange(ref_year, ref_month)[1]
        for i, row in enumerate(fixed):
            if row.row_date.year != _SENTINEL_YEAR:
                continue
            prev = next((fixed[j].row_date.day for j in range(i-1,-1,-1)
                         if fixed[j].row_date.year != _SENTINEL_YEAR), 0)
            nxt  = next((fixed[j].row_date.day for j in range(i+1,len(fixed))
                         if fixed[j].row_date.year != _SENTINEL_YEAR), None)
            candidate = prev + 1
            if nxt and candidate >= nxt:
                candidate = nxt - 1
            if 1 <= candidate <= days_in_month and candidate not in used_days:
                fixed[i] = self._replace_date(row, date(ref_year, ref_month, candidate))
                used_days.add(candidate)

        # derive day name from date for every resolved row
        return [
            self._replace_date(row, row.row_date)
            if row.row_date.year != _SENTINEL_YEAR else row
            for row in fixed
        ]

    def _replace_date(self, row: AttendanceRow, new_date: date) -> AttendanceRow:
        return AttendanceRow(
            row_date    = new_date,
            day_name    = self._day_name_from_date(new_date),
            clock       = row.clock,
            total_hours = row.total_hours,
            location    = row.location,
            break_rec   = row.break_rec,
            overtime    = row.overtime,
            notes       = row.notes,
        )

    @staticmethod
    def _day_name_from_date(d: date) -> str:
        _HEB_DAYS = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
        return f"יום {_HEB_DAYS[d.weekday()]}"
