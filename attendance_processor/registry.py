"""
registry.py
===========
Central TypeRegistry — single source of truth for every report type.

Instead of maintaining three separate dicts across ParserFactory,
TransformationService and config/rules.py, all per-type components are
registered once here:

    registry = TypeRegistry.default()
    registry.get_parser("TYPE_A")
    registry.get_strategy("TYPE_B")
    registry.get_rules("TYPE_A")

Adding a new report type requires a single call to ``register()``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from attendance_processor.config.rules import ReportTransformationRules
    from attendance_processor.parsers.base_parser import BaseParser
    from attendance_processor.transformation.strategy import TransformationStrategy


@dataclass
class _TypeEntry:
    parser:   "BaseParser"
    strategy: "TransformationStrategy"
    rules:    "ReportTransformationRules"


class TypeRegistry:
    """
    Maps report_type strings to their parser, strategy and rules.

    Usage::

        registry = TypeRegistry.default()
        parser   = registry.get_parser("TYPE_A")
        strategy = registry.get_strategy("TYPE_A")
        rules    = registry.get_rules("TYPE_A")

    Extend at runtime::

        registry.register("TYPE_C",
            parser=TypeCParser(),
            strategy=TypeCStrategy(),
            rules=TYPE_C_RULES,
        )
    """

    def __init__(self) -> None:
        self._entries: dict[str, _TypeEntry] = {}

    # ── Registration ─────────────────────────────────────────────────────────

    def register(
        self,
        report_type: str,
        parser:      "BaseParser",
        strategy:    "TransformationStrategy",
        rules:       "ReportTransformationRules",
    ) -> None:
        """Register all components for *report_type* in one call."""
        self._entries[report_type] = _TypeEntry(
            parser=parser,
            strategy=strategy,
            rules=rules,
        )

    # ── Accessors ─────────────────────────────────────────────────────────────

    def get_parser(self, report_type: str) -> "BaseParser":
        return self._get(report_type).parser

    def get_strategy(self, report_type: str) -> "TransformationStrategy":
        return self._get(report_type).strategy

    def get_rules(self, report_type: str) -> "ReportTransformationRules":
        return self._get(report_type).rules

    def known_types(self) -> list[str]:
        return list(self._entries)

    # ── Default factory ───────────────────────────────────────────────────────

    @classmethod
    def default(cls) -> "TypeRegistry":
        """Build the registry with the built-in TYPE_A and TYPE_B entries."""
        from config.rules import TYPE_A_RULES, TYPE_B_RULES
        from parsers.type_a_parser import TypeAParser
        from parsers.type_b_parser import TypeBParser
        from transformation.strategy import (
            TypeATransformationStrategy,
            TypeBTransformationStrategy,
        )

        registry = cls()
        registry.register(
            "TYPE_A",
            parser=TypeAParser(),
            strategy=TypeATransformationStrategy(),
            rules=TYPE_A_RULES,
        )
        registry.register(
            "TYPE_B",
            parser=TypeBParser(),
            strategy=TypeBTransformationStrategy(),
            rules=TYPE_B_RULES,
        )
        return registry

    # ── Private ───────────────────────────────────────────────────────────────

    def _get(self, report_type: str) -> _TypeEntry:
        entry = self._entries.get(report_type)
        if entry is None:
            from domain.errors import UnknownReportTypeError
            raise UnknownReportTypeError(
                report_type=report_type,
                registry_keys=self.known_types(),
            )
        return entry
