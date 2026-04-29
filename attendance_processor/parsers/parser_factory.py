"""
parsers/parser_factory.py
==========================
Factory that maps a ``report_type`` string to the correct concrete parser.

Dependency injection
--------------------
The default registry wires ``"TYPE_A"`` → :class:`TypeAParser` and
``"TYPE_B"`` → :class:`TypeBParser`.  Pass a custom ``registry`` dict to
``ParserFactory.__init__`` to override or extend that mapping without
touching this file — useful for testing or adding new document types::

    factory = ParserFactory(registry={"TYPE_X": MyXParser()})
    parser  = factory.get_parser("TYPE_X")
    report  = parser.parse(text)

Usage::

    from parsers.parser_factory import ParserFactory
    from classification.classifier import Classifier

    classifier = Classifier()
    result     = classifier.classify(normalized_text)

    factory = ParserFactory()
    parser  = factory.get_parser(result.report_type)
    report  = parser.parse(normalized_text, source_file="report.pdf")
"""

from __future__ import annotations

import logging

from errors import UnknownReportTypeError
from parsers.base_parser import BaseParser
from parsers.type_a_parser import TypeAParser
from parsers.type_b_parser import TypeBParser

logger = logging.getLogger(__name__)

# Default singleton instances — constructed once, reused for every file in a batch.
_DEFAULT_REGISTRY: dict[str, BaseParser] = {
    "TYPE_A": TypeAParser(),
    "TYPE_B": TypeBParser(),
}


class ParserFactory:
    """
    Maps ``report_type`` strings to concrete :class:`BaseParser` instances.

    Parameters
    ----------
    registry:
        ``{report_type: parser_instance}`` mapping.  Defaults to the
        module-level ``_DEFAULT_REGISTRY``.  Inject a custom dict to
        replace or extend the available parsers.
    """

    def __init__(
        self,
        registry: dict[str, BaseParser] | None = None,
    ) -> None:
        self._registry: dict[str, BaseParser] = (
            registry if registry is not None else _DEFAULT_REGISTRY
        )
        logger.debug(
            "ParserFactory initialised: registered_types=%s",
            list(self._registry),
        )

    def get_parser(self, report_type: str) -> BaseParser:
        """
        Return the parser for *report_type*.

        Raises:
            UnknownReportTypeError: If *report_type* is not in the registry.
        """
        parser = self._registry.get(report_type)
        if parser is None:
            logger.error(
                "ParserFactory.get_parser: no parser for type=%s  known=%s",
                report_type, list(self._registry),
            )
            raise UnknownReportTypeError(
                report_type=report_type,
                registry_keys=list(self._registry),
            )
        logger.debug("ParserFactory.get_parser: selected %s for type=%s", type(parser).__name__, report_type)
        return parser

    def register(self, report_type: str, parser: BaseParser) -> None:
        """
        Register a custom parser at runtime.

        Allows extending the system with new document types without
        subclassing or modifying this file.
        """
        logger.info("ParserFactory.register: type=%s  parser=%s", report_type, type(parser).__name__)
        self._registry[report_type] = parser
