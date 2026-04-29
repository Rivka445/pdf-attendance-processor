"""
domain/models.py
================
The Central Contract — Unified Attendance Domain Model.

Hierarchy
─────────
  TimeRange          low-level clock pair (entry + exit, validated)
  BreakRecord        one break segment inside a shift
  OvertimeBuckets    TYPE_A overtime split across rate bands
  AttendanceRow      one calendar day — shared by TYPE_A and TYPE_B
  ReportSummary      aggregate metadata from the report header / footer
  AttendanceReport   the root object: rows + summary

Design Principles:
  - Immutable (frozen=True) — transformers always return NEW objects.
  - AttendanceReport is a plain dataclass — lightweight, no framework magic.
  - Optional fields for type-specific data — no null bleed into shared fields.
  - Pydantic V2 for TimeRange / BreakRecord / OvertimeBuckets / AttendanceRow /
    ReportSummary where field-level validation is valuable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class BreakType(str, Enum):
    """Classifies the nature of a break entry."""
    LUNCH  = "LUNCH"
    SHORT  = "SHORT"
    UNPAID = "UNPAID"
    OTHER  = "OTHER"


# ---------------------------------------------------------------------------
# TimeRange  — low-level clock pair
# ---------------------------------------------------------------------------

class TimeRange(BaseModel):
    """
    A validated clock-in / clock-out pair for a single work segment.

    Replaces the old TimeEntry name; kept as the primitive building block
    used inside both AttendanceRow and BreakRecord.

    Invariant:  exit > entry  (validated at construction time).
    """

    entry: time = Field(..., description="Clock-in  time (HH:MM)")
    exit:  time = Field(..., description="Clock-out time (HH:MM)")

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def _exit_after_entry(self) -> "TimeRange":
        if self.exit <= self.entry:
            raise ValueError(
                f"exit ({self.exit}) must be strictly after entry ({self.entry})"
            )
        return self

    # ── Derived helpers ────────────────────────────────────────────────────
    @property
    def duration_minutes(self) -> int:
        """Total minutes between entry and exit."""
        return (self.exit.hour * 60 + self.exit.minute) - \
               (self.entry.hour * 60 + self.entry.minute)

    @property
    def duration_hours(self) -> float:
        """Total hours (decimal) between entry and exit."""
        return round(self.duration_minutes / 60.0, 4)


# ---------------------------------------------------------------------------
# BreakRecord  — one break segment
# ---------------------------------------------------------------------------

class BreakRecord(BaseModel):
    """
    A single break segment within a shift.

    Present in TYPE_A reports (הפסקה column).
    Absent / None in TYPE_B reports.
    """

    break_type:   BreakType  = Field(default=BreakType.OTHER)
    clock:        TimeRange  = Field(..., description="Break start / end times")
    duration_min: int        = Field(..., ge=0, description="Duration in minutes")

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def _duration_matches_clock(self) -> "BreakRecord":
        computed = self.clock.duration_minutes
        if self.duration_min != computed:
            # Allow a 1-minute tolerance for rounding in OCR-parsed data
            if abs(self.duration_min - computed) > 1:
                raise ValueError(
                    f"duration_min ({self.duration_min}) does not match "
                    f"clock range ({computed} min)"
                )
        return self


# ---------------------------------------------------------------------------
# OvertimeBuckets  — TYPE_A overtime split
# ---------------------------------------------------------------------------

class OvertimeBuckets(BaseModel):
    """
    Overtime hours broken down by rate band.
    Populated only for TYPE_A reports.
    All values are decimal hours (e.g. 1.5 = 90 min).
    """

    regular_ot: float = Field(default=0.0, ge=0.0, description="100 % OT hours")
    band_125:   float = Field(default=0.0, ge=0.0, description="125 % OT hours")
    band_150:   float = Field(default=0.0, ge=0.0, description="150 % OT hours")
    weekend_ot: float = Field(default=0.0, ge=0.0, description="Sabbath / weekend OT hours")
    total_ot:   float = Field(default=0.0, ge=0.0, description="Sum of all OT bands")

    model_config = {"frozen": True}

    @model_validator(mode="after")
    def _total_matches_sum(self) -> "OvertimeBuckets":
        computed = round(
            self.regular_ot + self.band_125 + self.band_150 + self.weekend_ot, 4
        )
        if self.total_ot != 0.0 and abs(computed - self.total_ot) > 0.05:
            raise ValueError(
                f"total_ot ({self.total_ot}) does not match "
                f"sum of bands ({computed})"
            )
        return self


# ---------------------------------------------------------------------------
# AttendanceRow  — one calendar day
# ---------------------------------------------------------------------------

class AttendanceRow(BaseModel):
    """
    A single calendar day's attendance record.

    Both TYPE_A and TYPE_B reports share this structure; the optional fields
    are populated only for the report type that carries that information.

    Shared fields (always present):
        row_date    — the calendar date of this entry
        day_name    — Hebrew day name as it appeared in the document (e.g. יום שני)
        clock       — TimeRange(entry, exit) for the main shift
        total_hours — hours worked as printed in the document column

    Optional fields (type-specific):
        location    — work-site name, e.g. גליליון / גונן  (TYPE_A only)
        break_rec   — break record for this day                (TYPE_A only)
        overtime    — per-day OT band breakdown                (TYPE_A only)
        notes       — free-text cell, e.g. holiday label       (TYPE_B only)
    """

    # ── Shared ─────────────────────────────────────────────────────────────
    row_date:    date       = Field(..., description="Calendar date of this work-day")
    day_name:    str        = Field(..., min_length=1,
                                   description="Hebrew day name (e.g. יום שני)")
    clock:       TimeRange  = Field(..., description="Main shift entry / exit")
    total_hours: float      = Field(..., ge=0.0,
                                   description="Hours for this row as printed in the document")

    # ── TYPE_A specific ─────────────────────────────────────────────────────
    location:   Optional[str]           = Field(default=None,
                                               description="Work-site (TYPE_A)")
    break_rec:  Optional[BreakRecord]   = Field(default=None,
                                               description="Break record (TYPE_A)")
    overtime:   Optional[OvertimeBuckets] = Field(default=None,
                                               description="Per-day OT bands (TYPE_A)")

    # ── TYPE_B specific ─────────────────────────────────────────────────────
    notes:      Optional[str]           = Field(default=None,
                                               description="Free-text cell, e.g. holiday name (TYPE_B)")

    model_config = {"frozen": True}

    # ── Derived helpers ────────────────────────────────────────────────────
    @property
    def net_hours(self) -> float:
        """Shift hours minus break time."""
        brk_min = self.break_rec.duration_min if self.break_rec else 0
        return round(self.clock.duration_hours - brk_min / 60.0, 4)


# ---------------------------------------------------------------------------
# ReportSummary  — aggregate metadata
# ---------------------------------------------------------------------------

class ReportSummary(BaseModel):
    """
    Aggregate-level metadata extracted from the report header / footer.

    These values are preserved as-is; they are NOT recomputed from the rows
    during generation so the layout can be faithfully reproduced.

    Shared:
        total_days    — number of worked days as printed
        total_hours   — monthly total hours as printed

    TYPE_A specific:
        ot_100 / ot_125 / ot_150 / ot_shabbat — OT band totals from footer
        travel_allowance                        — נסיעות line value

    TYPE_B specific:
        hourly_rate   — מחיר לשעה
        total_pay     — סה"כ לתשלום
    """

    # ── Shared ─────────────────────────────────────────────────────────────
    company_name:     Optional[str]   = Field(default=None,
                                             description="Company name from report header")
    total_days:       Optional[int]   = Field(default=None, ge=0,
                                             description="Worked days as printed")
    total_hours:      Optional[float] = Field(default=None, ge=0.0,
                                             description="Monthly total hours as printed")

    # ── TYPE_A footer totals ────────────────────────────────────────────────
    ot_100:           Optional[float] = Field(default=None, ge=0.0)
    ot_125:           Optional[float] = Field(default=None, ge=0.0)
    ot_150:           Optional[float] = Field(default=None, ge=0.0)
    ot_shabbat:       Optional[float] = Field(default=None, ge=0.0)
    travel_allowance: Optional[float] = Field(default=None, ge=0.0,
                                             description="נסיעות allowance")
    bonus:            Optional[float] = Field(default=None, ge=0.0,
                                             description="Bonus amount")

    # ── TYPE_B header totals ────────────────────────────────────────────────
    hourly_rate:         Optional[float] = Field(default=None, ge=0.0,
                                                description="מחיר לשעה")
    total_pay:           Optional[float] = Field(default=None, ge=0.0,
                                                description='סה"כ לתשלום')
    employee_card_month: Optional[str]   = Field(default=None,
                                                description="כרטיס עובד לחודש (month label)")

    model_config = {"frozen": True}


# ---------------------------------------------------------------------------
# AttendanceReport  — root document object
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AttendanceReport:
    """
    The complete parsed representation of one attendance PDF.

    Carrying report_type as a string here (rather than a class hierarchy)
    keeps the model layer simple; the Strategy pattern lives in the service
    layer (parsers, rules engine, transformer).

    Fields
    ──────
    report_type  — "TYPE_A" or "TYPE_B" (matches RULES_REGISTRY keys)
    rows         — immutable ordered sequence of per-day records
    summary      — aggregate header / footer metadata preserved as-is
    """

    report_type: str
    rows:        tuple[AttendanceRow, ...]
    summary:     ReportSummary

    def __post_init__(self) -> None:
        if not self.rows:
            raise ValueError("An attendance report must contain at least one row.")

    # ── Convenience helpers ────────────────────────────────────────────────

    @property
    def total_hours(self) -> float:
        """Summary total if available, otherwise sum of row totals."""
        if self.summary.total_hours is not None:
            return self.summary.total_hours
        return round(sum(r.total_hours for r in self.rows), 2)
