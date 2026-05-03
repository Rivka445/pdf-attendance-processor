"""
conftest.py
===========
Shared pytest configuration for the entire test suite.

Adds ``attendance_processor/`` to ``sys.path`` so that intra-package imports
such as ``from domain.models import ...`` work inside every test module,
matching the import style used by the package itself.

Also provides a small collection of reusable fixtures (sample domain objects)
shared between unit and integration tests.
"""

import sys
from datetime import date, time
from pathlib import Path

import pytest

# ── path setup ───────────────────────────────────────────────────────────────
# attendance_processor/ uses implicit root-relative imports, e.g.
#   from domain.models import AttendanceRow
# Adding the package directory to sys.path mirrors that convention.
_PKG_ROOT = Path(__file__).parent.parent / "attendance_processor"
if str(_PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(_PKG_ROOT))

# ── shared fixtures ───────────────────────────────────────────────────────────

from domain.models import (  # noqa: E402 — must come after path insert
    AttendanceReport,
    AttendanceRow,
    BreakRecord,
    OvertimeBuckets,
    ReportSummary,
    TimeRange,
)


@pytest.fixture()
def simple_clock() -> TimeRange:
    """08:00 → 17:00 shift (9 h)."""
    return TimeRange(entry=time(8, 0), exit=time(17, 0))


@pytest.fixture()
def lunch_break() -> BreakRecord:
    """30-minute lunch break starting at 12:00."""
    return BreakRecord(
        clock=TimeRange(entry=time(12, 0), exit=time(12, 30)),
        duration_min=30,
    )


@pytest.fixture()
def sample_ot() -> OvertimeBuckets:
    return OvertimeBuckets(
        regular_ot=8.0,
        band_125=1.0,
        band_150=0.5,
        weekend_ot=0.0,

    )


@pytest.fixture()
def type_a_row(simple_clock, lunch_break, sample_ot) -> AttendanceRow:
    return AttendanceRow(
        row_date=date(2024, 1, 7),
        day_name="יום ראשון",
        clock=simple_clock,
        total_hours=8.5,
        location="מפעל",
        break_rec=lunch_break,
        overtime=sample_ot,
    )


@pytest.fixture()
def type_b_row(simple_clock) -> AttendanceRow:
    return AttendanceRow(
        row_date=date(2024, 1, 7),
        day_name="יום ראשון",
        clock=simple_clock,
        total_hours=9.0,
        notes="",
    )


@pytest.fixture()
def type_a_summary() -> ReportSummary:
    return ReportSummary(
        total_days=22,
        total_hours=187.0,
        ot_100=160.0,
        ot_125=16.0,
        ot_150=11.0,
        ot_shabbat=0.0,
        travel_allowance=350.0,
    )


@pytest.fixture()
def type_b_summary() -> ReportSummary:
    return ReportSummary(
        total_days=20,
        total_hours=180.0,
        hourly_rate=35.5,
        total_pay=6390.0,
    )


@pytest.fixture()
def type_a_report(type_a_row, type_a_summary) -> AttendanceReport:
    return AttendanceReport(
        report_type="TYPE_A",
        rows=(type_a_row,),
        summary=type_a_summary,
    )


@pytest.fixture()
def type_b_report(type_b_row, type_b_summary) -> AttendanceReport:
    return AttendanceReport(
        report_type="TYPE_B",
        rows=(type_b_row,),
        summary=type_b_summary,
    )
