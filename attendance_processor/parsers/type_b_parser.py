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
from parsers.base_parser import BaseParser, clean_ocr

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

_SKIP = re.compile(
    r'(?:סה["ׄ:]כ\s+)?ימי\s+עבודה'
    r'|שעות\s+חודשי'
    r'|מחיר\s+לשעה'
    r'|לתשלום'
    r'|כרטיס\s+עובד'
    r'|עבודה\s+לחודש'
    r'|תאריך.*(?:יום|כניסה)'
    r'|בשבוע.*כניסה'
    r'|^[-=|─\s]{3,}$',
    re.UNICODE,
)

_TIME_PAT  = r"(\d{1,2}:?\d{2})"
_DATE_PAT  = r"(\d{1,2}/\d{1,2}/\d{2,4})"
_TOTAL_PAT = r"(\d{1,3}(?:[:.]\d{0,2}|[.,]\d+)?)"

_ROW = re.compile(
    r"\|[^|]*?" + _DATE_PAT +
    r"[^|]*\|+\s*([^|\d\n]{0,15}?)\s*"
    r"\|+\s*" + _TIME_PAT +
    r"(?:[^|]*\|+)+?\s*" + _TIME_PAT +
    r"(?:[^|]*\|+)+?\s*" + _TOTAL_PAT +
    r"[^\d|\n]*",
    re.UNICODE,
)

_WORK_DAYS = re.compile(r'(?:ימי\s+)?עבודה\s+לחודש[^\d\n]*(\d+)',           re.UNICODE)
_MONTHLY   = re.compile(r'שעות\s+חודשי[^\d\n]*([\d.]+)',                     re.UNICODE)
_RATE      = re.compile(r'(?:מחיר|תעריף)\s+(?:לשעה|שעתי)[^\d\n]*([\d.]+)',  re.UNICODE)
_PAY       = re.compile(r'לתשלום[^\d\n]*([\d.]+)',                            re.UNICODE)
_CARD_MON  = re.compile(
    r'(?:כרטיס\s+עובד\s+)?(?:לחודש|עבודה\s+לחודש)\s*[-–]?\s*(\d{1,2}[/\-]\d{2,4})?',
    re.UNICODE,
)


def _norm_time(s: str) -> str:
    s = (s or "").strip()
    if ":" in s:
        return s
    if len(s) == 5 and s[:2].isdigit() and s[2:].isdigit():
        return f"{s[:2]}:{s[2:4]}"
    if len(s) == 4:
        return f"{s[:2]}:{s[2:]}"
    if len(s) == 3:
        return f"{s[0]}:{s[1:]}"
    return s


def _preprocess(line: str) -> str:
    line = clean_ocr(line)
    line = re.sub(r"\[(?=[^|])", "|", line)
    line = re.sub(r"\(", "|", line)
    line = re.sub(r"(\|\s*\|\s*)([\u05d0-\u05ea]{2,})", r"| \2", line)
    return line


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

    def _parse_row(self, line: str) -> AttendanceRow | None:
        line = _preprocess(line)
        m = _ROW.search(line)
        if not m:
            return None
        raw_date, day_raw, entry_raw, exit_raw, total_raw = m.groups()

        clock = self._safe_clock(
            self._parse_time(_norm_time(entry_raw)),
            self._parse_time(_norm_time(exit_raw)),
        )
        if clock is None:
            return None

        day_clean = re.sub(r"[^\u05d0-\u05ea]", "", day_raw or "").strip()
        return AttendanceRow(
            row_date    = self._parse_date(raw_date) or date.today(),
            day_name    = f"יום {day_clean}" if len(day_clean) >= 2 else "—",
            clock       = clock,
            total_hours = self._hhmm_to_hours(total_raw or ""),
        )

    def _parse_summary(self, lines: list[str]) -> ReportSummary:
        text = "\n".join(lines)

        def _find(pat: re.Pattern) -> Optional[float]:
            m = pat.search(text)
            return float(m.group(1).replace(",", ".")) if m else None

        card_month = None
        for line in lines:
            cm = _CARD_MON.search(line)
            if cm and ("לחודש" in line or "עבודה" in line):
                card_month = cm.group(1) or line.strip()
                break

        work_days = _find(_WORK_DAYS)
        return ReportSummary(
            total_days          = int(work_days) if work_days is not None else None,
            total_hours         = _find(_MONTHLY),
            hourly_rate         = _find(_RATE),
            total_pay           = _find(_PAY),
            employee_card_month = str(card_month) if card_month else None,
        )
