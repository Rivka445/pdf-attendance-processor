"""
generation/pdf_renderer.py
===========================
Renders an AttendanceReport to a PDF file.

Reuses HtmlRenderer to build the HTML string, then converts it to PDF
using weasyprint — so the PDF is pixel-identical to the HTML output.

Usage::

    from generation.pdf_renderer import PdfRenderer
    renderer = PdfRenderer()
    path = renderer.render(report, output_dir)
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from domain.models import AttendanceReport
from domain.errors import RenderingError
from generation.base import BaseRenderer
from generation.html_renderer import HtmlRenderer

logger = logging.getLogger(__name__)


class PdfRenderer(BaseRenderer):
    """
    Renders an AttendanceReport to a PDF file.

    Delegates HTML generation to :class:`HtmlRenderer` and converts
    the result to PDF via weasyprint.

    Parameters
    ----------
    html_renderer:
        Optional :class:`HtmlRenderer` instance.  Defaults to a new
        ``HtmlRenderer()`` with default column map and themes.
        Inject a custom renderer to override columns or colours.
    """

    def __init__(self, html_renderer: HtmlRenderer | None = None) -> None:
        self._html_renderer = html_renderer or HtmlRenderer()

    def render(self, report: AttendanceReport, output_path: Path) -> Path:
        try:
            from weasyprint import HTML
        except ImportError as exc:
            raise RenderingError("weasyprint is required for PDF rendering") from exc

        logger.info(
            "PdfRenderer.render: starting  type=%s  rows=%d",
            report.report_type, len(report.rows),
        )

        self._ensure_output_dir(output_path)

        default_name = (
            f"attendance_{report.report_type.lower()}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        )
        dest = self._resolve_output_path(output_path, default_name)

        # Build HTML via the injected renderer
        import tempfile, os
        tmp_html = Path(tempfile.mktemp(suffix=".html"))
        try:
            html_path = self._html_renderer.render(report, tmp_html)
            html_string = html_path.read_text(encoding="utf-8")
        finally:
            if tmp_html.exists():
                tmp_html.unlink(missing_ok=True)

        try:
            HTML(string=html_string).write_pdf(str(dest))
        except Exception as exc:
            logger.error("PdfRenderer.render: write failed  path=%s  reason=%s", dest, exc)
            raise RenderingError(f"PDF generation failed: {exc}") from exc

        logger.info("PdfRenderer.render: written → %s", dest)
        return dest
