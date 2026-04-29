"""
tests/unit/test_models.py
==========================
Unit tests for domain/models.py.

Covers:
  - TimeRange: valid construction, exit-after-entry validation,
    duration_minutes, duration_hours.
  - BreakRecord: valid construction, duration mismatch validation (>1 min).
  - OvertimeBuckets: valid construction, total mismatch validation.
  - AttendanceRow: valid construction, net_hours property.
  - ReportSummary: optional fields, defaults to None.
  - AttendanceReport: empty rows rejected, total_hours fallback.
"""

from datetime import date, time

import pytest

from domain.models import (
    AttendanceReport,
    AttendanceRow,
    BreakRecord,
    BreakType,
    OvertimeBuckets,
    ReportSummary,
    TimeRange,
)


# ---------------------------------------------------------------------------
# TimeRange
# ---------------------------------------------------------------------------

class TestTimeRange:
    def test_valid(self):
        tr = TimeRange(entry=time(8, 0), exit=time(17, 0))
        assert tr.entry == time(8, 0)
        assert tr.exit  == time(17, 0)

    def test_exit_equal_entry_raises(self):
        with pytest.raises(Exception):
            TimeRange(entry=time(8, 0), exit=time(8, 0))

    def test_exit_before_entry_raises(self):
        with pytest.raises(Exception):
            TimeRange(entry=time(17, 0), exit=time(8, 0))

    def test_duration_minutes(self):
        tr = TimeRange(entry=time(8, 0), exit=time(9, 30))
        assert tr.duration_minutes == 90

    def test_duration_hours(self):
        tr = TimeRange(entry=time(8, 0), exit=time(10, 0))
        assert tr.duration_hours == 2.0

    def test_duration_hours_fractional(self):
        tr = TimeRange(entry=time(8, 0), exit=time(8, 30))
        assert tr.duration_hours == 0.5

    def test_frozen(self):
        tr = TimeRange(entry=time(8, 0), exit=time(17, 0))
        with pytest.raises(Exception):
            tr.entry = time(9, 0)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BreakRecord
# ---------------------------------------------------------------------------

class TestBreakRecord:
    def test_valid(self):
        br = BreakRecord(
            break_type=BreakType.LUNCH,
            clock=TimeRange(entry=time(12, 0), exit=time(12, 30)),
            duration_min=30,
        )
        assert br.duration_min == 30

    def test_duration_mismatch_within_tolerance(self):
        # 1-minute tolerance is allowed
        BreakRecord(
            break_type=BreakType.SHORT,
            clock=TimeRange(entry=time(12, 0), exit=time(12, 30)),
            duration_min=29,
        )

    def test_duration_mismatch_outside_tolerance_raises(self):
        with pytest.raises(Exception):
            BreakRecord(
                break_type=BreakType.SHORT,
                clock=TimeRange(entry=time(12, 0), exit=time(12, 30)),
                duration_min=15,  # differs by 15 min — well outside tolerance
            )

    def test_default_break_type(self):
        br = BreakRecord(
            clock=TimeRange(entry=time(12, 0), exit=time(12, 20)),
            duration_min=20,
        )
        assert br.break_type == BreakType.OTHER


# ---------------------------------------------------------------------------
# OvertimeBuckets
# ---------------------------------------------------------------------------

class TestOvertimeBuckets:
    def test_valid_zero(self):
        ot = OvertimeBuckets()
        assert ot.total_ot == 0.0

    def test_valid_with_values(self):
        ot = OvertimeBuckets(
            regular_ot=8.0,
            band_125=1.0,
            band_150=0.5,
            weekend_ot=0.0,
            total_ot=9.5,
        )
        assert ot.total_ot == 9.5

    def test_total_mismatch_large_raises(self):
        with pytest.raises(Exception):
            OvertimeBuckets(
                regular_ot=8.0,
                band_125=1.0,
                band_150=0.0,
                weekend_ot=0.0,
                total_ot=5.0,  # wrong — sum is 9.0
            )

    def test_total_zero_skips_validation(self):
        # total_ot=0 bypasses the sum check (partial data allowed)
        OvertimeBuckets(regular_ot=0.0, band_125=0.0, band_150=0.0, weekend_ot=0.0, total_ot=0.0)

    def test_negative_band_raises(self):
        with pytest.raises(Exception):
            OvertimeBuckets(regular_ot=-1.0)


# ---------------------------------------------------------------------------
# AttendanceRow
# ---------------------------------------------------------------------------

class TestAttendanceRow:
    def _make_row(self, break_rec=None, overtime=None):
        return AttendanceRow(
            row_date=date(2024, 1, 7),
            day_name="יום ראשון",
            clock=TimeRange(entry=time(8, 0), exit=time(17, 0)),
            total_hours=8.5,
            break_rec=break_rec,
            overtime=overtime,
        )

    def test_basic_construction(self):
        row = self._make_row()
        assert row.row_date == date(2024, 1, 7)
        assert row.total_hours == 8.5

    def test_net_hours_no_break(self):
        row = self._make_row()
        # clock = 9 h, no break → net = 9.0
        assert row.net_hours == pytest.approx(9.0, abs=0.01)

    def test_net_hours_with_break(self):
        brk = BreakRecord(
            break_type=BreakType.LUNCH,
            clock=TimeRange(entry=time(12, 0), exit=time(12, 30)),
            duration_min=30,
        )
        row = self._make_row(break_rec=brk)
        # 9 h clock − 30 min break = 8.5 h
        assert row.net_hours == pytest.approx(8.5, abs=0.01)

    def test_optional_type_a_fields_default_none(self):
        row = self._make_row()
        assert row.location is None
        assert row.break_rec is None
        assert row.overtime is None
        assert row.notes is None

    def test_frozen(self):
        row = self._make_row()
        with pytest.raises(Exception):
            row.total_hours = 99.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ReportSummary
# ---------------------------------------------------------------------------

class TestReportSummary:
    def test_all_none_by_default(self):
        s = ReportSummary()
        assert s.total_days is None
        assert s.total_hours is None
        assert s.ot_100 is None
        assert s.hourly_rate is None

    def test_type_a_fields(self):
        s = ReportSummary(
            total_days=22,
            total_hours=187.0,
            ot_100=160.0,
            ot_125=16.0,
            ot_150=11.0,
            ot_shabbat=0.0,
            travel_allowance=350.0,
        )
        assert s.total_days == 22
        assert s.travel_allowance == 350.0

    def test_negative_days_raises(self):
        with pytest.raises(Exception):
            ReportSummary(total_days=-1)


# ---------------------------------------------------------------------------
# AttendanceReport
# ---------------------------------------------------------------------------

class TestAttendanceReport:
    def _make_row(self):
        return AttendanceRow(
            row_date=date(2024, 1, 7),
            day_name="יום ראשון",
            clock=TimeRange(entry=time(8, 0), exit=time(17, 0)),
            total_hours=9.0,
        )

    def test_valid_construction(self):
        report = AttendanceReport(
            report_type="TYPE_B",
            rows=(self._make_row(),),
            summary=ReportSummary(total_hours=9.0),
        )
        assert report.report_type == "TYPE_B"
        assert len(report.rows) == 1

    def test_empty_rows_raises(self):
        with pytest.raises(ValueError):
            AttendanceReport(
                report_type="TYPE_B",
                rows=(),
                summary=ReportSummary(),
            )

    def test_total_hours_from_summary(self):
        report = AttendanceReport(
            report_type="TYPE_B",
            rows=(self._make_row(),),
            summary=ReportSummary(total_hours=99.0),
        )
        assert report.total_hours == 99.0

    def test_total_hours_fallback_to_rows(self):
        report = AttendanceReport(
            report_type="TYPE_B",
            rows=(self._make_row(),),
            summary=ReportSummary(total_hours=None),
        )
        # falls back to sum of row.total_hours
        assert report.total_hours == pytest.approx(9.0, abs=0.01)

    def test_multiple_rows(self):
        rows = tuple(self._make_row() for _ in range(5))
        report = AttendanceReport(
            report_type="TYPE_B",
            rows=rows,
            summary=ReportSummary(),
        )
        assert len(report.rows) == 5
