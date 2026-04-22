import os
import re
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_RIGHT

from app.processing.rendering.base_renderer import BaseRenderer
from app.templates import TEMPLATES
from app.row_extractor import get_cell_value
from app.processing.rules.base_rules import minutes_to_str

_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_HEB_RE = re.compile(r'[\u0590-\u05FF]')


def _try_register_hebrew_font():
    global _FONT, _FONT_BOLD
    for path in [r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\ARIAL.TTF"]:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont("Arial", path))
                _FONT = _FONT_BOLD = "Arial"
                return
            except Exception:
                pass


_try_register_hebrew_font()


def _h(text: str) -> str:
    if not text or not _HEB_RE.search(text):
        return text
    return get_display(text)


HEADER_COLOR  = colors.HexColor("#2C3E50")
ALT_COLOR     = colors.HexColor("#F2F3F4")
SUMMARY_COLOR = colors.HexColor("#D5E8D4")
SHABAT_COLOR  = colors.HexColor("#A0A0A0")
INFO_COLOR    = colors.HexColor("#EBF5FB")
GRID_COLOR    = colors.HexColor("#BDC3C7")


class PdfRenderer(BaseRenderer):

    def render(self, report, output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        doc_type = report.doc_type
        template = TEMPLATES[doc_type]
        title = "דוח נוכחות - סוג A" if doc_type == "A" else f"דוח נוכחות - סוג B | {report.month or ''}"

        title_style = ParagraphStyle("t", fontName=_FONT_BOLD, fontSize=13, alignment=TA_RIGHT, spaceAfter=8)
        elements = [Paragraph(_h(title), title_style), Spacer(1, 0.2*cm)]

        info_table = self._build_info_table(report, doc_type)
        main_table = self._build_main_table(report, doc_type, template)

        if doc_type == "B":
            elements += [info_table, Spacer(1, 0.4*cm), main_table]
        else:
            elements += [main_table, Spacer(1, 0.4*cm), info_table]

        doc = SimpleDocTemplate(
            output_path, pagesize=landscape(A4),
            rightMargin=1*cm, leftMargin=1*cm,
            topMargin=1*cm, bottomMargin=1*cm,
        )
        doc.build(elements)
        return output_path

    def _build_main_table(self, report, doc_type, template):
        rtl = list(reversed(template))
        header_row = [_h(col.header) for col in rtl]
        col_widths = [col.width_cm * cm for col in rtl]
        data = [header_row]
        shabat_rows = []

        for line in report.lines:
            is_shabat = getattr(line, "is_shabat", False)
            if is_shabat:
                shabat_rows.append(len(data))
                row = [_h(get_cell_value(line, col.key)) if col.key in ("date", "day") else "" for col in rtl]
            else:
                row = [_h(get_cell_value(line, col.key)) for col in rtl]
            data.append(row)

        data.append([_h(self._summary_val(report, doc_type, col.key)) for col in rtl])
        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(self._main_style(shabat_rows))
        return table

    def _build_info_table(self, report, doc_type: str):
        if doc_type == "A":
            rows = [
                ("ימים:", report.days),
                ('סה"כ שעות:', minutes_to_str(report.total_hours)),
                ("100% שעות:", minutes_to_str(report.hours_100)),
                ("125% שעות:", minutes_to_str(report.hours_125)),
                ("150% שעות:", minutes_to_str(report.hours_150)),
                ("שבת 150%:", minutes_to_str(report.shabat_total)),
                ("בונוס:", f"{report.bonus:.2f}"),
                ("נסיעות:", f"{report.nesiot:.2f}"),
            ]
        else:
            rows = [
                ("שם העובד:", report.worker_name or ""),
                ('סה"כ ימי עבודה:', report.days),
                ('סה"כ שעות חודשיות:', minutes_to_str(report.total_hours)),
                ("מחיר לשעה:", f"{report.price_per_hour:.2f}"),
                ('סה"כ לתשלום:', f"{report.total_payment:.2f}"),
                ("כרטיס עובד לחודש:", report.month or ""),
            ]
        data = [[str(val), _h(label)] for label, val in rows]
        table = Table(data, colWidths=[3*cm, 5*cm])
        table.setStyle(TableStyle([
            ("FONTNAME",      (0, 0), (-1, -1), _FONT),
            ("FONTNAME",      (1, 0), (1, -1),  _FONT_BOLD),
            ("FONTSIZE",      (0, 0), (-1, -1), 9),
            ("ALIGN",         (0, 0), (0, -1),  "CENTER"),
            ("ALIGN",         (1, 0), (1, -1),  "RIGHT"),
            ("BACKGROUND",    (0, 0), (-1, -1), INFO_COLOR),
            ("GRID",          (0, 0), (-1, -1), 0.5, GRID_COLOR),
            ("TOPPADDING",    (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return table

    def _summary_val(self, report, doc_type: str, key: str) -> str:
        if key == "date":       return 'סה"כ'
        if key == "total":      return minutes_to_str(report.total_hours)
        if key == "hours_100" and doc_type == "A": return minutes_to_str(report.hours_100)
        if key == "hours_125" and doc_type == "A": return minutes_to_str(report.hours_125)
        if key == "hours_150" and doc_type == "A": return minutes_to_str(report.hours_150)
        return ""

    def _main_style(self, shabat_rows: list) -> TableStyle:
        cmds = [
            ("BACKGROUND",    (0, 0), (-1, 0),  HEADER_COLOR),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, -1), _FONT),
            ("FONTNAME",      (0, 0), (-1, 0),  _FONT_BOLD),
            ("FONTNAME",      (0, -1),(-1, -1), _FONT_BOLD),
            ("FONTSIZE",      (0, 0), (-1, -1), 8),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("ROWBACKGROUNDS",(0, 1), (-1, -2), [colors.white, ALT_COLOR]),
            ("BACKGROUND",    (0, -1),(-1, -1), SUMMARY_COLOR),
            ("GRID",          (0, 0), (-1, -1), 0.5, GRID_COLOR),
            ("BOX",           (0, 0), (-1, -1), 1,   HEADER_COLOR),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        for r in shabat_rows:
            cmds += [
                ("BACKGROUND", (0, r), (-1, r), SHABAT_COLOR),
                ("TEXTCOLOR",  (0, r), (-1, r), colors.HexColor("#333333")),
            ]
        return TableStyle(cmds)
