"""
parsers/parser_factory.py
==========================
Factory that maps a ``report_type`` string to the correct concrete parser.
Delegates to :class:`TypeRegistry` as the single source of truth.

Usage::

    from parsers.parser_factory import ParserFactory

    factory = ParserFactory()
    parser  = factory.get_parser("TYPE_A")
    report  = parser.parse(normalized_text, source_file="report.pdf")

Custom registry::

    from attendance_processor.registry import TypeRegistry
    factory = ParserFactory(registry=TypeRegistry.default())
"""

from __future__ import annotations

import logging

from attendance_processor.registry import TypeRegistry
from parsers.base_parser import BaseParser

logger = logging.getLogger(__name__)


class ParserFactory:
    """
    Maps ``report_type`` strings to concrete :class:`BaseParser` instances.

    Parameters
    ----------
    registry:
        A :class:`TypeRegistry` instance.  Defaults to ``TypeRegistry.default()``.
        Inject a custom registry to replace or extend the available parsers.
    """

    def __init__(self, registry: TypeRegistry | None = None) -> None:
        self._registry = registry or TypeRegistry.default()
        logger.debug(
            "ParserFactory initialised: registered_types=%s",
            self._registry.known_types(),
        )

    def get_parser(self, report_type: str) -> BaseParser:
        """
        Return the parser for *report_type*.

        Raises:
            UnknownReportTypeError: If *report_type* is not in the registry.
        """
        parser = self._registry.get_parser(report_type)
        logger.debug(
            "ParserFactory.get_parser: selected %s for type=%s",
            type(parser).__name__, report_type,
        )
        return parser
