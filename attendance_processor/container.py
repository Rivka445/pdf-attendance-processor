"""
container.py
============
Pure-Python DI Container for the attendance-processor application.

AppConfig  — all tuneable settings in one immutable object.
AppContainer — creates every service exactly once and wires them together.

Usage::

    from attendance_processor.container import AppContainer, AppConfig

    container = AppContainer(AppConfig(
        tesseract_cmd=r"C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
    ))

    container.parser_factory.get_parser("TYPE_A")
    container.transformation_service.transform(report)
    container.renderers   # list[BaseRenderer]
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# AppConfig  — all tuneable knobs in one place
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AppConfig:
    # PDFExtractor
    tesseract_cmd:        Optional[str] = None
    dpi:                  int           = 300
    lang:                 str           = "heb+eng"
    ocr_oem:              int           = 3
    ocr_psm:              int           = 6

    # Classifier
    confidence_threshold: float         = 0.25

    # Output
    output_formats:       tuple[str, ...] = field(default=("html", "pdf"))


# ---------------------------------------------------------------------------
# AppContainer  — single source of truth for every service instance
# ---------------------------------------------------------------------------

class AppContainer:
    """
    Wires the entire application together.

    Every service is created once (lazy, on first access) and reused
    for the lifetime of the container.  All dependencies flow through
    the constructor — nothing is imported at module level inside services.

    Parameters
    ----------
    config:
        An :class:`AppConfig` instance.  Defaults to ``AppConfig()``
        (all defaults, no tesseract path override).
    """

    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or AppConfig()
        self._registry:               object | None = None
        self._extractor:              object | None = None
        self._classifier:             object | None = None
        self._parser_factory:         object | None = None
        self._transformation_service: object | None = None
        self._renderers:              list  | None = None

    # ── Config ───────────────────────────────────────────────────────────────

    @property
    def config(self) -> AppConfig:
        return self._config

    # ── Registry (shared across factory + service) ────────────────────────────

    @property
    def registry(self):
        if self._registry is None:
            from attendance_processor.registry import TypeRegistry
            self._registry = TypeRegistry.default()
        return self._registry

    # ── Ingestion ─────────────────────────────────────────────────────────────

    @property
    def extractor(self):
        if self._extractor is None:
            from attendance_processor.ingestion.pdf_extractor import (
                PDFExtractor,
                PDFExtractorConfig,
            )
            self._extractor = PDFExtractor(
                config=PDFExtractorConfig(
                    dpi=self._config.dpi,
                    lang=self._config.lang,
                    oem=self._config.ocr_oem,
                    psm=self._config.ocr_psm,
                    tesseract_cmd=self._config.tesseract_cmd,
                )
            )
        return self._extractor

    # ── Classification ────────────────────────────────────────────────────────

    @property
    def classifier(self):
        if self._classifier is None:
            from attendance_processor.classification.classifier import Classifier
            self._classifier = Classifier(
                confidence_threshold=self._config.confidence_threshold,
            )
        return self._classifier

    # ── Parsing ───────────────────────────────────────────────────────────────

    @property
    def parser_factory(self):
        if self._parser_factory is None:
            from attendance_processor.parsers.parser_factory import ParserFactory
            self._parser_factory = ParserFactory(registry=self.registry)
        return self._parser_factory

    # ── Transformation ────────────────────────────────────────────────────────

    @property
    def transformation_service(self):
        if self._transformation_service is None:
            from attendance_processor.transformation.service import TransformationService
            self._transformation_service = TransformationService(registry=self.registry)
        return self._transformation_service

    # ── Rendering ─────────────────────────────────────────────────────────────

    @property
    def renderers(self) -> list:
        if self._renderers is None:
            from attendance_processor.generation.html_renderer import HtmlRenderer

            _format_map = {
                "html":  HtmlRenderer
                }
            self._renderers = [
                _format_map[fmt]()
                for fmt in self._config.output_formats
                if fmt in _format_map
            ]
        return self._renderers
