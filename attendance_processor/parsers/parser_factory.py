"""
parsers/parser_factory.py
==========================
Factory that maps a ``report_type`` string to the correct concrete parser.

Accepts either a :class:`TypeRegistry` or a plain ``dict`` as the registry.

Usage::

    factory = ParserFactory()
    parser  = factory.get_parser("TYPE_A")

    # Custom dict registry:
    factory = ParserFactory(registry={"CUSTOM": my_parser})

    # Register at runtime:
    factory.register("TYPE_C", TypeCParser())
"""

from __future__ import annotations

import logging

from parsers.base_parser import BaseParser

logger = logging.getLogger(__name__)


class ParserFactory:
    """
    Maps ``report_type`` strings to concrete :class:`BaseParser` instances.

    Parameters
    ----------
    registry:
        A :class:`TypeRegistry` instance **or** a plain ``dict`` mapping
        report_type strings to parser instances.
        Defaults to ``TypeRegistry.default()``.
    """

    def __init__(self, registry=None) -> None:
        if registry is None:
            from attendance_processor.registry import TypeRegistry
            self._type_registry = TypeRegistry.default()
            self._dict_registry: dict | None = None
        elif isinstance(registry, dict):
            self._type_registry = None
            self._dict_registry = dict(registry)
        else:
            # TypeRegistry instance
            self._type_registry = registry
            self._dict_registry = None

        logger.debug(
            "ParserFactory initialised: registered_types=%s",
            self._known_types(),
        )

    def get_parser(self, report_type: str) -> BaseParser:
        """
        Return the parser for *report_type*.

        Raises:
            UnknownReportTypeError: If *report_type* is not in the registry.
        """
        if self._dict_registry is not None:
            parser = self._dict_registry.get(report_type)
            if parser is None:
                from domain.errors import UnknownReportTypeError
                raise UnknownReportTypeError(
                    report_type=report_type,
                    registry_keys=list(self._dict_registry),
                )
            return parser
        parser = self._type_registry.get_parser(report_type)
        logger.debug(
            "ParserFactory.get_parser: selected %s for type=%s",
            type(parser).__name__, report_type,
        )
        return parser

    def register(self, report_type: str, parser: BaseParser) -> None:
        """Add or replace a parser for *report_type*."""
        if self._dict_registry is not None:
            self._dict_registry[report_type] = parser
        else:
            # Wrap the TypeRegistry in a dict so we can mutate it
            known = self._known_types()
            d: dict = {}
            for t in known:
                d[t] = self._type_registry.get_parser(t)
            d[report_type] = parser
            self._dict_registry = d
            self._type_registry = None

    def _known_types(self) -> list[str]:
        if self._dict_registry is not None:
            return list(self._dict_registry)
        return self._type_registry.known_types()
