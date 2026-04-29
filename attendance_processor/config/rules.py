"""
config/rules.py
===============
Immutable configuration for every report type.

Three focused dataclasses describe *what is valid* and *how to transform*:

  WorkdayBounds        — earliest / latest permissible entry and exit times
  TimeVariationBounds  — per-field jitter range (minutes) for anonymisation
  OvertimeThresholds   — daily hour caps that decide which OT band applies

  ReportTransformationRules — bundles all three + break bounds into one
                              object that both the RulesEngine (validation)
                              and the Transformer (anonymisation) consume.

RULES_REGISTRY maps a report_type string to its singleton instance so that
any service can do:  rules = RULES_REGISTRY[report.report_type]
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# WorkdayBounds
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WorkdayBounds:
    """Earliest / latest permissible entry and exit within a working day."""

    earliest_entry: datetime.time
    latest_entry:   datetime.time
    earliest_exit:  datetime.time
    latest_exit:    datetime.time


# ---------------------------------------------------------------------------
# TimeVariationBounds
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TimeVariationBounds:
    """Allowed random jitter (in minutes) applied during transformation."""

    entry_min_delta: int   # negative = can shift earlier
    entry_max_delta: int
    exit_min_delta:  int
    exit_max_delta:  int
    break_min_delta: int
    break_max_delta: int


# ---------------------------------------------------------------------------
# OvertimeThresholds
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class OvertimeThresholds:
    """Hours-per-day thresholds that determine the overtime bucket."""

    regular_cap:       float   # hours up to this → 100 %
    overtime_125_cap:  float   # hours above regular_cap up to this → 125 %
                               # anything above overtime_125_cap → 150 %


# ---------------------------------------------------------------------------
# ReportTransformationRules  — the unified config object
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ReportTransformationRules:
    """All rules for one report type, bundled as a single immutable config."""

    workday:           WorkdayBounds
    jitter:            TimeVariationBounds
    overtime:          OvertimeThresholds
    min_break_minutes: int
    max_break_minutes: int


# ---------------------------------------------------------------------------
# Concrete instances
# ---------------------------------------------------------------------------

TYPE_A_RULES = ReportTransformationRules(
    workday=WorkdayBounds(
        earliest_entry=datetime.time(7,  0),
        latest_entry  =datetime.time(10, 0),
        earliest_exit =datetime.time(14, 0),
        latest_exit   =datetime.time(19, 0),
    ),
    jitter=TimeVariationBounds(
        entry_min_delta=-20,
        entry_max_delta= 20,
        exit_min_delta =-20,
        exit_max_delta = 20,
        break_min_delta=  0,
        break_max_delta=  0,   # TYPE_A break column is a fixed printed value
    ),
    overtime=OvertimeThresholds(
        regular_cap      =8.0,
        overtime_125_cap =9.0,
    ),
    min_break_minutes=0,
    max_break_minutes=0,
)

TYPE_B_RULES = ReportTransformationRules(
    workday=WorkdayBounds(
        earliest_entry=datetime.time(7,  0),
        latest_entry  =datetime.time(10, 0),
        earliest_exit =datetime.time(14, 0),
        latest_exit   =datetime.time(20, 0),
    ),
    jitter=TimeVariationBounds(
        entry_min_delta=-20,
        entry_max_delta= 20,
        exit_min_delta =-30,
        exit_max_delta = 30,
        break_min_delta=-10,
        break_max_delta= 10,
    ),
    overtime=OvertimeThresholds(
        regular_cap      =8.0,
        overtime_125_cap =9.0,
    ),
    min_break_minutes= 0,
    max_break_minutes=60,
)

RULES_REGISTRY: dict[str, ReportTransformationRules] = {
    "TYPE_A": TYPE_A_RULES,
    "TYPE_B": TYPE_B_RULES,
}
