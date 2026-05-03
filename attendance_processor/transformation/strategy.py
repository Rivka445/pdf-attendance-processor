"""
transformation/strategy.py
===========================
Strategy Pattern — one concrete strategy per report type.

TransformationStrategy (ABC)
  _jitter_clock()               ← shared: shift + clamp + guarantee exit > entry
  transform_row()               ← abstract

TypeATransformationStrategy     ← entry/exit jitter, break unchanged
TypeBTransformationStrategy     ← entry/exit/break jitter, break rebuilt
"""

from __future__ import annotations

import hashlib
import logging
import random
from abc import ABC, abstractmethod
from datetime import date, time

from config.rules import OvertimeThresholds, ReportTransformationRules
from domain.models import AttendanceRow, BreakRecord, OvertimeBuckets, TimeRange

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module-level pure helpers
# ---------------------------------------------------------------------------

def _row_rng(row_date: date) -> random.Random:
    seed_key = row_date.strftime("%Y%m%d").encode()
    digest   = hashlib.sha256(seed_key).hexdigest()[:8]
    return random.Random(int(digest, 16))


def _shift_time(t: time, delta_minutes: int) -> time:
    total = max(0, min(t.hour * 60 + t.minute + delta_minutes, 23 * 60 + 59))
    return time(total // 60, total % 60)


def _clamp_time(t: time, lo: time, hi: time) -> time:
    return lo if t < lo else (hi if t > hi else t)


def _compute_overtime(net_hours: float, thresholds: OvertimeThresholds) -> OvertimeBuckets:
    net      = max(net_hours, 0.0)
    regular  = round(min(net, thresholds.regular_cap), 4)
    band_125 = round(max(0.0, min(net, thresholds.overtime_125_cap) - thresholds.regular_cap), 4)
    band_150 = round(max(0.0, net - thresholds.overtime_125_cap), 4)
    return OvertimeBuckets(
        regular_ot=regular, band_125=band_125, band_150=band_150,
        weekend_ot=0.0,
    )


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class TransformationStrategy(ABC):

    @abstractmethod
    def transform_row(self, row: AttendanceRow, rules: ReportTransformationRules) -> AttendanceRow:
        """Return a new AttendanceRow with jitter applied per *rules*."""

    def _jitter_clock(self, row: AttendanceRow, rules: ReportTransformationRules,
                      rng: random.Random) -> TimeRange:
        """Shift entry/exit, clamp to workday bounds, guarantee exit > entry."""
        new_entry = _clamp_time(
            _shift_time(row.clock.entry, rng.randint(rules.jitter.entry_min_delta, rules.jitter.entry_max_delta)),
            rules.workday.earliest_entry, rules.workday.latest_entry,
        )
        new_exit = _clamp_time(
            _shift_time(row.clock.exit, rng.randint(rules.jitter.exit_min_delta, rules.jitter.exit_max_delta)),
            rules.workday.earliest_exit, rules.workday.latest_exit,
        )
        if new_exit <= new_entry:
            new_exit = _clamp_time(
                _shift_time(new_entry, 1),
                rules.workday.earliest_exit, rules.workday.latest_exit,
            )
        return TimeRange(entry=new_entry, exit=new_exit)


# ---------------------------------------------------------------------------
# TYPE_A — entry/exit jitter only, break unchanged
# ---------------------------------------------------------------------------

class TypeATransformationStrategy(TransformationStrategy):

    def transform_row(self, row: AttendanceRow, rules: ReportTransformationRules) -> AttendanceRow:
        rng       = _row_rng(row.row_date)
        new_clock = self._jitter_clock(row, rules, rng)
        break_min = row.break_rec.duration_min if row.break_rec else 0
        net_hours = max(round(new_clock.duration_hours - break_min / 60.0, 4), 0.0)
        return AttendanceRow(
            row_date    = row.row_date,
            day_name    = row.day_name,
            clock       = new_clock,
            total_hours = net_hours,
            location    = row.location,
            break_rec   = row.break_rec,  # TYPE_A: printed value, never changed
            overtime    = _compute_overtime(net_hours, rules.overtime) if row.overtime is not None else None,
            notes       = row.notes,
        )


# ---------------------------------------------------------------------------
# TYPE_B — entry/exit/break jitter, break rebuilt
# ---------------------------------------------------------------------------

class TypeBTransformationStrategy(TransformationStrategy):

    def transform_row(self, row: AttendanceRow, rules: ReportTransformationRules) -> AttendanceRow:
        rng         = _row_rng(row.row_date)
        new_clock   = self._jitter_clock(row, rules, rng)
        break_delta = rng.randint(rules.jitter.break_min_delta, rules.jitter.break_max_delta)

        old_break_min = row.break_rec.duration_min if row.break_rec else 0
        new_break_min = max(rules.min_break_minutes,
                            min(old_break_min + break_delta, rules.max_break_minutes))
        new_break_min = max(0, min(new_break_min, new_clock.duration_minutes - 1))

        new_break_rec: BreakRecord | None = None
        if row.break_rec is not None:
            entry_delta = rng.randint(rules.jitter.entry_min_delta, rules.jitter.entry_max_delta)
            brk_start   = _clamp_time(
                _shift_time(row.break_rec.clock.entry, entry_delta),
                new_clock.entry, new_clock.exit,
            )
            brk_end_min = min(
                brk_start.hour * 60 + brk_start.minute + new_break_min,
                new_clock.exit.hour * 60 + new_clock.exit.minute - 1,
            )
            brk_end = time(brk_end_min // 60, brk_end_min % 60)
            if brk_end > brk_start:
                actual = brk_end.hour * 60 + brk_end.minute - brk_start.hour * 60 - brk_start.minute
                new_break_rec = BreakRecord(
                    break_type   = row.break_rec.break_type,
                    clock        = TimeRange(entry=brk_start, exit=brk_end),
                    duration_min = actual,
                )
                new_break_min = actual

        net_hours = max(round(new_clock.duration_hours - new_break_min / 60.0, 4), 0.0)
        return AttendanceRow(
            row_date    = row.row_date,
            day_name    = row.day_name,
            clock       = new_clock,
            total_hours = net_hours,
            location    = row.location,
            break_rec   = new_break_rec,
            overtime    = _compute_overtime(net_hours, rules.overtime) if row.overtime is not None else None,
            notes       = row.notes,
        )
