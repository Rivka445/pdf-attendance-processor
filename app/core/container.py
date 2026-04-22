from __future__ import annotations
from typing import Callable
from dataclasses import dataclass

from app.core.protocols import ParserProtocol, RulesProtocol, RendererProtocol
from app.processing.rendering.pdf_renderer import PdfRenderer
from app.processing.rendering.excel_renderer import ExcelRenderer
from app.processing.rendering.html_renderer import HtmlRenderer
from app.processing.classification.classifier import classify_document
from app.processing.parsing.parser_type_a import ParserA
from app.processing.parsing.parser_type_b import ParserB
from app.processing.rules.rules_type_a import RulesA
from app.processing.rules.rules_type_b import RulesB
from app.ocr.extractor import extract_words, build_lines


@dataclass
class DocTypeHandler:
    """Holds the parser, rules, and input-preparation function for one document type."""
    parser: ParserProtocol
    rules:  RulesProtocol
    prepare_input: Callable


class Container:
    """Dependency-injection container. Maps document types and output formats to handlers."""

    def __init__(self):
        self.extract_words: Callable = extract_words
        self.build_lines:   Callable = build_lines
        self.classify:      Callable = classify_document

        self._handlers: dict[str, DocTypeHandler] = {
            "A": DocTypeHandler(
                parser=ParserA(),
                rules=RulesA(),
                prepare_input=lambda words, c: "\n".join(c.build_lines(words)),
            ),
            "B": DocTypeHandler(
                parser=ParserB(),
                rules=RulesB(),
                prepare_input=lambda words, c: words,
            ),
        }

        self._renderers: dict[str, RendererProtocol] = {
            "pdf":   PdfRenderer(),
            "excel": ExcelRenderer(),
            "html":  HtmlRenderer(),
        }

    def get_handler(self, doc_type: str) -> DocTypeHandler | None:
        """Return the handler registered for the given document type, or None."""
        return self._handlers.get(doc_type)

    def register_type(self, doc_type: str, parser: ParserProtocol,
                      rules: RulesProtocol, prepare_input: Callable = None) -> None:
        """Register a new document type with its parser and rules."""
        if prepare_input is None:
            prepare_input = lambda words, c: words
        self._handlers[doc_type] = DocTypeHandler(parser, rules, prepare_input)

    def get_renderer(self, fmt: str) -> RendererProtocol | None:
        """Return the renderer registered for the given format, or None."""
        return self._renderers.get(fmt)

    def register_renderer(self, fmt: str, renderer: RendererProtocol) -> None:
        """Register a new output renderer for the given format key."""
        self._renderers[fmt] = renderer

    def supported_types(self) -> list[str]:
        """Return all registered document type keys."""
        return list(self._handlers.keys())

    def available_formats(self) -> list[str]:
        """Return all registered output format keys."""
        return list(self._renderers.keys())
