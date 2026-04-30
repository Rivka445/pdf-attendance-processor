"""
parsers/base_parser.py
======================
Abstract base class for report parsers.

Pattern: Template Method
  parse() defines the high-level algorithm:
    1. _parse_summary(lines) → ReportSummary
    2. _extract_rows(lines)  → list[AttendanceRow]
    3. assemble into AttendanceReport

Concrete subclasses override only the steps that differ between report types.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from datetime import date, time
from typing import Optional

from domain.models import AttendanceReport, AttendanceRow, ReportSummary, TimeRange
from domain.errors import InvalidClockError, NoRowsError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared OCR noise cleanup — used by all parsers
# ---------------------------------------------------------------------------

_RTL_CHARS = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_SHEKEL_RE = re.compile(r"\u20aa")


def clean_ocr(line: str) -> str:
    """Strip RTL marks and replace shekel sign with digit zero."""
    line = _RTL_CHARS.sub("", line)
    return _SHEKEL_RE.sub("0", line)


class BaseParser(ABC):
    """
    Common skeleton for TYPE_A and TYPE_B parsers.

    Subclasses implement:
        report_type        – string identifier e.g. 'TYPE_A'
        _parse_summary()   – extracts header/footer → ReportSummary
        _parse_row()       – parses one data line   → AttendanceRow | None
        _is_header_line()  – True for headers / separators to skip
    """

    @property
    @abstractmethod
    def report_type(self) -> str: ...

    # ── Template method ───────────────────────────────────────────────────

    def parse(self, text: str, source_file: str = "") -> AttendanceReport:
        """Full parse pipeline. Do not override."""
        logger.debug("BaseParser.parse: starting  type=%s  source=%s  chars=%d",
                    self.report_type, source_file or "<none>", len(text))

        lines   = text.splitlines()
        summary = self._parse_summary(lines)
        rows    = self._extract_rows(lines)

        if not rows:
            raise NoRowsError(self.report_type)

        logger.debug("BaseParser.parse: done  type=%s  rows=%d", self.report_type, len(rows))
        return AttendanceReport(report_type=self.report_type, rows=tuple(rows), summary=summary)

    # ── Abstract steps ────────────────────────────────────────────────────

    @abstractmethod
    def _parse_summary(self, lines: list[str]) -> ReportSummary:
        """Extract header/footer metadata from all lines."""

    @abstractmethod
    def _parse_row(self, line: str) -> AttendanceRow | None:
        """Parse one data line into an AttendanceRow, or None if not a data row."""

    @abstractmethod
    def _is_header_line(self, line: str) -> bool:
        """True if the line is a column header, separator, or page header."""

    # ── Shared implementation ─────────────────────────────────────────────

    def _extract_rows(self, lines: list[str]) -> list[AttendanceRow]:
        rows: list[AttendanceRow] = []
        for line in lines:
            stripped = line.strip()
            if not stripped or self._is_header_line(stripped):
                continue
            try:
                row = self._parse_row(stripped)
                if row is not None:
                    rows.append(row)
            except (ValueError, IndexError) as exc:
                logger.debug("Skipping unparseable line %r: %s", stripped[:60], exc)
        rows = self._post_process_rows(rows)
        rows.sort(key=lambda r: r.row_date)
        return rows

    def _post_process_rows(self, rows: list[AttendanceRow]) -> list[AttendanceRow]:
        """Hook for subclasses to fix up rows after initial parsing (e.g. date inference)."""
        return rows

    # ── Shared static helpers ─────────────────────────────────────────────

    @staticmethod
    def _parse_date(text: str) -> Optional[date]:
        for pat, fmt in [
            (r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", "dmy4"),
            (r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})",  "dmy2"),
            (r"(\d{4})[/\-](\d{2})[/\-](\d{2})",       "ymd"),
        ]:
            m = re.search(pat, text)
            if not m:
                continue
            g = m.groups()
            try:
                if fmt == "ymd":
                    return date(int(g[0]), int(g[1]), int(g[2]))
                y = int(g[2])
                if y < 100:
                    y += 2000
                return date(y, int(g[1]), int(g[0]))
            except ValueError:
                continue
        return None

    @staticmethod
    def _parse_time(raw: str) -> Optional[time]:
        if not raw:
            return None
        m = re.match(r"(\d{1,2}):(\d{2})", raw.strip())
        if not m:
            return None
        try:
            return time(int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None

    @staticmethod
    def _parse_float(text: str) -> Optional[float]:
        m = re.search(r"\d+[.,]\d+|\d+", text)
        return float(m.group(0).replace(",", ".")) if m else None

    @staticmethod
    def _hhmm_to_hours(value: str) -> float:
        m = re.match(r"(\d+):(\d{2})$", (value or "").strip())
        if m:
            return int(m.group(1)) + int(m.group(2)) / 60
        try:
            return float(str(value).replace(",", "."))
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _safe_clock(entry: Optional[time], exit_: Optional[time]) -> Optional[TimeRange]:
        if not entry or not exit_:
            return None
        try:
            return TimeRange(entry=entry, exit=exit_)
        except ValueError:
            return None
