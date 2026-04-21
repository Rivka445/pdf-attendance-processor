# ===== DI Container =====
# מאפשר החלפת כל רכיב (OCR, classifier, parser, renderer) בלי לשנות את ה-pipeline.
#
# שימוש:
#   container = Container()                          # ברירות מחדל
#   container.register_renderer("pdf", MyRenderer()) # החלפת renderer
#   run_pipeline("file.pdf", container=container)

from __future__ import annotations
from typing import Callable
from rendering.pdf_renderer import PdfRenderer
from rendering.excel_renderer import ExcelRenderer
from rendering.html_renderer import HtmlRenderer
from classification.classifier import classify_document
from parsing.parser_type_a import ParserA
from parsing.parser_type_b import ParserB
from rules.rules_type_a import generate_type_a
from rules.rules_type_b import generate_type_b
from ocr.extractor import extract_words, build_lines


class Container:
    """
    מחזיק את כל הרכיבים הניתנים להחלפה.
    כל רכיב ניתן לרישום מחדש דרך register_*.
    """

    def __init__(self):
        # OCR
        self.extract_words: Callable = extract_words
        self.build_lines:   Callable = build_lines

        # סיווג
        self.classify: Callable = classify_document

        # פרסורים
        self.parser_a = ParserA()
        self.parser_b = ParserB()

        # Rules
        self.generate_a: Callable = generate_type_a
        self.generate_b: Callable = generate_type_b

        # Renderers
        self._renderers: dict = {
            "pdf":   PdfRenderer(),
            "excel": ExcelRenderer(),
            "html":  HtmlRenderer(),
        }

    def get_renderer(self, fmt: str):
        return self._renderers.get(fmt)

    def register_renderer(self, fmt: str, renderer) -> None:
        """רישום renderer חדש לפורמט נתון."""
        self._renderers[fmt] = renderer

    def available_formats(self) -> list[str]:
        return list(self._renderers.keys())
