"""
parsers/base_parser.py
======================
Abstract Base Parser — the template-method contract every concrete parser fulfils.

Abstract members (each subclass implements):
─────────────────────────────────────────────
  report_type          →  str property   ("TYPE_A" / "TYPE_B")
  _is_header_line(line)→  bool           skip company names, column headers, separators
  _parse_row(line)     →  dict | None    extract one data row as a raw dict
  _parse_summary(lines)→  dict           extract header / footer metadata
  _rows_to_domain(rows)→  tuple[AttendanceRow, ...]   convert raw dicts → domain objects
  _summary_to_domain(s)→  ReportSummary              convert summary dict → domain object

Template method (shared, do NOT override):
──────────────────────────────────────────
  parse(text, source_file) → AttendanceReport
      1. Split text into lines.
      2. Call _parse_summary() with all lines.
      3. Filter header/separator lines via _is_header_line().
      4. Call _parse_row() per remaining line; collect non-None dicts.
      5. Call _rows_to_domain() and _summary_to_domain().
      6. Assemble and return AttendanceReport — no subclass needed for step 6.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from datetime import date, time
from typing import Optional

from domain.models import AttendanceReport, AttendanceRow, ReportSummary, TimeRange
from errors import InvalidClockError, NoRowsError, ParseError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract Base Parser
# ---------------------------------------------------------------------------

class BaseParser(ABC):
    """
    Template-method base class for all document-type parsers.

    Subclasses implement six focused members and get parse() for free.
    """

    # ── Abstract: identity ──────────────────────────────────────────────────

    @property
    @abstractmethod
    def report_type(self) -> str:
        """
        The string key for this parser's document type, e.g. "TYPE_A".
        Must match a key in config/rules.RULES_REGISTRY.
        """
        ...

    # ── Abstract: text-level extraction ────────────────────────────────────

    @abstractmethod
    def _is_header_line(self, line: str) -> bool:
        """
        Return True if *line* is a header, separator, or watermark row that
        must be skipped before _parse_row is attempted.
        Must never raise.
        """
        ...

    @abstractmethod
    def _parse_row(self, line: str) -> Optional[dict]:
        """
        Try to parse *line* as a single data row.
        Returns a plain dict of raw string values, or None if not a data row.
        Must never raise.
        """
        ...

    @abstractmethod
    def _parse_summary(self, lines: list[str]) -> dict:
        """
        Extract header / footer metadata from the full line list.
        Returns a plain dict (keys are parser-specific).
        """
        ...

    # ── Abstract: dict → domain conversion ─────────────────────────────────

    @abstractmethod
    def _rows_to_domain(self, rows: list[dict]) -> tuple[AttendanceRow, ...]:
        """
        Convert the list of raw row dicts (from _parse_row) into an immutable
        tuple of AttendanceRow domain objects.

        Invalid clock pairs (exit ≤ entry) should be silently dropped here;
        the RulesEngine flags them on the assembled report.

        Raises ParseError if no valid rows could be built.
        """
        ...

    @abstractmethod
    def _summary_to_domain(self, summary: dict) -> ReportSummary:
        """
        Convert the raw summary dict (from _parse_summary) into a ReportSummary.
        Missing / unparseable values should become None rather than raising.
        """
        ...

    # ── Template method ──────────────────────────────────────────────────────

    def parse(self, text: str, source_file: str = "") -> AttendanceReport:
        """
        Orchestrates the full parse pipeline.

        Args:
            text:        Normalised OCR text (from PDFExtractor.extract()).
            source_file: Original PDF filename (for logging / tracing).

        Returns:
            A frozen AttendanceReport.

        Raises:
            NoRowsError:      propagated from _rows_to_domain() if no rows found.
            InvalidClockError: propagated when all rows have bad clocks.
        """
        logger.info(
            "BaseParser.parse: starting  type=%s  source=%s  chars=%d",
            self.report_type, source_file or "<none>", len(text),
        )

        lines = text.splitlines()

        summary_dict = self._parse_summary(lines)
        logger.debug("BaseParser.parse: summary extracted  keys=%s", list(summary_dict))

        raw_rows: list[dict] = []
        skipped = 0
        for line in lines:
            stripped = line.strip()
            if not stripped or self._is_header_line(stripped):
                skipped += 1
                continue
            result = self._parse_row(stripped)
            if result is not None:
                raw_rows.append(result)

        logger.debug(
            "BaseParser.parse: raw rows=%d  skipped=%d", len(raw_rows), skipped
        )

        rows    = self._rows_to_domain(raw_rows)
        summary = self._summary_to_domain(summary_dict)

        logger.info(
            "BaseParser.parse: done  type=%s  domain_rows=%d", self.report_type, len(rows)
        )

        return AttendanceReport(
            report_type=self.report_type,
            rows=rows,
            summary=summary,
        )

    # ── Shared static helpers ────────────────────────────────────────────────

    @staticmethod
    def _parse_date(text: str) -> Optional[date]:
        """Parse the first date found in *text* (D/M/YY, DD/MM/YYYY, YYYY-MM-DD)."""
        patterns = [
            (r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})", "dmy4"),
            (r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})",  "dmy2"),
            (r"(\d{4})[/\-](\d{2})[/\-](\d{2})",       "ymd"),
        ]
        for pat, fmt in patterns:
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
        """Parse 'H:MM' or 'HH:MM' → datetime.time.  Returns None on failure."""
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
        """Extract the first decimal or integer number from *text*."""
        m = re.search(r"\d+[.,]\d+|\d+", text)
        return float(m.group(0).replace(",", ".")) if m else None

    @staticmethod
    def _hhmm_to_hours(value: str) -> float:
        """Convert 'H:MM' / 'HH:MM' to decimal hours.  Falls back to float()."""
        m = re.match(r"(\d+):(\d{2})$", (value or "").strip())
        if m:
            return int(m.group(1)) + int(m.group(2)) / 60
        try:
            return float(str(value).replace(",", "."))
        except (ValueError, TypeError):
            return 0.0

    @staticmethod
    def _safe_clock(entry: Optional[time], exit_: Optional[time]) -> Optional[TimeRange]:
        """
        Build a TimeRange only when both times are present and exit > entry.
        Returns None silently — the RulesEngine will flag the violation later.
        """
        if not entry or not exit_:
            return None
        try:
            return TimeRange(entry=entry, exit=exit_)
        except ValueError:
            return None

    def _parse_clock(self, raw: dict) -> Optional[TimeRange]:
        """Parse 'entry' and 'exit' from a raw row dict into a validated TimeRange."""
        return self._safe_clock(
            self._parse_time(raw.get("entry", "")),
            self._parse_time(raw.get("exit",  "")),
        )
