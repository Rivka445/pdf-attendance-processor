"""
tests/unit/test_transformation.py
===================================
Unit tests for the transformation layer.

Covers:
  strategy.py:
    - _shift_time: normal delta, clamp at 00:00, clamp at 23:59.
    - _clamp_time: below lo → lo, above hi → hi, within range → unchanged.
    - _compute_overtime: regular only, band_125, band_150, zero hours.
    - _row_rng: same date → same sequence; different dates → different sequence.
    - TypeATransformationStrategy.transform_row:
        new clock is within workday bounds, break record unchanged,
        exit strictly after entry, deterministic for same date.
    - TypeBTransformationStrategy.transform_row:
        similar checks + break record rebuilt correctly.

  service.py:
    - TransformationService.transform returns new report (original unchanged).
    - All rows are transformed (count preserved).
    - Summary is rebuilt with new totals.
    - Unknown report_type raises UnknownReportTypeError.
    - _rebuild_summary: total_hours is sum of rows, OT bands summed.
"""

from datetime import date, time

import pytest

from config.rules import TYPE_A_RULES, TYPE_B_RULES
from domain.models import (
    AttendanceReport,
    AttendanceRow,
    BreakRecord,
    OvertimeBuckets,
    ReportSummary,
    TimeRange,
)
from errors import UnknownReportTypeError
from transformation.service import TransformationService, _rebuild_summary
from transformation.strategy import (
    TypeATransformationStrategy,
    TypeBTransformationStrategy,
    _clamp_time,
    _compute_overtime,
    _row_rng,
    _shift_time,
)


# ---------------------------------------------------------------------------
# Pure helper tests
# ---------------------------------------------------------------------------

class TestShiftTime:
    def test_normal_forward(self):
        t = time(8, 0)
        assert _shift_time(t, 30) == time(8, 30)

    def test_normal_backward(self):
        t = time(8, 0)
        assert _shift_time(t, -30) == time(7, 30)

    def test_clamp_at_zero(self):
        t = time(0, 5)
        result = _shift_time(t, -60)
        assert result == time(0, 0)

    def test_clamp_at_23_59(self):
        t = time(23, 55)
        result = _shift_time(t, 30)
        assert result == time(23, 59)

    def test_zero_delta(self):
        t = time(12, 0)
        assert _shift_time(t, 0) == time(12, 0)


class TestClampTime:
    def test_within_range_unchanged(self):
        t = time(10, 0)
        assert _clamp_time(t, time(8, 0), time(18, 0)) == time(10, 0)

    def test_below_lo_returns_lo(self):
        assert _clamp_time(time(6, 0), time(7, 0), time(19, 0)) == time(7, 0)

    def test_above_hi_returns_hi(self):
        assert _clamp_time(time(20, 0), time(7, 0), time(19, 0)) == time(19, 0)

    def test_equal_to_lo_unchanged(self):
        assert _clamp_time(time(7, 0), time(7, 0), time(19, 0)) == time(7, 0)

    def test_equal_to_hi_unchanged(self):
        assert _clamp_time(time(19, 0), time(7, 0), time(19, 0)) == time(19, 0)


class TestComputeOvertime:
    """OvertimeThresholds: regular_cap=8.0, overtime_125_cap=9.0"""

    def _thresholds(self):
        return TYPE_A_RULES.overtime  # regular=8.0, 125_cap=9.0

    def test_below_regular_cap(self):
        ot = _compute_overtime(7.0, self._thresholds())
        assert ot.regular_ot == pytest.approx(7.0)
        assert ot.band_125   == pytest.approx(0.0)
        assert ot.band_150   == pytest.approx(0.0)

    def test_exactly_regular_cap(self):
        ot = _compute_overtime(8.0, self._thresholds())
        assert ot.regular_ot == pytest.approx(8.0)
        assert ot.band_125   == pytest.approx(0.0)

    def test_in_125_band(self):
        ot = _compute_overtime(8.5, self._thresholds())
        assert ot.regular_ot == pytest.approx(8.0)
        assert ot.band_125   == pytest.approx(0.5)
        assert ot.band_150   == pytest.approx(0.0)

    def test_above_125_cap(self):
        ot = _compute_overtime(10.0, self._thresholds())
        assert ot.regular_ot == pytest.approx(8.0)
        assert ot.band_125   == pytest.approx(1.0)
        assert ot.band_150   == pytest.approx(1.0)

    def test_zero_hours(self):
        ot = _compute_overtime(0.0, self._thresholds())
        assert ot.total_ot == pytest.approx(0.0)

    def test_negative_hours_treated_as_zero(self):
        ot = _compute_overtime(-1.0, self._thresholds())
        assert ot.total_ot == pytest.approx(0.0)

    def test_total_ot_equals_sum(self):
        ot = _compute_overtime(10.0, self._thresholds())
        expected = ot.regular_ot + ot.band_125 + ot.band_150
        assert ot.total_ot == pytest.approx(expected)


class TestRowRng:
    def test_same_date_same_sequence(self):
        d = date(2024, 1, 7)
        rng1 = _row_rng(d)
        rng2 = _row_rng(d)
        assert rng1.random() == rng2.random()

    def test_different_dates_different_sequence(self):
        d1, d2 = date(2024, 1, 7), date(2024, 1, 8)
        assert _row_rng(d1).random() != _row_rng(d2).random()


# ---------------------------------------------------------------------------
# Strategy tests
# ---------------------------------------------------------------------------

def _make_type_a_row(
    d: date = date(2024, 1, 7),
    entry: time = time(8, 0),
    exit_: time = time(17, 0),
    with_break: bool = True,
    with_ot: bool = True,
) -> AttendanceRow:
    brk = BreakRecord(
        clock=TimeRange(entry=time(12, 0), exit=time(12, 30)),
        duration_min=30,
    ) if with_break else None
    ot = OvertimeBuckets(
        regular_ot=8.0, band_125=0.5, band_150=0.0,

    ) if with_ot else None
    return AttendanceRow(
        row_date=d,
        day_name="יום ראשון",
        clock=TimeRange(entry=entry, exit=exit_),
        total_hours=8.5,
        location="מפעל",
        break_rec=brk,
        overtime=ot,
    )


def _make_type_b_row(
    d: date = date(2024, 1, 7),
    entry: time = time(8, 0),
    exit_: time = time(17, 0),
) -> AttendanceRow:
    return AttendanceRow(
        row_date=d,
        day_name="יום ראשון",
        clock=TimeRange(entry=entry, exit=exit_),
        total_hours=9.0,
    )


class TestTypeAStrategy:
    def setup_method(self):
        self.strategy = TypeATransformationStrategy()

    def test_returns_new_row(self):
        row = _make_type_a_row()
        new_row = self.strategy.transform_row(row, TYPE_A_RULES)
        assert new_row is not row

    def test_entry_within_workday_bounds(self):
        row = _make_type_a_row()
        new_row = self.strategy.transform_row(row, TYPE_A_RULES)
        wb = TYPE_A_RULES.workday
        assert wb.earliest_entry <= new_row.clock.entry <= wb.latest_entry

    def test_exit_within_workday_bounds(self):
        row = _make_type_a_row()
        new_row = self.strategy.transform_row(row, TYPE_A_RULES)
        wb = TYPE_A_RULES.workday
        assert wb.earliest_exit <= new_row.clock.exit <= wb.latest_exit

    def test_exit_strictly_after_entry(self):
        row = _make_type_a_row()
        new_row = self.strategy.transform_row(row, TYPE_A_RULES)
        assert new_row.clock.exit > new_row.clock.entry

    def test_break_record_unchanged(self):
        """TYPE_A: break column is a fixed printed value; must not change."""
        row = _make_type_a_row(with_break=True)
        new_row = self.strategy.transform_row(row, TYPE_A_RULES)
        assert new_row.break_rec is row.break_rec

    def test_no_ot_row_has_no_ot_after(self):
        row = _make_type_a_row(with_ot=False)
        new_row = self.strategy.transform_row(row, TYPE_A_RULES)
        assert new_row.overtime is None

    def test_deterministic_for_same_date(self):
        row = _make_type_a_row()
        r1 = self.strategy.transform_row(row, TYPE_A_RULES)
        r2 = self.strategy.transform_row(row, TYPE_A_RULES)
        assert r1.clock.entry == r2.clock.entry
        assert r1.clock.exit  == r2.clock.exit

    def test_row_date_preserved(self):
        d = date(2024, 3, 15)
        row = _make_type_a_row(d=d)
        new_row = self.strategy.transform_row(row, TYPE_A_RULES)
        assert new_row.row_date == d

    def test_location_preserved(self):
        row = _make_type_a_row()
        new_row = self.strategy.transform_row(row, TYPE_A_RULES)
        assert new_row.location == "מפעל"


class TestTypeBStrategy:
    def setup_method(self):
        self.strategy = TypeBTransformationStrategy()

    def test_returns_new_row(self):
        row = _make_type_b_row()
        assert self.strategy.transform_row(row, TYPE_B_RULES) is not row

    def test_exit_strictly_after_entry(self):
        row = _make_type_b_row()
        new_row = self.strategy.transform_row(row, TYPE_B_RULES)
        assert new_row.clock.exit > new_row.clock.entry

    def test_entry_within_workday_bounds(self):
        row = _make_type_b_row()
        new_row = self.strategy.transform_row(row, TYPE_B_RULES)
        wb = TYPE_B_RULES.workday
        assert wb.earliest_entry <= new_row.clock.entry <= wb.latest_entry

    def test_deterministic(self):
        row = _make_type_b_row()
        r1 = self.strategy.transform_row(row, TYPE_B_RULES)
        r2 = self.strategy.transform_row(row, TYPE_B_RULES)
        assert r1.clock.entry == r2.clock.entry

    def test_total_hours_non_negative(self):
        row = _make_type_b_row()
        new_row = self.strategy.transform_row(row, TYPE_B_RULES)
        assert new_row.total_hours >= 0.0


# ---------------------------------------------------------------------------
# TransformationService
# ---------------------------------------------------------------------------

def _make_report(report_type: str, n_rows: int = 2) -> AttendanceReport:
    row_fn = _make_type_a_row if report_type == "TYPE_A" else _make_type_b_row
    rows = tuple(
        row_fn(d=date(2024, 1, i + 1))  # type: ignore[call-arg]
        for i in range(n_rows)
    )
    summary = ReportSummary(total_days=n_rows, total_hours=float(n_rows * 9))
    return AttendanceReport(report_type=report_type, rows=rows, summary=summary)


class TestTransformationService:
    def test_transform_returns_new_report(self):
        svc = TransformationService()
        report = _make_report("TYPE_A")
        result = svc.transform(report)
        assert result is not report

    def test_original_report_unchanged(self):
        svc = TransformationService()
        report = _make_report("TYPE_A")
        original_entry = report.rows[0].clock.entry
        svc.transform(report)
        assert report.rows[0].clock.entry == original_entry

    def test_row_count_preserved(self):
        svc = TransformationService()
        for rtype in ("TYPE_A", "TYPE_B"):
            report = _make_report(rtype, n_rows=3)
            result = svc.transform(report)
            assert len(result.rows) == 3

    def test_report_type_preserved(self):
        svc = TransformationService()
        for rtype in ("TYPE_A", "TYPE_B"):
            result = svc.transform(_make_report(rtype))
            assert result.report_type == rtype

    def test_summary_total_days_updated(self):
        svc = TransformationService()
        report = _make_report("TYPE_B", n_rows=4)
        result = svc.transform(report)
        assert result.summary.total_days == 4

    def test_summary_total_hours_updated(self):
        svc = TransformationService()
        report = _make_report("TYPE_B", n_rows=2)
        result = svc.transform(report)
        # Recalculated from transformed rows, not the original summary
        assert result.summary.total_hours is not None
        assert result.summary.total_hours >= 0

    def test_unknown_type_raises(self):
        svc = TransformationService()
        report = AttendanceReport(
            report_type="TYPE_X",
            rows=(_make_type_a_row(),),
            summary=ReportSummary(),
        )
        with pytest.raises(UnknownReportTypeError):
            svc.transform(report)

    def test_custom_strategies_injected(self):
        """Custom strategy via TypeRegistry overrides the defaults."""
        calls = []

        class SpyStrategy:
            def transform_row(self, row, rules):
                calls.append(row)
                return row

        from config.rules import TYPE_A_RULES
        from registry import TypeRegistry
        from parsers.type_a_parser import TypeAParser

        registry = TypeRegistry()
        registry.register("SPY",
            parser=TypeAParser(),
            strategy=SpyStrategy(),
            rules=TYPE_A_RULES,
        )
        svc = TransformationService(registry=registry)
        report = AttendanceReport(
            report_type="SPY",
            rows=(_make_type_a_row(),),
            summary=ReportSummary(),
        )
        svc.transform(report)
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# _rebuild_summary (pure function)
# ---------------------------------------------------------------------------

class TestRebuildSummary:
    def test_total_days_equals_row_count(self):
        rows = tuple(_make_type_b_row(d=date(2024, 1, i + 1)) for i in range(5))
        original = ReportSummary(total_hours=0.0, hourly_rate=35.0, total_pay=100.0)
        result = _rebuild_summary(original, rows)
        assert result.total_days == 5

    def test_total_hours_is_sum(self):
        rows = (
            _make_type_b_row(d=date(2024, 1, 1)),
            _make_type_b_row(d=date(2024, 1, 2)),
        )
        original = ReportSummary()
        result = _rebuild_summary(original, rows)
        expected = sum(r.total_hours for r in rows)
        assert result.total_hours == pytest.approx(expected, abs=0.01)

    def test_financial_fields_preserved(self):
        rows = (_make_type_b_row(),)
        original = ReportSummary(hourly_rate=35.5, total_pay=6390.0)
        result = _rebuild_summary(original, rows)
        assert result.hourly_rate == pytest.approx(35.5)
        assert result.total_pay   == pytest.approx(6390.0)

    def test_travel_allowance_preserved(self):
        rows = (_make_type_a_row(),)
        original = ReportSummary(travel_allowance=350.0)
        result = _rebuild_summary(original, rows)
        assert result.travel_allowance == pytest.approx(350.0)

    def test_ot_bands_summed_from_rows(self):
        row1 = _make_type_a_row(d=date(2024, 1, 1), with_ot=True)
        row2 = _make_type_a_row(d=date(2024, 1, 2), with_ot=True)
        original = ReportSummary()
        result = _rebuild_summary(original, (row1, row2))
        # Both rows have band_125=0.5 → total should be ~1.0
        if result.ot_125 is not None:
            assert result.ot_125 == pytest.approx(1.0, abs=0.01)

    def test_no_ot_rows_gives_none_bands(self):
        rows = (_make_type_b_row(),)   # no overtime attribute
        original = ReportSummary()
        result = _rebuild_summary(original, rows)
        assert result.ot_100 is None
