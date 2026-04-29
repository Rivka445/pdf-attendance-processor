"""
generation/pdf_renderer.py
===========================
Renders an AttendanceReport to a PDF file via WeasyPrint.

Strategy
--------
1. Delegate HTML generation to :class:`~generation.html_renderer.HtmlRenderer`.
2. Write the HTML to a temporary file.
3. Use WeasyPrint to convert the HTML to PDF.

WeasyPrint is imported **lazily** so the rest of the package stays usable
even when WeasyPrint is not installed.

Dependency injection
--------------------
An :class:`~generation.html_renderer.HtmlRenderer` instance can be injected
to share a customised column map / theme with the PDF renderer::

    html = HtmlRenderer(column_map=..., themes=...)
    pdf  = PdfRenderer(html_renderer=html)
"""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime
from pathlib import Path

from domain.models import AttendanceReport
from errors import OutputDirectoryError, RenderingError
from generation.base import BaseRenderer
from generation.html_renderer import HtmlRenderer

logger = logging.getLogger(__name__)


class PdfRenderer(BaseRenderer):
    """
    Renders an :class:`AttendanceReport` to a PDF file.

    Parameters
    ----------
    html_renderer:
        The :class:`HtmlRenderer` used for the intermediate HTML step.
        A default instance (no custom column maps / themes) is created when
        this argument is omitted.
    """

    def __init__(self, html_renderer: HtmlRenderer | None = None) -> None:
        self._html_renderer = html_renderer if html_renderer is not None else HtmlRenderer()
        logger.debug("PdfRenderer initialised  html_renderer=%r", self._html_renderer)

    def render(self, report: AttendanceReport, output_path: Path) -> Path:
        """
        Render *report* to a PDF file.

        The method writes a temporary HTML file, converts it to PDF using
        WeasyPrint, and cleans up the temp file afterwards.

        Raises:
            RenderingError: If WeasyPrint is not installed or PDF conversion fails.
            OutputDirectoryError: If the output directory is not writable.
        """
        logger.info(
            "PdfRenderer.render: starting  type=%s  rows=%d",
            report.report_type, len(report.rows),
        )

        # Lazy import — raises RenderingError if WeasyPrint is unavailable.
        try:
            from weasyprint import HTML as WeasyHTML  # type: ignore[import]
        except ImportError as exc:
            logger.error("PdfRenderer: WeasyPrint not installed  reason=%s", exc)
            raise RenderingError(
                "WeasyPrint is not installed. "
                "Install it with:  pip install weasyprint"
            ) from exc

        self._ensure_output_dir(output_path)

        default_name = (
            f"attendance_{report.report_type.lower()}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        )
        dest = self._resolve_output_path(output_path, default_name)

        # Step 1: render intermediate HTML to a temp file.
        with tempfile.NamedTemporaryFile(
            suffix=".html", delete=False, encoding="utf-8", mode="w"
        ) as tmp:
            tmp_path = Path(tmp.name)

        try:
            logger.debug("PdfRenderer: rendering intermediate HTML  tmp=%s", tmp_path)
            self._html_renderer.render(report, tmp_path)

            # Step 2: convert HTML → PDF.
            try:
                logger.debug("PdfRenderer: calling WeasyPrint  dest=%s", dest)
                WeasyHTML(filename=str(tmp_path)).write_pdf(str(dest))
            except Exception as exc:
                logger.error(
                    "PdfRenderer: WeasyPrint conversion failed  dest=%s  reason=%s",
                    dest, exc,
                )
                raise RenderingError(
                    f"WeasyPrint failed to convert HTML to PDF: {exc}"
                ) from exc
        finally:
            # Always remove the temp HTML file.
            tmp_path.unlink(missing_ok=True)
            logger.debug("PdfRenderer: temp file removed  tmp=%s", tmp_path)

        logger.info("PdfRenderer.render: written → %s", dest)
        return dest
