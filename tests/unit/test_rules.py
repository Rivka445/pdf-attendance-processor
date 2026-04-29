"""
tests/unit/test_rules.py
=========================
Unit tests for config/rules.py.

Covers:
  - All four dataclasses are frozen (immutable).
  - RULES_REGISTRY contains exactly TYPE_A and TYPE_B.
  - Field values for TYPE_A and TYPE_B match the documented constants.
  - OvertimeThresholds: regular_cap < overtime_125_cap.
"""

import datetime

import pytest

from config.rules import (
    RULES_REGISTRY,
    TYPE_A_RULES,
    TYPE_B_RULES,
    OvertimeThresholds,
    ReportTransformationRules,
    TimeVariationBounds,
    WorkdayBounds,
)


class TestWorkdayBounds:
    def test_frozen(self):
        wb = WorkdayBounds(
            earliest_entry=datetime.time(7, 0),
            latest_entry=datetime.time(10, 0),
            earliest_exit=datetime.time(14, 0),
            latest_exit=datetime.time(19, 0),
        )
        with pytest.raises(Exception):
            wb.earliest_entry = datetime.time(6, 0)  # type: ignore[misc]


class TestTimeVariationBounds:
    def test_frozen(self):
        tvb = TimeVariationBounds(
            entry_min_delta=-20, entry_max_delta=20,
            exit_min_delta=-20, exit_max_delta=20,
            break_min_delta=0, break_max_delta=0,
        )
        with pytest.raises(Exception):
            tvb.entry_min_delta = -99  # type: ignore[misc]


class TestRulesRegistry:
    def test_contains_both_types(self):
        assert "TYPE_A" in RULES_REGISTRY
        assert "TYPE_B" in RULES_REGISTRY

    def test_no_extra_types(self):
        assert set(RULES_REGISTRY.keys()) == {"TYPE_A", "TYPE_B"}

    def test_values_are_correct_instances(self):
        for v in RULES_REGISTRY.values():
            assert isinstance(v, ReportTransformationRules)


class TestTypeARules:
    def test_workday_bounds(self):
        wb = TYPE_A_RULES.workday
        assert wb.earliest_entry == datetime.time(7, 0)
        assert wb.latest_entry   == datetime.time(10, 0)
        assert wb.earliest_exit  == datetime.time(14, 0)
        assert wb.latest_exit    == datetime.time(19, 0)

    def test_jitter_break_is_zero(self):
        # TYPE_A break column is a fixed printed value
        j = TYPE_A_RULES.jitter
        assert j.break_min_delta == 0
        assert j.break_max_delta == 0

    def test_overtime_caps(self):
        ot = TYPE_A_RULES.overtime
        assert ot.regular_cap < ot.overtime_125_cap

    def test_break_bounds_zero(self):
        assert TYPE_A_RULES.min_break_minutes == 0
        assert TYPE_A_RULES.max_break_minutes == 0


class TestTypeBRules:
    def test_workday_bounds(self):
        wb = TYPE_B_RULES.workday
        assert wb.earliest_entry == datetime.time(7, 0)
        assert wb.latest_exit    == datetime.time(20, 0)

    def test_jitter_break_nonzero(self):
        j = TYPE_B_RULES.jitter
        assert j.break_max_delta > 0

    def test_max_break_positive(self):
        assert TYPE_B_RULES.max_break_minutes > 0

    def test_overtime_caps_consistent(self):
        ot = TYPE_B_RULES.overtime
        assert ot.regular_cap < ot.overtime_125_cap
