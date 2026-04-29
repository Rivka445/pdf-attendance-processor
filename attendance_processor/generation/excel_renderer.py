"""
generation/excel_renderer.py
=============================
Renders an AttendanceReport to an Excel workbook (.xlsx) using *openpyxl*.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from domain.models import AttendanceReport, AttendanceRow
from errors import MissingRendererError, OutputDirectoryError, RenderingError
from generation.base import BaseRenderer

logger = logging.getLogger(__name__)


def _fmt_hours(decimal_hours: float) -> str:
    """Format decimal hours as H.MM (minutes as decimal digits)."""
    h = int(decimal_hours)
    m = round((decimal_hours - h) * 60)
    if m == 60:
        h += 1
        m = 0
    return f"{h}.{m:02d}"


# ---------------------------------------------------------------------------
# Column specs — (header_label, extractor_key, number_format, min_width)
# ---------------------------------------------------------------------------

_COLUMNS_TYPE_A: list[tuple[str, str, str, int]] = [
    ("תאריך",     "date",     "DD/MM/YYYY", 12),
    ("יום",       "day",      "@",           6),
    ("כניסה",     "entry",    "HH:MM",       7),
    ("יציאה",     "exit",     "HH:MM",       7),
    ("הפסקה",     "break",    "0",           8),
    ("שעות נטו", "net",      "@",          10),
    ("OT 100%",   "ot_100",   "@",           8),
    ("OT 125%",   "ot_125",   "@",           8),
    ("OT 150%",   "ot_150",   "@",           8),
    ("מקום",      "location", "@",          12),
    ("שבת",       "shabbat",  "@",           8),
]

_COLUMNS_TYPE_B: list[tuple[str, str, str, int]] = [
    ("תאריך",    "date",  "DD/MM/YYYY", 12),
    ("יום",      "day",   "@",           6),
    ("כניסה",    "entry", "HH:MM",       7),
    ("יציאה",    "exit",  "HH:MM",       7),
    ("שעות נטו","net",   "@",          10),
    ("הערות",    "notes", "@",          20),
]

_COLUMN_MAP: dict[str, list[tuple[str, str, str, int]]] = {
    "TYPE_A": _COLUMNS_TYPE_A,
    "TYPE_B": _COLUMNS_TYPE_B,
}

# Columns that get a SUM totals row
_NUMERIC_KEYS = {"net", "ot_100", "ot_125", "ot_150", "shabbat"}


# ---------------------------------------------------------------------------
# Cell-value extractor
# ---------------------------------------------------------------------------

def _cell_value(row: AttendanceRow, key: str) -> Any:
    if key == "date":
        return row.row_date
    if key == "day":
        return row.day_name
    if key == "entry":
        return row.clock.entry
    if key == "exit":
        return row.clock.exit
    if key == "break":
        return row.break_rec.duration_min if row.break_rec else 0
    if key == "net":
        return row.net_hours
    if key == "ot_100":
        return row.overtime.regular_ot if (row.overtime and row.overtime.regular_ot) else 0.0
    if key == "ot_125":
        return row.overtime.band_125   if (row.overtime and row.overtime.band_125)   else 0.0
    if key == "ot_150":
        return row.overtime.band_150   if (row.overtime and row.overtime.band_150)   else 0.0
    if key == "shabbat":
        return row.overtime.weekend_ot if (row.overtime and row.overtime.weekend_ot) else 0.0
    if key == "location":
        return row.location or ""
    if key == "notes":
        return row.notes or ""
    return ""


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class ExcelRenderer(BaseRenderer):
    """Renders an AttendanceReport to a .xlsx file."""

    def __init__(
        self,
        header_fill_hex: str = "1E3A5F",
        column_map: dict[str, list[tuple[str, str, str, int]]] | None = None,
    ) -> None:
        self._header_hex = header_fill_hex.lstrip("#").upper()
        self._column_map = column_map if column_map is not None else _COLUMN_MAP

    def render(self, report: AttendanceReport, output_path: Path) -> Path:
        logger.info(
            "ExcelRenderer.render: starting  type=%s  rows=%d",
            report.report_type, len(report.rows),
        )

        try:
            import openpyxl
            from openpyxl.styles import Alignment, Font, PatternFill
            from openpyxl.utils import get_column_letter
        except ImportError as exc:
            raise RenderingError("openpyxl is not installed.") from exc

        columns = self._resolve_columns(report.report_type)
        self._ensure_output_dir(output_path)
        default_name = (
            f"attendance_{report.report_type.lower()}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
        dest = self._resolve_output_path(output_path, default_name)

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "נוכחות"
        ws.sheet_view.rightToLeft = True

        header_fill  = PatternFill(start_color=self._header_hex, end_color=self._header_hex, fill_type="solid")
        header_font  = Font(bold=True, color="FFFFFF", size=11)
        alt_fill     = PatternFill(start_color="EEF3FA", end_color="EEF3FA", fill_type="solid")
        total_fill   = PatternFill(start_color="D0DFF5", end_color="D0DFF5", fill_type="solid")
        center_align = Alignment(horizontal="center", vertical="center")
        right_align  = Alignment(horizontal="right",  vertical="center")

        # Header row
        for col_idx, (label, _key, _fmt, _min_w) in enumerate(columns, start=1):
            cell = ws.cell(row=1, column=col_idx, value=label)
            cell.fill      = header_fill
            cell.font      = header_font
            cell.alignment = center_align

        # Data rows
        for row_idx, row in enumerate(report.rows, start=2):
            is_even = (row_idx % 2 == 0)
            for col_idx, (_label, key, fmt, _min_w) in enumerate(columns, start=1):
                cell = ws.cell(row=row_idx, column=col_idx, value=_cell_value(row, key))
                cell.number_format = fmt
                cell.alignment     = right_align
                if is_even:
                    cell.fill = alt_fill

        # Totals row
        totals_row_idx = len(report.rows) + 2
        totals_font    = Font(bold=True)
        for col_idx, (_label, key, fmt, _min_w) in enumerate(columns, start=1):
            if key in _NUMERIC_KEYS:
                # Sum the string-formatted values by recomputing from rows
                total = 0.0
                for row in report.rows:
                    if key == "net":
                        total += row.net_hours or 0.0
                    elif key == "ot_100":
                        total += (row.overtime.regular_ot if row.overtime else 0.0)
                    elif key == "ot_125":
                        total += (row.overtime.band_125   if row.overtime else 0.0)
                    elif key == "ot_150":
                        total += (row.overtime.band_150   if row.overtime else 0.0)
                    elif key == "shabbat":
                        total += (row.overtime.weekend_ot if row.overtime else 0.0)
                total_cell = ws.cell(row=totals_row_idx, column=col_idx, value=_fmt_hours(total))
                total_cell.font          = totals_font
                total_cell.fill          = total_fill
                total_cell.alignment     = right_align
            else:
                cell = ws.cell(row=totals_row_idx, column=col_idx)
                cell.fill = total_fill

        ws.cell(row=totals_row_idx, column=1, value='סה"כ').font = totals_font

        # Auto column widths
        for col_idx, (_label, _key, _fmt, min_w) in enumerate(columns, start=1):
            max_len = min_w
            for row_obj in ws.iter_rows(min_row=1, max_row=totals_row_idx, min_col=col_idx, max_col=col_idx):
                for cell in row_obj:
                    try:
                        clen = len(str(cell.value)) if cell.value is not None else 0
                        if clen > max_len:
                            max_len = clen
                    except Exception:
                        pass
            ws.column_dimensions[get_column_letter(col_idx)].width = max_len + 2

        self._add_summary_sheet(wb, report)

        try:
            wb.save(str(dest))
        except OSError as exc:
            raise OutputDirectoryError(dest, str(exc)) from exc

        logger.info("ExcelRenderer.render: written → %s", dest)
        return dest

    def _resolve_columns(self, report_type: str) -> list[tuple[str, str, str, int]]:
        columns = self._column_map.get(report_type)
        if columns is None:
            raise MissingRendererError(report_type=report_type, registered=list(self._column_map))
        return columns

    def _add_summary_sheet(self, wb: Any, report: AttendanceReport) -> None:
        from openpyxl.styles import Font, PatternFill
        ws = wb.create_sheet(title="סיכום")
        ws.sheet_view.rightToLeft = True

        s = report.summary
        metrics: list[tuple[str, Any]] = []

        if s.company_name:                      metrics.append(("שם חברה",          s.company_name))
        if s.total_days   is not None:          metrics.append(("ימי עבודה",        s.total_days))
        if s.total_hours  is not None:          metrics.append(('סה"כ שעות',        _fmt_hours(s.total_hours)))

        if report.report_type == "TYPE_A":
            for lbl, val in [
                ("OT 100%",  s.ot_100),
                ("OT 125%",  s.ot_125),
                ("OT 150%",  s.ot_150),
                ("שבת",      s.ot_shabbat),
                ("נסיעות",   s.travel_allowance),
                ("בונוס",    s.bonus),
            ]:
                if val is not None:
                    metrics.append((lbl, _fmt_hours(val)))
        elif report.report_type == "TYPE_B":
            if s.employee_card_month:           metrics.append(("כרטיס עובד לחודש", s.employee_card_month))
            if s.hourly_rate  is not None:      metrics.append(("תעריף לשעה",       f"{s.hourly_rate:.2f} ₪"))
            if s.total_pay    is not None:      metrics.append(('סה"כ לתשלום',      f"{s.total_pay:.2f} ₪"))

        header_fill = PatternFill(start_color=self._header_hex, end_color=self._header_hex, fill_type="solid")
        ws.cell(row=1, column=1, value="מדד").fill  = header_fill
        ws.cell(row=1, column=1).font               = Font(bold=True, color="FFFFFF")
        ws.cell(row=1, column=2, value="ערך").fill  = header_fill
        ws.cell(row=1, column=2).font               = Font(bold=True, color="FFFFFF")

        for r_idx, (lbl, val) in enumerate(metrics, start=2):
            ws.cell(row=r_idx, column=1, value=lbl)
            ws.cell(row=r_idx, column=2, value=val)

        ws.column_dimensions["A"].width = 22
        ws.column_dimensions["B"].width = 18


