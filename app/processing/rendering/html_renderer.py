import os
from app.processing.rendering.base_renderer import BaseRenderer
from app.templates import TEMPLATES
from app.row_extractor import get_cell_value
from app.processing.rules.base_rules import minutes_to_str

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
  .info-block { margin-top: 16px; background: white; border: 1px solid #BDC3C7; padding: 12px 16px; display: inline-block; }
  .info-block table { margin-top: 0; }
  .info-block td { border: none; text-align: right; padding: 3px 10px; font-size: 12px; }
  .info-block td:first-child { font-weight: bold; color: #2C3E50; }
</style>
"""


class HtmlRenderer(BaseRenderer):

    def render(self, report, output_path: str) -> str:
        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        doc_type = report.doc_type
        template = TEMPLATES[doc_type]
        title = "דוח נוכחות - סוג A" if doc_type == "A" else f"דוח נוכחות - סוג B | {report.month or ''}"

        th = "".join(f"<th>{col.header}</th>" for col in template)
        rows = []
        for line in report.lines:
            is_shabat = getattr(line, "is_shabat", False)
            css = ' class="shabat"' if is_shabat else ""
            tds = "".join(
                f"<td>{get_cell_value(line, col.key) if not is_shabat or col.key in ('date', 'day') else ''}</td>"
                for col in template
            )
            rows.append(f"<tr{css}>{tds}</tr>")

        sum_tds = "".join(f"<td>{v}</td>" for v in self._summary_row(report, doc_type, template))
        rows.append(f'<tr class="summary">{sum_tds}</tr>')

        table = f"<table><thead><tr>{th}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
        info = self._info_block(report, doc_type)

        content = f"{info}{table}" if doc_type == "B" else f"{table}{info}"
        html = f"<!DOCTYPE html><html><head><meta charset='utf-8'>{_CSS}</head><body><h2>{title}</h2>{content}</body></html>"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)
        return output_path

    def _info_block(self, report, doc_type: str) -> str:
        if doc_type == "A":
            rows = [
                ("ימים", report.days),
                ('סה"כ שעות', minutes_to_str(report.total_hours)),
                ("100% שעות", minutes_to_str(report.hours_100)),
                ("125% שעות", minutes_to_str(report.hours_125)),
                ("150% שעות", minutes_to_str(report.hours_150)),
                ("שבת 150%", minutes_to_str(report.shabat_total)),
                ("בונוס", f"{report.bonus:.2f}"),
                ("נסיעות", f"{report.nesiot:.2f}"),
            ]
        else:
            rows = [
                ("שם העובד", report.worker_name or ""),
                ('סה"כ ימי עבודה לחודש', report.days),
                ('סה"כ שעות חודשיות', minutes_to_str(report.total_hours)),
                ("מחיר לשעה", f"{report.price_per_hour:.2f}"),
                ('סה"כ לתשלום', f"{report.total_payment:.2f}"),
                ("כרטיס עובד לחודש", report.month or ""),
            ]
        trs = "".join(f"<tr><td>{k}:</td><td>{v}</td></tr>" for k, v in rows)
        return f'<div class="info-block"><table>{trs}</table></div>'

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
