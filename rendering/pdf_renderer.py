# ===== PDF Renderer =====
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.enums import TA_RIGHT

from rendering.base_renderer import BaseRenderer
from models.type_a import TypeA
from models.type_b import TypeB
from templates import TEMPLATES
from row_extractor import get_cell_value
from rules.base_rules import minutes_to_str

_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"


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

HEADER_COLOR  = colors.HexColor("#2C3E50")
ALT_COLOR     = colors.HexColor("#F2F3F4")
SUMMARY_COLOR = colors.HexColor("#D5E8D4")
SHABAT_COLOR  = colors.HexColor("#A0A0A0")
GRID_COLOR    = colors.HexColor("#BDC3C7")


class PdfRenderer(BaseRenderer):

    def render(self, report, output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        doc_type = "A" if isinstance(report, TypeA) else "B"
        template = TEMPLATES[doc_type]
        title = "דוח נוכחות - סוג A" if doc_type == "A" else f"דוח נוכחות - סוג B | {report.month or ''}"

        # בניית שורות הטבלה
        header_row = [col.header for col in template]
        col_widths = [col.width_cm * cm for col in template]

        data = [header_row]
        shabat_rows = []

        for line in report.lines:
            is_shabat = getattr(line, "is_shabat", False)
            if is_shabat:
                shabat_rows.append(len(data))
                row = [get_cell_value(line, col.key) if col.key in ("date", "day") else "" for col in template]
            else:
                row = [get_cell_value(line, col.key) for col in template]
            data.append(row)

        # שורת סיכום
        summary = [self._summary_val(report, doc_type, col.key) for col in template]
        data.append(summary)

        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(self._build_style(len(data), shabat_rows))

        title_style = ParagraphStyle("t", fontName=_FONT_BOLD, fontSize=13, alignment=TA_RIGHT, spaceAfter=8)
        doc = SimpleDocTemplate(
            output_path, pagesize=landscape(A4),
            rightMargin=1*cm, leftMargin=1*cm,
            topMargin=1*cm, bottomMargin=1*cm,
        )
        doc.build([Paragraph(title, title_style), Spacer(1, 0.2*cm), table])
        return output_path

    def _summary_val(self, report, doc_type: str, key: str) -> str:
        if key == "date":
            return 'סה"כ'
        if key == "total":
            return minutes_to_str(report.total_hours)
        if key == "hours_100" and doc_type == "A":
            return minutes_to_str(report.hours_100)
        if key == "hours_125" and doc_type == "A":
            return minutes_to_str(report.hours_125)
        if key == "hours_150" and doc_type == "A":
            return minutes_to_str(report.hours_150)
        return ""

    def _build_style(self, num_rows: int, shabat_rows: list) -> TableStyle:
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
