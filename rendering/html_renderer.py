# ===== HTML Renderer =====
import os
from rendering.base_renderer import BaseRenderer
from models.type_a import TypeA
from models.type_b import TypeB
from templates import TEMPLATES
from row_extractor import get_cell_value
from rules.base_rules import minutes_to_str

_CSS = """
<style>
  body { font-family: Arial, sans-serif; direction: rtl; padding: 20px; background: #f9f9f9; }
  h2 { color: #2C3E50; border-bottom: 2px solid #2C3E50; padding-bottom: 6px; }
  table { border-collapse: collapse; margin-top: 12px; background: white; }
  th { background: #2C3E50; color: white; padding: 8px 12px; text-align: center; font-size: 13px; white-space: nowrap; }
  td { padding: 6px 12px; text-align: center; font-size: 12px; border: 1px solid #BDC3C7; white-space: nowrap; }
  tr:nth-child(even) td { background: #F2F3F4; }
  tr.shabat td { background: #A0A0A0; color: #333; font-style: italic; }
  tr.summary td { background: #D5E8D4; font-weight: bold; border-top: 2px solid #2C3E50; }
</style>
"""


class HtmlRenderer(BaseRenderer):

    def render(self, report, output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        doc_type = "A" if isinstance(report, TypeA) else "B"
        template = TEMPLATES[doc_type]
        title = "דוח נוכחות - סוג A" if doc_type == "A" else f"דוח נוכחות - סוג B | {report.month or ''}"

        # כותרות
        th = "".join(f"<th>{col.header}</th>" for col in template)

        # שורות נתונים
        body = ""
        for line in report.lines:
            is_shabat = getattr(line, "is_shabat", False)
            css = ' class="shabat"' if is_shabat else ""
            tds = "".join(
                f"<td>{get_cell_value(line, col.key) if not is_shabat or col.key in ('date','day') else ''}</td>"
                for col in template
            )
            body += f"<tr{css}>{tds}</tr>"

        # שורת סיכום
        summary_vals = self._summary_row(report, doc_type, template)
        sum_tds = "".join(f"<td>{v}</td>" for v in summary_vals)
        body += f'<tr class="summary">{sum_tds}</tr>'

        table = f"<table><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"
        html = f"<!DOCTYPE html><html><head><meta charset='utf-8'>{_CSS}</head><body><h2>{title}</h2>{table}</body></html>"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return output_path

    def _summary_row(self, report, doc_type: str, template) -> list:
        row = []
        for col in template:
            if col.key == "date":
                row.append('סה"כ')
            elif col.key == "total":
                row.append(minutes_to_str(report.total_hours))
            elif col.key == "hours_100" and doc_type == "A":
                row.append(minutes_to_str(report.hours_100))
            elif col.key == "hours_125" and doc_type == "A":
                row.append(minutes_to_str(report.hours_125))
            elif col.key == "hours_150" and doc_type == "A":
                row.append(minutes_to_str(report.hours_150))
            else:
                row.append("")
        return row
