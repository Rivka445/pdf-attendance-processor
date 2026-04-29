"""
parsers/type_a_parser.py
=========================
Concrete parser for TYPE_A documents (נ.ע. הנשר כח אדם בע"מ).

Real OCR column order (RTL): שבת | 150% | 125% | 100% | סה"כ | הפסקה | יציאה | כניסה | <Hebrew> | תאריך
Test synthetic order (LTR):  תאריך | <Hebrew> | כניסה | יציאה | הפסקה | סה"כ | 100% | 125% | 150% | שבת
"""

from __future__ import annotations

import logging
import re
from datetime import date, time as dt_time
from typing import Optional

from domain.models import (
    AttendanceRow,
    BreakRecord,
    BreakType,
    OvertimeBuckets,
    ReportSummary,
    TimeRange,
)
from domain.errors import InvalidClockError, NoRowsError
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

# Numeric value: HH:MM or decimal (8.5 / 8,5 / 8)
_NUM = r"(\d{1,2}(?::\d{2}|[.,]\d+)?)"

# RTL (real OCR): shabbat 150% 125% 100% total break exit entry <Hebrew+date suffix>
_ROW_RTL = re.compile(
    r"^[^\d]*"
    + _NUM + r"\s+"           # 1 שבת
    + _NUM + r"\s+"           # 2 150%
    + _NUM + r"\s+"           # 3 125%
    + _NUM + r"\s+"           # 4 100%
    + _NUM + r"\s+"           # 5 total
    + _NUM + r"\s+"           # 6 break
    + r"(\d{1,2}:\d{2})\s+"   # 7 exit  (HH:MM)
    + r"(\d{1,2}:\d{2})"      # 8 entry (HH:MM)
    + r"(.*)",                  # 9 suffix
    re.UNICODE,
)

# LTR (test synthetic): date <Hebrew> entry exit break total 100% 125% 150% shabbat
_ROW_LTR = re.compile(
    r"(\d{1,2}/\d{1,2}/\d{2,4})"   # 1 date
    r"[^\d:]*"                       # day + location
    r"(\d{1,2}:\d{2})\s+"           # 2 entry
    r"(\d{1,2}:\d{2})\s+"           # 3 exit
    + _NUM + r"\s+"                  # 4 break
    + _NUM + r"\s+"                  # 5 total
    + _NUM + r"\s+"                  # 6 100%
    + _NUM + r"\s+"                  # 7 125%
    + _NUM + r"\s+"                  # 8 150%
    + _NUM,                          # 9 shabbat
    re.UNICODE,
)

_DATE_IN_LINE     = re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4})")
_DAY_IN_LINE      = re.compile(r"יום\s+(\S+)", re.UNICODE)
_HEBREW_WORD      = re.compile(r"[\u05d0-\u05ea]{2,}", re.UNICODE)
_HEBREW_DAY_WORDS = frozenset({"ראשון","שני","שלישי","רביעי","חמישי","שישי","שבת","יום"})

# Footer: plain numeric line  days absent total_h pct_100 pct_125 pct_150 shabbat
_FOOTER_LINE = re.compile(
    r"^\s*(\d+)\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*$"
)
_FOOTER_TRVL  = re.compile(r"נסיעות\s+([\d.]+)|([\d.]+)\s*\|?\s*נסיעות", re.UNICODE)
_FOOTER_BONUS = re.compile(r"בונוס\s+([\d.]+)|([\d.]+)\s*\|?\s*בונוס",   re.UNICODE)
_COMPANY_RE   = re.compile(r"(?:הנשר|נ\.ע\.|כח\s+אדם)[^\n]*", re.UNICODE)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class TypeAParser(BaseParser):
    """Parses TYPE_A scanned attendance reports."""

    @property
    def report_type(self) -> str:
        return "TYPE_A"

    def _is_header_line(self, line: str) -> bool:
        return bool(_SKIP.search(line))

    def _parse_row(self, line: str) -> Optional[dict]:
        # Try LTR first (test synthetic: date ... entry exit break total 100% 125% 150% shabbat)
        m = _ROW_LTR.search(line)
        if m:
            raw_date, entry, exit_, brk, total, pct_100, pct_125, pct_150, pct_shab = m.groups()
            prefix = line[m.start(1) + len(raw_date): m.start(2)]
            day_m  = _DAY_IN_LINE.search(prefix)
            location = ""
            for word in _HEBREW_WORD.findall(prefix):
                if word not in _HEBREW_DAY_WORDS:
                    location = word
                    break
            return {
                "raw_date":    raw_date,
                "day":         day_m.group(1) if day_m else "—",
                "location":    location,
                "entry":       entry,
                "exit":        exit_,
                "break":       brk,
                "total":       total,
                "pct_100":     pct_100,
                "pct_125":     pct_125,
                "pct_150":     pct_150,
                "pct_shabbat": pct_shab,
            }

        # Try RTL (real OCR: shabbat 150% 125% 100% total break exit entry <Hebrew> date)
        m = _ROW_RTL.search(line)
        if not m:
            return None
        g = m.groups()
        suffix   = g[8] or ""
        date_m   = _DATE_IN_LINE.search(line)
        day_m    = _DAY_IN_LINE.search(suffix)
        location = ""
        for word in _HEBREW_WORD.findall(suffix):
            if word not in _HEBREW_DAY_WORDS:
                location = word
                break
        return {
            "raw_date":    date_m.group(1) if date_m else "",
            "day":         day_m.group(1) if day_m else "—",
            "location":    location,
            "entry":       g[7],
            "exit":        g[6],
            "break":       g[5],
            "total":       g[4],
            "pct_100":     g[3],
            "pct_125":     g[2],
            "pct_150":     g[1],
            "pct_shabbat": g[0],
        }

    def _parse_summary(self, lines: list[str]) -> dict:
        summary: dict = {}

        for line in lines:
            if _COMPANY_RE.search(line):
                clean = re.sub(r"[\u200e\u200f]", "", line).strip()
                clean = re.sub(r"\s+ND\s*", " ", clean).strip()
                summary.setdefault("company_name", clean)
                break

        for line in lines:
            stripped = line.strip()

            fm = _FOOTER_LINE.match(stripped)
            if fm:
                summary.setdefault("days",     int(fm.group(1)))
                summary.setdefault("total_h",  float(fm.group(3)))
                summary.setdefault("pct_100",  float(fm.group(4)))
                summary.setdefault("pct_125",  float(fm.group(5)))
                summary.setdefault("pct_150",  float(fm.group(6)))
                summary.setdefault("pct_shab", float(fm.group(7)))
                continue

            tm = _FOOTER_TRVL.search(stripped)
            if tm:
                summary.setdefault("travel", float(tm.group(1) or tm.group(2)))

            bm = _FOOTER_BONUS.search(stripped)
            if bm:
                summary.setdefault("bonus", float(bm.group(1) or bm.group(2)))

        logger.debug("TypeAParser._parse_summary: %s", summary)
        return summary

    def _rows_to_domain(self, rows: list[dict]) -> tuple[AttendanceRow, ...]:
        if not rows:
            logger.error("TypeAParser._rows_to_domain: no raw rows received")
            raise NoRowsError("TYPE_A")

        result: list[AttendanceRow] = []
        for raw in rows:
            clock = self._parse_clock(raw)
            if clock is None:
                continue

            row_date  = self._parse_date(raw["raw_date"]) if raw.get("raw_date") else None
            break_rec = self._make_break(raw, clock.entry)

            pct_100  = self._hhmm_to_hours(raw.get("pct_100",     "") or "")
            pct_125  = self._hhmm_to_hours(raw.get("pct_125",     "") or "")
            pct_150  = self._hhmm_to_hours(raw.get("pct_150",     "") or "")
            pct_shab = self._hhmm_to_hours(raw.get("pct_shabbat", "") or "")
            ot_total = round(pct_100 + pct_125 + pct_150 + pct_shab, 2)

            overtime = OvertimeBuckets(
                regular_ot=round(pct_100,  2),
                band_125  =round(pct_125,  2),
                band_150  =round(pct_150,  2),
                weekend_ot=round(pct_shab, 2),
                total_ot  =ot_total,
            )

            day_raw  = raw.get("day", "—")
            day_name = f"יום {day_raw}" if day_raw and day_raw != "—" else "—"

            result.append(AttendanceRow(
                row_date    = row_date or date.today(),
                day_name    = day_name,
                clock       = clock,
                total_hours = self._hhmm_to_hours(raw.get("total", "") or ""),
                location    = raw.get("location") or None,
                break_rec   = break_rec,
                overtime    = overtime,
            ))

        if not result:
            logger.error("TypeAParser._rows_to_domain: all rows had invalid clock pairs")
            raise InvalidClockError("TYPE_A")

        result.sort(key=lambda r: r.row_date)
        logger.debug("TypeAParser._rows_to_domain: built %d domain rows", len(result))
        return tuple(result)

    def _summary_to_domain(self, summary: dict) -> ReportSummary:
        return ReportSummary(
            company_name     = summary.get("company_name"),
            total_days       = summary.get("days"),
            total_hours      = summary.get("total_h"),
            ot_100           = summary.get("pct_100"),
            ot_125           = summary.get("pct_125"),
            ot_150           = summary.get("pct_150"),
            ot_shabbat       = summary.get("pct_shab"),
            travel_allowance = summary.get("travel"),
            bonus            = summary.get("bonus"),
        )

    def _make_break(self, raw: dict, shift_entry: object) -> Optional[BreakRecord]:
        brk_time = self._parse_time(raw.get("break", ""))
        if not brk_time:
            return None
        dur_min = brk_time.hour * 60 + brk_time.minute
        if dur_min <= 0:
            return None
        entry: dt_time = shift_entry  # type: ignore[assignment]
        end_min  = entry.hour * 60 + entry.minute + dur_min
        brk_exit = dt_time(end_min // 60, end_min % 60)
        return BreakRecord(
            break_type  = BreakType.LUNCH,
            clock       = TimeRange(entry=entry, exit=brk_exit),
            duration_min= dur_min,
        )
