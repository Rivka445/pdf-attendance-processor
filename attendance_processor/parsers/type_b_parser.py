"""
parsers/type_b_parser.py
=========================
Concrete parser for TYPE_B documents (hourly / part-time layout).

Column structure (pipe-delimited):
  | תאריך | יום | כניסה | יציאה | סה"כ | הערות |

No break or overtime columns.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Optional

from domain.models import AttendanceRow, ReportSummary
from domain.errors import InvalidClockError, NoRowsError
from parsers.base_parser import BaseParser

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_SKIP = re.compile(
    r'(?:סה["\u05f4:]כ\s+)?ימי\s+עבודה'
    r'|שעות\s+חודשי'
    r'|מחיר\s+לשעה'
    r'|לתשלום'
    r'|כרטיס\s+עובד'
    r'|עבודה\s+לחודש'
    r'|תאריך.*(?:יום|כניסה)'   # header row
    r'|בשבוע.*כניסה'
    r'|^[-=|─\s]{3,}$',
    re.UNICODE,
)

# Accept pipe-delimited rows; be lenient about extra pipes, spaces and OCR noise
# Date: digits with / separators (allowing surrounding noise)
# Day:  any text between pipes (may be Hebrew day or garbled)
# Time: H:MM, HH:MM, or 3-4 digit run (OCR drops the colon)
_TIME_PAT = r"(\d{1,2}:?\d{2})"
_DATE_PAT = r"(\d{1,2}/\d{1,2}/\d{2,4})"

_ROW = re.compile(
    r"\|[^|]*?" + _DATE_PAT +          # date (inside first cell)
    r"[^|]*\|+\s*([^|\d\n]{0,12}?)\s*" # day name (lenient — any non-pipe, non-digit text)
    r"\|+" + r"\s*" + _TIME_PAT +       # entry time
    r"[^|]*\|+" + r"\s*" + _TIME_PAT + # exit  time
    r"[^|]*\|+\s*" + r"([\d:.]+)",     # total hours
    re.UNICODE,
)

_WORK_DAYS = re.compile(r'(?:ימי\s+)?עבודה\s+לחודש[^\d\n]*(\d+)',             re.UNICODE)
_MONTHLY   = re.compile(r'שעות\s+חודשי[^\d\n]*([\d.]+)',                        re.UNICODE)
_RATE      = re.compile(r'(?:מחיר|תעריף)\s+(?:לשעה|שעתי)[^\d\n]*([\d.]+)',     re.UNICODE)
_PAY       = re.compile(r'לתשלום[^\d\n]*([\d.]+)',                               re.UNICODE)
_CARD_MON  = re.compile(
    r'(?:כרטיס\s+עובד\s+)?(?:לחודש|עבודה\s+לחודש)\s*[-–]?\s*(\d{1,2}[/\-]\d{2,4})?',
    re.UNICODE,
)


def _norm_time(s: str) -> str:
    """Insert colon into OCR-garbled times: '1200' → '12:00', '830' → '8:30'."""
    s = (s or "").strip()
    if ":" in s:
        return s
    if len(s) == 4:
        return f"{s[:2]}:{s[2:]}"
    if len(s) == 3:
        return f"{s[0]}:{s[1:]}"
    return s


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class TypeBParser(BaseParser):
    """Parses TYPE_B scanned attendance reports."""

    @property
    def report_type(self) -> str:
        return "TYPE_B"

    def _is_header_line(self, line: str) -> bool:
        return bool(_SKIP.search(line))

    def _parse_row(self, line: str) -> Optional[dict]:
        m = _ROW.search(line)
        if not m:
            return None
        raw_date, day_raw, entry_raw, exit_raw, total_raw = m.groups()
        # Normalise garbled times
        entry = _norm_time(entry_raw)
        exit_ = _norm_time(exit_raw)
        # Clean day name: keep only Hebrew letters; fall back to "—"
        day_clean = re.sub(r"[^\u05d0-\u05ea]", "", day_raw or "").strip()
        return {
            "raw_date": raw_date,
            "day":      day_clean if len(day_clean) >= 2 else "—",
            "entry":    entry,
            "exit":     exit_,
            "total":    total_raw,
        }

    def _parse_summary(self, lines: list[str]) -> dict:
        text = "\n".join(lines)

        def _find(pat: re.Pattern) -> Optional[float]:
            m = pat.search(text)
            return float(m.group(1).replace(",", ".")) if m else None

        summary: dict = {
            "work_days": _find(_WORK_DAYS),
            "total_h":   _find(_MONTHLY),
            "rate":      _find(_RATE),
            "pay":       _find(_PAY),
        }

        # Extract month label for "כרטיס עובד לחודש"
        for line in lines:
            cm = _CARD_MON.search(line)
            if cm and ("לחודש" in line or "עבודה" in line):
                summary["card_month"] = cm.group(1) or line.strip()
                break

        return summary

    def _rows_to_domain(self, rows: list[dict]) -> tuple[AttendanceRow, ...]:
        if not rows:
            logger.error("TypeBParser._rows_to_domain: no raw rows received")
            raise NoRowsError("TYPE_B")

        result: list[AttendanceRow] = []
        for raw in rows:
            clock = self._parse_clock(raw)
            if clock is None:
                logger.debug("TypeBParser._rows_to_domain: skipping row bad clock  raw=%s", raw)
                continue
            row_date = self._parse_date(raw["raw_date"]) if raw.get("raw_date") else None
            day_raw  = raw.get("day", "—")
            result.append(AttendanceRow(
                row_date    = row_date or date.today(),
                day_name    = f"יום {day_raw}" if day_raw and day_raw != "—" else "—",
                clock       = clock,
                total_hours = self._hhmm_to_hours(raw.get("total", "") or ""),
            ))

        if not result:
            logger.error("TypeBParser._rows_to_domain: all rows had invalid clock pairs")
            raise InvalidClockError("TYPE_B")

        result.sort(key=lambda r: r.row_date)
        logger.debug("TypeBParser._rows_to_domain: built %d domain rows", len(result))
        return tuple(result)

    def _summary_to_domain(self, summary: dict) -> ReportSummary:
        work_days = summary.get("work_days")
        # Derive employee_card_month from card_month or from work_days context
        card_month = summary.get("card_month")
        return ReportSummary(
            total_days           = int(work_days) if work_days is not None else None,
            total_hours          = summary.get("total_h"),
            hourly_rate          = summary.get("rate"),
            total_pay            = summary.get("pay"),
            employee_card_month  = str(card_month) if card_month else None,
        )

