"""
transformation/service.py
==========================
TransformationService — applies row-level jitter and rebuilds the summary.
"""

from __future__ import annotations

import logging
from typing import Optional

from attendance_processor.registry import TypeRegistry
from domain.models import AttendanceReport, AttendanceRow, ReportSummary

logger = logging.getLogger(__name__)


class TransformationService:
    """
    Applies report-type-aware jitter to every row and returns a new report.

    Inject a custom TypeRegistry for testing or to support extra types.
    """

    def __init__(self, registry: TypeRegistry | None = None) -> None:
        self._registry = registry or TypeRegistry.default()

    def transform(self, report: AttendanceReport) -> AttendanceReport:
        logger.debug("TransformationService.transform: starting  type=%s  rows=%d",
                    report.report_type, len(report.rows))

        rules    = self._registry.get_rules(report.report_type)
        strategy = self._registry.get_strategy(report.report_type)
        new_rows = tuple(strategy.transform_row(row, rules) for row in report.rows)
        new_summary = _rebuild_summary(report.summary, new_rows)

        logger.debug("TransformationService.transform: done  type=%s  rows=%d  total_h=%.2f",
                    report.report_type, len(new_rows), new_summary.total_hours or 0)

        return AttendanceReport(
            report_type=report.report_type,
            rows=new_rows,
            summary=new_summary,
        )


def _rebuild_summary(
    original: ReportSummary,
    rows: tuple[AttendanceRow, ...],
) -> ReportSummary:
    """Recompute totals from transformed rows; preserve financial fields."""

    def _sum_ot(attr: str) -> Optional[float]:
        vals = [getattr(r.overtime, attr) for r in rows if r.overtime is not None]
        return round(sum(v for v in vals if v is not None), 2) if vals else None

    return ReportSummary(
        total_days       = len(rows),
        total_hours      = round(sum(r.total_hours for r in rows), 2),
        ot_100           = _sum_ot("regular_ot"),
        ot_125           = _sum_ot("band_125"),
        ot_150           = _sum_ot("band_150"),
        ot_shabbat       = _sum_ot("weekend_ot"),
        travel_allowance = original.travel_allowance,
        hourly_rate      = original.hourly_rate,
        total_pay        = original.total_pay,
    )
