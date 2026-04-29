"""
generation/html_renderer.py
============================
Renders an AttendanceReport to a self-contained HTML file.

TYPE_A columns: Date | Day | Entry | Exit | Break | Net h | OT 100% | OT 125% | OT 150% | Location | שבת
TYPE_B columns: Date | Day | Entry | Exit | Net h | Notes
Layout:  TYPE_A → header → table → summary footer
         TYPE_B → header → summary bar → table
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from domain.models import AttendanceReport, AttendanceRow
from domain.errors import MissingRendererError, OutputDirectoryError, RenderingError
from generation.base import BaseRenderer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hour formatting helper
# ---------------------------------------------------------------------------

def _fmt_hours(decimal_hours: float) -> str:
    """Format decimal hours as H.MM (minutes as two decimal digits).
    e.g. 3.25 → '3.15'  (3h 15min),  7.833... → '7.50'  (7h 50min).
    """
    h = int(decimal_hours)
    m = round((decimal_hours - h) * 60)
    if m == 60:
        h += 1
        m = 0
    return f"{h}.{m:02d}"


# ---------------------------------------------------------------------------
# Default column specs  — (header_label, extractor_key)
# ---------------------------------------------------------------------------

_COLUMNS_TYPE_A: list[tuple[str, str]] = [
    ("תאריך",       "date"),
    ("יום",         "day"),
    ("כניסה",       "entry"),
    ("יציאה",       "exit"),
    ("הפסקה",       "break"),
    ("שעות נטו",   "net"),
    ("OT 100%",     "ot_100"),
    ("OT 125%",     "ot_125"),
    ("OT 150%",     "ot_150"),
    ("מקום",        "location"),
    ("שבת",         "shabbat"),
]

_COLUMNS_TYPE_B: list[tuple[str, str]] = [
    ("תאריך",       "date"),
    ("יום",         "day"),
    ("כניסה",       "entry"),
    ("יציאה",       "exit"),
    ("שעות נטו",   "net"),
    ("הערות",       "notes"),
]

_DEFAULT_COLUMN_MAP: dict[str, list[tuple[str, str]]] = {
    "TYPE_A": _COLUMNS_TYPE_A,
    "TYPE_B": _COLUMNS_TYPE_B,
}

# ---------------------------------------------------------------------------
# Default colour themes
# ---------------------------------------------------------------------------

_DEFAULT_THEMES: dict[str, dict[str, str]] = {
    "TYPE_A": {
        "header_bg":      "#1e3a5f",
        "header_text":    "#ffffff",
        "even_row":       "#f0f4fa",
        "hover":          "#dce8f8",
        "border":         "#c5d4e8",
        "summary_bg":     "#e8eef6",
        "summary_accent": "#1e3a5f",
        "total_row":      "#d0dff5",
    },
    "TYPE_B": {
        "header_bg":      "#2d4a22",
        "header_text":    "#ffffff",
        "even_row":       "#f0f7ec",
        "hover":          "#d8edd0",
        "border":         "#b8d4ac",
        "summary_bg":     "#ecf4e8",
        "summary_accent": "#2d4a22",
        "total_row":      "#c8e0c0",
    },
}

_OT_PILL: dict[str, tuple[str, str]] = {
    "ot_100": ("#d1fae5", "#065f46"),
    "ot_125": ("#fef3c7", "#92400e"),
    "ot_150": ("#fee2e2", "#991b1b"),
}


# ---------------------------------------------------------------------------
# Cell-value extractor
# ---------------------------------------------------------------------------

def _cell_value(row: AttendanceRow, key: str) -> str:
    return html_cell_value(row, key)


def html_cell_value(row: AttendanceRow, key: str) -> str:
    if key == "date":
        return row.row_date.strftime("%d/%m/%Y")
    if key == "day":
        return row.day_name
    if key == "entry":
        return row.clock.entry.strftime("%H:%M")
    if key == "exit":
        return row.clock.exit.strftime("%H:%M")
    if key == "break":
        if row.break_rec is None:
            return "—"
        return f"{row.break_rec.duration_min} דק'" if row.break_rec.duration_min else "—"
    if key == "net":
        return _fmt_hours(row.net_hours)
    if key in _OT_PILL:
        if row.overtime is None:
            return "—"
        attr_map = {"ot_100": "regular_ot", "ot_125": "band_125", "ot_150": "band_150"}
        val = getattr(row.overtime, attr_map[key])
        bg, fg = _OT_PILL[key]
        return (
            f'<span style="display:inline-block;padding:1px 6px;'
            f'border-radius:10px;font-size:11px;font-weight:600;'
            f'background:{bg};color:{fg}">{_fmt_hours(val or 0.0)}</span>'
        )
    if key == "shabbat":
        if row.overtime is None:
            return "—"
        val = row.overtime.weekend_ot
        return _fmt_hours(val or 0.0)
    if key == "location":
        return row.location or "—"
    if key == "notes":
        return row.notes or "—"
    return "—"


# ---------------------------------------------------------------------------
# HTML-building helpers
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )


def _build_css(t: dict[str, str]) -> str:
    return (
        "<style>"
        "*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}"
        "body{font-family:'Segoe UI',Arial,sans-serif;font-size:13px;"
        "color:#1a1a1a;background:#f7f8fa;padding:24px;direction:rtl}"
        f".rpt-header{{background:{t['header_bg']};color:{t['header_text']};"
        "border-radius:8px 8px 0 0;padding:18px 24px 14px;"
        "display:flex;justify-content:space-between;align-items:flex-end}"
        ".rpt-header h1{font-size:20px;font-weight:700}"
        ".rpt-header .sub{font-size:13px;opacity:.85;margin-top:4px}"
        ".rpt-header .meta{font-size:11px;opacity:.8;text-align:left}"
        f".summary-bar{{background:{t['summary_bg']};border:1px solid {t['border']};"
        "padding:10px 24px;display:flex;flex-wrap:wrap;gap:24px}}"
        ".summary-bar .item{display:flex;flex-direction:column}"
        ".summary-bar .lbl{font-size:10px;color:#5a6a80;"
        "text-transform:uppercase;letter-spacing:.5px}"
        f".summary-bar .val{{font-size:15px;font-weight:600;color:{t['summary_accent']}}}"
        f".tbl-wrap{{overflow-x:auto;border:1px solid {t['border']};"
        "border-radius:0 0 8px 8px;background:#fff}}"
        "table{width:100%;border-collapse:collapse;font-size:12.5px}"
        f"thead tr{{background:{t['header_bg']};color:{t['header_text']}}}"
        "thead th{padding:9px 10px;text-align:right;font-weight:600;white-space:nowrap}"
        f"tbody tr:nth-child(even){{background:{t['even_row']}}}"
        f"tbody tr:hover{{background:{t['hover']}}}"
        "tbody td{padding:7px 10px;border-bottom:1px solid #e2e8f0;white-space:nowrap}"
        f".total-row{{background:{t.get('total_row', '#e0e8f0')}!important;font-weight:700}}"
        ".footer{margin-top:14px;font-size:10px;color:#8a9ab0;text-align:center}"
        "</style>"
    )


def _build_summary_bar(report: AttendanceReport, css_extra: str = "") -> str:
    s     = report.summary
    rtype = report.report_type
    items: list[tuple[str, str]] = []

    if s.total_days  is not None: items.append(("ימי עבודה", str(s.total_days)))
    if s.total_hours is not None: items.append(('סה"כ שעות', _fmt_hours(s.total_hours)))

    if rtype == "TYPE_A":
        for lbl, val in [
            ("OT 100%",  s.ot_100),
            ("OT 125%",  s.ot_125),
            ("OT 150%",  s.ot_150),
            ('שבת',      s.ot_shabbat),
            ("נסיעות",   s.travel_allowance),
            ("בונוס",    s.bonus),
        ]:
            if val is not None:
                items.append((lbl, _fmt_hours(val)))
    elif rtype == "TYPE_B":
        if s.employee_card_month:
            items.insert(0, ("כרטיס עובד לחודש", s.employee_card_month))
        for lbl, val, suffix in [
            ("תעריף לשעה",  s.hourly_rate, " ₪"),
            ('סה"כ לתשלום', s.total_pay,   " ₪"),
        ]:
            if val is not None:
                items.append((lbl, f"{val:.2f}{suffix}"))

    parts = "".join(
        f'<div class="item">'
        f'<span class="lbl">{_esc(lbl)}</span>'
        f'<span class="val">{_esc(val)}</span>'
        f'</div>'
        for lbl, val in items
    )
    return f'<div class="summary-bar"{css_extra}>{parts}</div>'


_NUMERIC_KEYS = {"net", "ot_100", "ot_125", "ot_150", "shabbat"}


def _totals_row(report: AttendanceReport, columns: list[tuple[str, str]]) -> str:
    """Build a bold totals <tr> summing all numeric columns."""
    cells: list[str] = []
    for i, (label, key) in enumerate(columns):
        if i == 0:
            cells.append("<td><strong>סה\"כ</strong></td>")
            continue
        if key not in _NUMERIC_KEYS:
            cells.append("<td>—</td>")
            continue
        total = 0.0
        for row in report.rows:
            if key == "net":
                total += row.net_hours or 0.0
            elif key == "ot_100":
                total += row.overtime.regular_ot
            elif key == "ot_125":
                total += row.overtime.band_125
            elif key == "ot_150":
                total += row.overtime.band_150
            elif key == "shabbat":
                total += row.overtime.weekend_ot
        cells.append(f"<td>{_fmt_hours(total)}</td>")
    return f'<tr class="total-row">{"".join(cells)}</tr>'


def _build_table(report: AttendanceReport, columns: list[tuple[str, str]]) -> str:
    ths  = "".join(f"<th>{_esc(label)}</th>" for label, _ in columns)
    head = f"<thead><tr>{ths}</tr></thead>"

    body_rows: list[str] = []
    for row in report.rows:
        tds = "".join(f"<td>{html_cell_value(row, key)}</td>" for _, key in columns)
        body_rows.append(f"<tr>{tds}</tr>")

    body_rows.append(_totals_row(report, columns))

    return (
        f'<div class="tbl-wrap">'
        f'<table>{head}<tbody>{"".join(body_rows)}</tbody></table>'
        f'</div>'
    )


def _build_page(
    report:  AttendanceReport,
    columns: list[tuple[str, str]],
    theme:   dict[str, str],
) -> str:
    generated_at = datetime.now().strftime("%d/%m/%Y %H:%M")
    s            = report.summary
    company      = _esc(s.company_name) if s.company_name else ""
    title        = f"דוח נוכחות – {report.report_type}"

    header = (
        f'<div class="rpt-header">'
        f'<div>'
        f'<h1>דוח נוכחות — {_esc(report.report_type)}</h1>'
        + (f'<div class="sub">{company}</div>' if company else "")
        + f'</div>'
        f'<div class="meta">שורות: {len(report.rows)}<br>{_esc(generated_at)}</div>'
        f'</div>'
    )

    if report.report_type == "TYPE_A":
        # TYPE_A: table first, summary footer below
        body = (
            _build_table(report, columns)
            + _build_summary_bar(report, ' style="border-top:none;border-radius:0 0 8px 8px;margin-top:8px"')
        )
    else:
        # TYPE_B: summary bar at top, then table
        body = _build_summary_bar(report) + _build_table(report, columns)

    return (
        f'<!DOCTYPE html><html lang="he" dir="rtl"><head>'
        f'<meta charset="UTF-8"/>'
        f'<meta name="viewport" content="width=device-width,initial-scale=1.0"/>'
        f"<title>{_esc(title)}</title>"
        f"{_build_css(theme)}</head><body>"
        f"{header}"
        f"{body}"
        f'<div class="footer">נוצר אוטומטית · {_esc(generated_at)}</div>'
        f"</body></html>"
    )


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

class HtmlRenderer(BaseRenderer):
    """Renders an AttendanceReport to a self-contained HTML file."""

    def __init__(
        self,
        column_map: dict[str, list[tuple[str, str]]] | None = None,
        themes:     dict[str, dict[str, str]]         | None = None,
    ) -> None:
        self._column_map = column_map if column_map is not None else _DEFAULT_COLUMN_MAP
        self._themes     = themes     if themes     is not None else _DEFAULT_THEMES

    def render(self, report: AttendanceReport, output_path: Path) -> Path:
        logger.info(
            "HtmlRenderer.render: starting  type=%s  rows=%d",
            report.report_type, len(report.rows),
        )

        columns = self._resolve_columns(report.report_type)
        theme   = self._themes.get(report.report_type, next(iter(self._themes.values())))

        self._ensure_output_dir(output_path)

        default_name = (
            f"attendance_{report.report_type.lower()}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        )
        dest = self._resolve_output_path(output_path, default_name)

        html = _build_page(report, columns, theme)

        try:
            dest.write_text(html, encoding="utf-8")
        except OSError as exc:
            logger.error("HtmlRenderer.render: write failed  path=%s  reason=%s", dest, exc)
            raise OutputDirectoryError(dest, str(exc)) from exc

        logger.info("HtmlRenderer.render: written → %s", dest)
        return dest

    def build_html(self, report: AttendanceReport) -> str:
        """Return the HTML string for *report* without writing to disk.
        Used by PdfRenderer to reuse the same HTML pipeline.
        """
        columns = self._resolve_columns(report.report_type)
        theme   = self._themes.get(report.report_type, next(iter(self._themes.values())))
        return _build_page(report, columns, theme)

    def _resolve_columns(self, report_type: str) -> list[tuple[str, str]]:
        columns = self._column_map.get(report_type)
        if columns is None:
            raise MissingRendererError(
                report_type=report_type,
                registered=list(self._column_map),
            )
        return columns


