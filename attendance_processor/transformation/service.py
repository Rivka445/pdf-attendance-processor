"""
transformation/service.py
==========================
TransformationService — the top-level entry point for row transformation.

Responsibilities
----------------
* Select the correct :class:`TransformationStrategy` for each report type.
* Iterate over all rows in an :class:`AttendanceReport`, delegating each row
  to the chosen strategy.
* Rebuild the :class:`ReportSummary` from the transformed rows.
* Return a *new* :class:`AttendanceReport` (original is never mutated).

Dependency injection
--------------------
Both the strategy mapping **and** the rules registry are injected via
constructor parameters so every dependency can be replaced in tests or
extended for new report types without modifying this file::

    service = TransformationService(
        strategies={
            "TYPE_A": TypeATransformationStrategy(),
            "TYPE_B": TypeBTransformationStrategy(),
        },
        rules_registry=RULES_REGISTRY,
    )
    result = service.transform(report)
"""

from __future__ import annotations

import logging
from typing import Optional

from config.rules import RULES_REGISTRY, ReportTransformationRules
from domain.models import (
    AttendanceReport,
    AttendanceRow,
    ReportSummary,
)
from errors import UnknownReportTypeError
from transformation.strategy import (
    TransformationStrategy,
    TypeATransformationStrategy,
    TypeBTransformationStrategy,
)

logger = logging.getLogger(__name__)

_DEFAULT_STRATEGIES: dict[str, TransformationStrategy] = {
    "TYPE_A": TypeATransformationStrategy(),
    "TYPE_B": TypeBTransformationStrategy(),
}


class TransformationService:
    """
    Applies report-type-aware jitter to every row in an
    :class:`AttendanceReport` and returns a recalculated replacement.

    Parameters
    ----------
    strategies:
        ``{report_type: strategy}`` mapping.  Defaults to
        ``TYPE_A → TypeATransformationStrategy`` and
        ``TYPE_B → TypeBTransformationStrategy``.
        Inject a custom dict to override or add new strategies.
    rules_registry:
        ``{report_type: ReportTransformationRules}`` mapping.
        Defaults to ``config.rules.RULES_REGISTRY``.
        Inject a custom dict for testing or to support extra types.
    """

    def __init__(
        self,
        strategies:      Optional[dict[str, TransformationStrategy]] = None,
        rules_registry:  Optional[dict[str, ReportTransformationRules]] = None,
    ) -> None:
        self._strategies:     dict[str, TransformationStrategy]      = (
            strategies     if strategies     is not None else _DEFAULT_STRATEGIES
        )
        self._rules_registry: dict[str, ReportTransformationRules] = (
            rules_registry if rules_registry is not None else RULES_REGISTRY
        )
        logger.debug(
            "TransformationService initialised: strategies=%s  rules=%s",
            list(self._strategies), list(self._rules_registry),
        )

    # ── Public API ───────────────────────────────────────────────────────────

    def transform(self, report: AttendanceReport) -> AttendanceReport:
        """
        Apply jitter to every row in *report* and return a new report.

        Args:
            report: The parsed :class:`AttendanceReport` to transform.

        Returns:
            A new :class:`AttendanceReport` with shifted times, recalculated
            ``total_hours``, and updated ``ReportSummary`` totals.

        Raises:
            UnknownReportTypeError: If ``report.report_type`` has no
                                    registered strategy or rules.
        """
        logger.info(
            "TransformationService.transform: starting  type=%s  rows=%d",
            report.report_type, len(report.rows),
        )

        rules    = self._get_rules(report.report_type)
        strategy = self._get_strategy(report.report_type)

        new_rows = tuple(
            strategy.transform_row(row, rules)
            for row in report.rows
        )

        new_summary = _rebuild_summary(report.summary, new_rows)

        logger.info(
            "TransformationService.transform: done  type=%s  rows=%d  total_h=%.2f",
            report.report_type, len(new_rows), new_summary.total_hours or 0,
        )

        return AttendanceReport(
            report_type=report.report_type,
            rows=new_rows,
            summary=new_summary,
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    def _get_rules(self, report_type: str) -> ReportTransformationRules:
        rules = self._rules_registry.get(report_type)
        if rules is None:
            logger.error(
                "TransformationService: no rules for type=%s  known=%s",
                report_type, list(self._rules_registry),
            )
            raise UnknownReportTypeError(
                report_type=report_type,
                registry_keys=list(self._rules_registry),
            )
        return rules

    def _get_strategy(self, report_type: str) -> TransformationStrategy:
        strategy = self._strategies.get(report_type)
        if strategy is None:
            logger.error(
                "TransformationService: no strategy for type=%s  known=%s",
                report_type, list(self._strategies),
            )
            raise UnknownReportTypeError(
                report_type=report_type,
                registry_keys=list(self._strategies),
            )
        return strategy


# ---------------------------------------------------------------------------
# Summary rebuilder (module-level pure function)
# ---------------------------------------------------------------------------

def _rebuild_summary(
    original: ReportSummary,
    rows: tuple[AttendanceRow, ...],
) -> ReportSummary:
    """
    Recompute ``total_days`` and ``total_hours`` from the transformed rows.

    Financial fields (``hourly_rate``, ``total_pay``, ``travel_allowance``)
    are preserved unchanged — they are document-level metadata, not derived
    from individual row times.

    OT band totals are summed from ``row.overtime`` where present.
    """
    new_total_hours = round(sum(r.total_hours for r in rows), 2)

    def _sum_ot(attr: str) -> Optional[float]:
        vals = [
            getattr(r.overtime, attr)
            for r in rows
            if r.overtime is not None
        ]
        if not vals:
            return None
        return round(sum(v for v in vals if v is not None), 2)

    return ReportSummary(
        total_days       = len(rows),
        total_hours      = new_total_hours,
        ot_100           = _sum_ot("regular_ot"),
        ot_125           = _sum_ot("band_125"),
        ot_150           = _sum_ot("band_150"),
        ot_shabbat       = _sum_ot("weekend_ot"),
        travel_allowance = original.travel_allowance,
        hourly_rate      = original.hourly_rate,
        total_pay        = original.total_pay,
    )
