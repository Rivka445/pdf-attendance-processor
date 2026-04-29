"""
transformation/strategy.py
===========================
Strategy Pattern — one concrete strategy per report type.

Each strategy knows how to apply rules-based jitter to a *single* row and
return a fully recalculated replacement row.  The TransformationService
selects the right strategy at runtime using ``report.report_type``.

Public surface
--------------
TransformationStrategy        — ABC (the contract)
TypeATransformationStrategy   — entry/exit jitter + workday clamping
TypeBTransformationStrategy   — entry/exit/break jitter + OT recalculation
"""

from __future__ import annotations

import hashlib
import logging
import random
from abc import ABC, abstractmethod
from datetime import date, time

from config.rules import OvertimeThresholds, ReportTransformationRules
from domain.models import (
    AttendanceRow,
    BreakRecord,
    OvertimeBuckets,
    TimeRange,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Row-level deterministic RNG
# ---------------------------------------------------------------------------

def _row_rng(row_date: date) -> random.Random:
    """
    Create a seeded :class:`random.Random` from a row's date.

    Seed key is the date formatted as YYYYMMDD, SHA-256 hashed so that
    adjacent calendar days produce independent sequences.
    """
    seed_key = row_date.strftime("%Y%m%d").encode()
    digest   = hashlib.sha256(seed_key).hexdigest()[:8]
    return random.Random(int(digest, 16))


# ---------------------------------------------------------------------------
# Pure time-manipulation helpers
# ---------------------------------------------------------------------------

def _shift_time(t: time, delta_minutes: int) -> time:
    """Add *delta_minutes* to *t*, clamped to [00:00, 23:59]."""
    total = t.hour * 60 + t.minute + delta_minutes
    total = max(0, min(total, 23 * 60 + 59))
    return time(total // 60, total % 60)


def _clamp_time(t: time, lo: time, hi: time) -> time:
    """Clamp *t* within [lo, hi]."""
    if t < lo:
        return lo
    if t > hi:
        return hi
    return t


def _compute_overtime(net_hours: float, thresholds: OvertimeThresholds) -> OvertimeBuckets:
    """
    Split *net_hours* into overtime rate buckets.

    Bucket boundaries (from ``OvertimeThresholds``):
      * 0 – regular_cap        → regular_ot  (100 %)
      * regular_cap – 125_cap  → band_125    (125 %)
      * above 125_cap          → band_150    (150 %)
    """
    net        = max(net_hours, 0.0)
    regular_ot = round(min(net, thresholds.regular_cap), 4)
    band_125   = round(max(0.0, min(net, thresholds.overtime_125_cap) - thresholds.regular_cap), 4)
    band_150   = round(max(0.0, net - thresholds.overtime_125_cap), 4)
    total_ot   = round(regular_ot + band_125 + band_150, 4)

    return OvertimeBuckets(
        regular_ot=regular_ot,
        band_125=band_125,
        band_150=band_150,
        weekend_ot=0.0,
        total_ot=total_ot,
    )


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class TransformationStrategy(ABC):
    """
    Contract for all row-level transformation strategies.

    A strategy receives one :class:`AttendanceRow`, the applicable
    :class:`ReportTransformationRules`, and a seeded :class:`random.Random`
    instance, and returns a *new* row with recalculated fields.
    """

    @abstractmethod
    def transform_row(
        self,
        row: AttendanceRow,
        rules: ReportTransformationRules,
    ) -> AttendanceRow:
        """Return a new AttendanceRow with jitter applied per *rules*."""


# ---------------------------------------------------------------------------
# TYPE_A strategy
# ---------------------------------------------------------------------------

class TypeATransformationStrategy(TransformationStrategy):
    """
    TYPE_A jitter: entry and exit times only.

    Break records are printed verbatim in the TYPE_A layout (the column is
    a fixed value from the source document) so ``break_min/max_delta`` is 0
    and the break record is carried forward unchanged.

    Steps
    -----
    1. Draw independent entry/exit deltas from the jitter bounds.
    2. Shift each time by its delta.
    3. Clamp to workday bounds.
    4. Guarantee exit > entry (floor the exit up if needed).
    5. Recalculate ``total_hours`` and ``OvertimeBuckets`` from the new clock.
    """

    def transform_row(
        self,
        row: AttendanceRow,
        rules: ReportTransformationRules,
    ) -> AttendanceRow:
        rng = _row_rng(row.row_date)

        # ── 1 & 2: draw and apply deltas ─────────────────────────────────
        entry_delta = rng.randint(rules.jitter.entry_min_delta, rules.jitter.entry_max_delta)
        exit_delta  = rng.randint(rules.jitter.exit_min_delta,  rules.jitter.exit_max_delta)

        new_entry = _shift_time(row.clock.entry, entry_delta)
        new_exit  = _shift_time(row.clock.exit,  exit_delta)

        # ── 3: clamp to workday bounds ────────────────────────────────────
        new_entry = _clamp_time(new_entry, rules.workday.earliest_entry, rules.workday.latest_entry)
        new_exit  = _clamp_time(new_exit,  rules.workday.earliest_exit,  rules.workday.latest_exit)

        # ── 4: ensure exit is strictly after entry ────────────────────────
        if new_exit <= new_entry:
            new_exit = _clamp_time(
                _shift_time(new_entry, 1),     # at least 1 minute later
                rules.workday.earliest_exit,
                rules.workday.latest_exit,
            )

        new_clock = TimeRange(entry=new_entry, exit=new_exit)

        # ── 5: recalculate totals ─────────────────────────────────────────
        break_min = row.break_rec.duration_min if row.break_rec else 0
        net_hours = round(new_clock.duration_hours - break_min / 60.0, 4)
        overtime  = _compute_overtime(net_hours, rules.overtime) if row.overtime is not None else None

        logger.debug(
            "TypeAStrategy: date=%s  entry %s→%s  exit %s→%s  net_h=%.4f",
            row.row_date,
            row.clock.entry, new_entry,
            row.clock.exit,  new_exit,
            net_hours,
        )

        return AttendanceRow(
            row_date    = row.row_date,
            day_name    = row.day_name,
            clock       = new_clock,
            total_hours = max(net_hours, 0.0),
            location    = row.location,
            break_rec   = row.break_rec,   # unchanged (TYPE_A break is printed value)
            overtime    = overtime,
            notes       = row.notes,
        )


# ---------------------------------------------------------------------------
# TYPE_B strategy
# ---------------------------------------------------------------------------

class TypeBTransformationStrategy(TransformationStrategy):
    """
    TYPE_B jitter: entry, exit, **and** break minutes.

    After shifting the three time dimensions the strategy recomputes
    ``total_hours`` and (re)builds ``OvertimeBuckets`` so every numeric
    column stays internally consistent.

    Steps
    -----
    1. Draw independent deltas for entry, exit, and break minutes.
    2. Shift entry/exit and clamp to workday bounds.
    3. Guarantee exit > entry.
    4. Clamp new break minutes within the rule-defined break bounds.
    5. Rebuild ``BreakRecord`` (if the row had one) with the new duration.
    6. Recalculate net_hours and ``OvertimeBuckets``.
    """

    def transform_row(
        self,
        row: AttendanceRow,
        rules: ReportTransformationRules,
    ) -> AttendanceRow:
        rng = _row_rng(row.row_date)

        # ── 1 & 2: entry / exit ───────────────────────────────────────────
        entry_delta = rng.randint(rules.jitter.entry_min_delta, rules.jitter.entry_max_delta)
        exit_delta  = rng.randint(rules.jitter.exit_min_delta,  rules.jitter.exit_max_delta)
        break_delta = rng.randint(rules.jitter.break_min_delta, rules.jitter.break_max_delta)

        new_entry = _clamp_time(
            _shift_time(row.clock.entry, entry_delta),
            rules.workday.earliest_entry, rules.workday.latest_entry,
        )
        new_exit = _clamp_time(
            _shift_time(row.clock.exit, exit_delta),
            rules.workday.earliest_exit, rules.workday.latest_exit,
        )

        # ── 3: ensure exit > entry ────────────────────────────────────────
        if new_exit <= new_entry:
            new_exit = _clamp_time(
                _shift_time(new_entry, 1),
                rules.workday.earliest_exit,
                rules.workday.latest_exit,
            )

        new_clock = TimeRange(entry=new_entry, exit=new_exit)

        # ── 4: break minutes — clamp within rule bounds ───────────────────
        old_break_min = row.break_rec.duration_min if row.break_rec else 0
        new_break_min = max(
            rules.min_break_minutes,
            min(old_break_min + break_delta, rules.max_break_minutes),
        )
        # Break cannot exceed shift duration
        new_break_min = min(new_break_min, new_clock.duration_minutes - 1)
        new_break_min = max(new_break_min, 0)

        # ── 5: rebuild BreakRecord ────────────────────────────────────────
        new_break_rec: BreakRecord | None = None
        if row.break_rec is not None:
            # Shift the break clock window by the same entry delta so it
            # stays within the shift, then rebuild with the new duration.
            brk_start = _clamp_time(
                _shift_time(row.break_rec.clock.entry, entry_delta),
                new_entry, new_exit,
            )
            brk_end_minutes = (
                brk_start.hour * 60 + brk_start.minute + new_break_min
            )
            brk_end_minutes = min(brk_end_minutes, new_exit.hour * 60 + new_exit.minute - 1)
            brk_end = time(brk_end_minutes // 60, brk_end_minutes % 60)

            if brk_end > brk_start:
                actual_break_min = brk_end.hour * 60 + brk_end.minute - \
                                   brk_start.hour * 60 - brk_start.minute
                new_break_rec = BreakRecord(
                    break_type   = row.break_rec.break_type,
                    clock        = TimeRange(entry=brk_start, exit=brk_end),
                    duration_min = actual_break_min,
                )
                new_break_min = actual_break_min

        # ── 6: recalculate net_hours and OT buckets ───────────────────────
        net_hours = round(new_clock.duration_hours - new_break_min / 60.0, 4)
        net_hours = max(net_hours, 0.0)
        overtime  = _compute_overtime(net_hours, rules.overtime) if row.overtime is not None else None

        logger.debug(
            "TypeBStrategy: date=%s  entry %s→%s  exit %s→%s  break_min %d→%d  net_h=%.4f",
            row.row_date,
            row.clock.entry, new_entry,
            row.clock.exit,  new_exit,
            (row.break_rec.duration_min if row.break_rec else 0), new_break_min,
            net_hours,
        )

        return AttendanceRow(
            row_date    = row.row_date,
            day_name    = row.day_name,
            clock       = new_clock,
            total_hours = net_hours,
            location    = row.location,
            break_rec   = new_break_rec,
            overtime    = overtime,
            notes       = row.notes,
        )
