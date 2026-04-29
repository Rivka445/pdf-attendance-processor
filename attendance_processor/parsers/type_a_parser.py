"""
parsers/type_a_parser.py
=========================
Concrete parser for TYPE_A documents (נ.ע. הנשר כח אדם בע"מ).

Real column structure (verified from OCR — columns are reversed, RTL→LTR):
  OCR order: שבת | 150% | 125% | 100% | סה"כ | הפסקה | יציאה | כניסה | <Hebrew> | תאריך
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
    r"|בונוס|נסיעות"
    r"|Is\s*$",          # OCR noise line
    re.UNICODE,
)

# 8 consecutive HH:MM values (reversed RTL columns)
_ROW = re.compile(
    r"^[^\d]*"
    r"(\d{1,2}:\d{2})\s+"   # 1 שבת
    r"(\d{1,2}:\d{2})\s+"   # 2 150%
    r"(\d{1,2}:\d{2})\s+"   # 3 125%
    r"(\d{1,2}:\d{2})\s+"   # 4 100%
    r"(\d{1,2}:\d{2})\s+"   # 5 סה"כ total
    r"(\d{1,2}:\d{2})\s+"   # 6 הפסקה break
    r"(\d{1,2}:\d{2})\s+"   # 7 יציאה exit
    r"(\d{1,2}:\d{2})"      # 8 כניסה entry
    r"(.*)",                  # 9 suffix (Hebrew text: location, day, date)
    re.UNICODE,
)

_DATE_IN_LINE    = re.compile(r"(\d{1,2}/\d{1,2}/\d{2,4})")
_DAY_IN_LINE     = re.compile(r"יום\s+(\S+)", re.UNICODE)
_HEBREW_WORD     = re.compile(r"[\u05d0-\u05ea]{2,}", re.UNICODE)
_HEBREW_DAY_WORDS = frozenset({"ראשון","שני","שלישי","רביעי","חמישי","שישי","שבת","יום"})

# Footer patterns (reversed in OCR)
_FOOTER_100  = re.compile(r"([\d.]+)\s*\|?\s*100%\s*שעות", re.UNICODE)
_FOOTER_125  = re.compile(r"([\d.]+)\]?\s*125%\s*שעות",    re.UNICODE)
_FOOTER_150  = re.compile(r"([\d.]+)\]?\s*150%\s*שעות",    re.UNICODE)
_FOOTER_SHAB = re.compile(r"([\d.]+)\[?150%\s*(?:naw|שבת)",re.UNICODE)
_FOOTER_TRVL = re.compile(r"([\d.]+)\]?\s*\|?\s*נסיעות",   re.UNICODE)
_FOOTER_BONUS= re.compile(r"([\d.]+)\]?\s*\|?\s*בונוס",    re.UNICODE)
_FOOTER_DAYS = re.compile(r"(\d+)\s+(?:ימים|$)",            re.UNICODE)
_COMPANY_RE  = re.compile(r"(?:הנשר|נ\.ע\.|כח\s+אדם)[^\n]*", re.UNICODE)


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
        m = _ROW.search(line)
        if not m:
            return None
        g = m.groups()
        suffix   = g[8] or ""
        date_m   = _DATE_IN_LINE.search(line)
        day_m    = _DAY_IN_LINE.search(suffix)

        # Extract location: first Hebrew word in suffix that isn't a day-related word
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
        # Extract company name from header lines (before they are filtered as data)
        for line in lines:
            if _COMPANY_RE.search(line):
                # Clean the line: strip RTL markers, keep Hebrew + punctuation
                clean = re.sub(r"[\u200e\u200f]", "", line).strip()
                clean = re.sub(r"\s+ND\s*", " ", clean).strip()
                summary.setdefault("company_name", clean)
                break

        for line in lines:
            for pat, key in ((_FOOTER_100,  "pct_100"),
                             (_FOOTER_125,  "pct_125"),
                             (_FOOTER_150,  "pct_150"),
                             (_FOOTER_SHAB, "pct_shab"),
                             (_FOOTER_TRVL, "travel"),
                             (_FOOTER_BONUS,"bonus")):
                m = pat.search(line)
                if m:
                    summary[key] = float(m.group(1))
            dm = _FOOTER_DAYS.search(line)
            if dm:
                summary.setdefault("days", int(dm.group(1)))
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

            # Always create OvertimeBuckets so 125/150 show as 0.00 (not —)
            overtime = OvertimeBuckets(
                regular_ot=round(pct_100,  2),
                band_125  =round(pct_125,  2),
                band_150  =round(pct_150,  2),
                weekend_ot=round(pct_shab, 2),
                total_ot  =ot_total,
            )

            day_raw = raw.get("day", "—")
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

        # Sort chronologically; rows without a real date stay at the end
        result.sort(key=lambda r: r.row_date)

        logger.debug("TypeAParser._rows_to_domain: built %d domain rows", len(result))
        return tuple(result)

    def _summary_to_domain(self, summary: dict) -> ReportSummary:
        return ReportSummary(
            company_name     = summary.get("company_name"),
            total_days       = summary.get("days"),
            total_hours      = summary.get("pct_100"),
            ot_100           = summary.get("pct_100"),
            ot_125           = summary.get("pct_125"),
            ot_150           = summary.get("pct_150"),
            ot_shabbat       = summary.get("pct_shab"),
            travel_allowance = summary.get("travel"),
            bonus            = summary.get("bonus"),
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    def _make_break(self, raw: dict, shift_entry: object) -> Optional[BreakRecord]:
        """Build a BreakRecord from the HH:MM break column, or return None."""
        brk_time = self._parse_time(raw.get("break", ""))
        if not brk_time:
            return None
        dur_min = brk_time.hour * 60 + brk_time.minute
        if dur_min <= 0:
            return None
        entry: dt_time = shift_entry  # type: ignore[assignment]
        end_min = entry.hour * 60 + entry.minute + dur_min
        brk_exit = dt_time(end_min // 60, end_min % 60)
        return BreakRecord(
            break_type  = BreakType.LUNCH,
            clock       = TimeRange(entry=entry, exit=brk_exit),
            duration_min= dur_min,
        )


