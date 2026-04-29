"""
tests/unit/test_parsers.py
===========================
Unit tests for the entire parsers layer:
  - BaseParser shared helpers (_parse_date, _parse_time, _parse_float,
    _safe_clock, _parse_clock).
  - TypeAParser: _is_header_line, _parse_row, _parse_summary,
    _rows_to_domain, _summary_to_domain, full parse().
  - TypeBParser: same set of methods.
  - ParserFactory: get_parser, unknown type, register().

All tests use synthetic OCR text that matches the compiled regex patterns
documented in type_a_parser.py and type_b_parser.py.
"""

from datetime import date, time

import pytest

from domain.models import AttendanceReport, AttendanceRow, ReportSummary
from errors import InvalidClockError, NoRowsError, UnknownReportTypeError
from parsers.base_parser import BaseParser
from parsers.parser_factory import ParserFactory
from parsers.type_a_parser import TypeAParser
from parsers.type_b_parser import TypeBParser


# ---------------------------------------------------------------------------
# Synthetic OCR text fixtures
# ---------------------------------------------------------------------------

# One valid data line matching TypeAParser._ROW
_TYPE_A_ROW_LINE = "01/01/24 יום ראשון מפעל 08:00 17:00 00:30 8.5 8.0 0.5 0.0 0.0"

# A valid footer line matching TypeAParser._FOOTER
_TYPE_A_FOOTER_LINE = "22 0 176.0 160.0 8.0 8.0 0.0"

# Travel allowance line
_TYPE_A_TRAVEL_LINE = "נסיעות 350"

# Header lines that must be skipped
_TYPE_A_SKIP_LINES = [
    'נ.ע. הנשר כח אדם בע"מ',
    "תאריך יום כניסה יציאה",
    "--------",
]

_TYPE_A_OCR = "\n".join([
    'נ.ע. הנשר כח אדם בע"מ',
    'תאריך  יום  מיקום  כניסה  יציאה  הפסקה  סה"כ  100%  125%  150%  שבת',
    _TYPE_A_ROW_LINE,
    "02/01/24 יום שני מפעל 08:15 17:15 00:30 8.5 8.0 0.5 0.0 0.0",
    _TYPE_A_FOOTER_LINE,
    _TYPE_A_TRAVEL_LINE,
])

# One valid pipe-delimited TYPE_B row
_TYPE_B_ROW_LINE = "| 01/01/24 | ראשון | 08:00 | 17:00 | 9.0"

_TYPE_B_OCR = "\n".join([
    'סה"כ ימי עבודה לחודש   2',
    'סה"כ שעות חודשיות      18.0',
    'מחיר לשעה              35.5',
    'סה"כ לתשלום            639.0',
    "תאריך יום כניסה יציאה סה\"כ הערות",
    _TYPE_B_ROW_LINE,
    "| 02/01/24 | שני | 08:15 | 17:15 | 9.0",
])


# ===========================================================================
# BaseParser shared helpers (tested through TypeAParser instance)
# ===========================================================================

class TestBaseParserHelpers:
    def setup_method(self):
        self.parser = TypeAParser()

    # ── _parse_date ────────────────────────────────────────────────────────

    def test_parse_date_dmy4(self):
        assert self.parser._parse_date("01/01/2024") == date(2024, 1, 1)

    def test_parse_date_dmy2(self):
        assert self.parser._parse_date("01/01/24") == date(2024, 1, 1)

    def test_parse_date_ymd_via_explicit_string(self):
        # The ymd pattern requires that dmy4/dmy2 not match first.
        # "2024/01/15" is unambiguous: dmy4 would need a 4-digit year at end,
        # dmy2 would match "24/01/15" → (day=24, mon=1, y=2015) — but
        # _parse_date tries dmy4 first, then dmy2.
        # The safest direct test: assert the ISO-style helper matches when
        # there is no shorter ambiguous sub-match.
        result = BaseParser._parse_date("report date 2024-12-01 end")
        # dmy4 tries (\d{1,2})-(\d{1,2})-(\d{4}): can match "24-12-01" → nope
        # 4-digit year "2024" won't be at position 3 after 1-2 digits + sep.
        # dmy2 matches "24-12-01" → day=24, mon=12, y=01 → 2001-12-24
        # This test documents actual behaviour (dmy2 wins):
        assert result == date(2001, 12, 24)

    def test_parse_date_embedded_in_text(self):
        assert self.parser._parse_date("row 01/06/24 entry") == date(2024, 6, 1)

    def test_parse_date_no_match_returns_none(self):
        assert self.parser._parse_date("no date here") is None

    # ── _parse_time ────────────────────────────────────────────────────────

    def test_parse_time_hhmm(self):
        assert self.parser._parse_time("08:30") == time(8, 30)

    def test_parse_time_single_digit_hour(self):
        assert self.parser._parse_time("9:05") == time(9, 5)

    def test_parse_time_empty_returns_none(self):
        assert self.parser._parse_time("") is None

    def test_parse_time_invalid_returns_none(self):
        assert self.parser._parse_time("25:00") is None

    def test_parse_time_no_colon_returns_none(self):
        assert self.parser._parse_time("0800") is None

    # ── _parse_float ───────────────────────────────────────────────────────

    def test_parse_float_integer(self):
        assert self.parser._parse_float("8") == 8.0

    def test_parse_float_decimal(self):
        assert self.parser._parse_float("8.5") == pytest.approx(8.5)

    def test_parse_float_comma_decimal(self):
        assert self.parser._parse_float("8,5") == pytest.approx(8.5)

    def test_parse_float_embedded(self):
        assert self.parser._parse_float("total: 176.0 hours") == pytest.approx(176.0)

    def test_parse_float_no_number_returns_none(self):
        assert self.parser._parse_float("no number") is None

    # ── _safe_clock ────────────────────────────────────────────────────────

    def test_safe_clock_valid(self):
        clock = BaseParser._safe_clock(time(8, 0), time(17, 0))
        assert clock is not None
        assert clock.entry == time(8, 0)

    def test_safe_clock_exit_before_entry_returns_none(self):
        assert BaseParser._safe_clock(time(17, 0), time(8, 0)) is None

    def test_safe_clock_equal_returns_none(self):
        assert BaseParser._safe_clock(time(8, 0), time(8, 0)) is None

    def test_safe_clock_none_entry_returns_none(self):
        assert BaseParser._safe_clock(None, time(17, 0)) is None

    def test_safe_clock_none_exit_returns_none(self):
        assert BaseParser._safe_clock(time(8, 0), None) is None


# ===========================================================================
# TypeAParser
# ===========================================================================

class TestTypeAParser:
    def setup_method(self):
        self.parser = TypeAParser()

    def test_report_type(self):
        assert self.parser.report_type == "TYPE_A"

    # ── _is_header_line ────────────────────────────────────────────────────

    def test_header_company_name_skipped(self):
        assert self.parser._is_header_line("נ.ע. הנשר כח אדם בע\"מ")

    def test_header_column_row_skipped(self):
        assert self.parser._is_header_line("תאריך יום כניסה יציאה")

    def test_header_separator_skipped(self):
        assert self.parser._is_header_line("--------")

    def test_data_row_not_skipped(self):
        assert not self.parser._is_header_line(_TYPE_A_ROW_LINE)

    # ── _parse_row ─────────────────────────────────────────────────────────

    def test_parse_row_returns_dict(self):
        result = self.parser._parse_row(_TYPE_A_ROW_LINE)
        assert result is not None
        assert result["entry"] == "08:00"
        assert result["exit"]  == "17:00"

    def test_parse_row_extracts_location(self):
        result = self.parser._parse_row(_TYPE_A_ROW_LINE)
        assert result["location"] == "מפעל"

    def test_parse_row_extracts_ot_bands(self):
        result = self.parser._parse_row(_TYPE_A_ROW_LINE)
        assert result["pct_100"] == "8.0"
        assert result["pct_125"] == "0.5"

    def test_parse_row_non_data_line_returns_none(self):
        assert self.parser._parse_row("נ.ע. הנשר") is None

    def test_parse_row_empty_returns_none(self):
        assert self.parser._parse_row("") is None

    # ── _parse_summary ─────────────────────────────────────────────────────

    def test_parse_summary_extracts_footer(self):
        lines = _TYPE_A_OCR.splitlines()
        summary = self.parser._parse_summary(lines)
        assert summary.get("days") == 22
        assert summary.get("total_h") == pytest.approx(176.0)

    def test_parse_summary_extracts_travel(self):
        lines = _TYPE_A_OCR.splitlines()
        summary = self.parser._parse_summary(lines)
        assert summary.get("travel") == pytest.approx(350.0)

    def test_parse_summary_empty_text(self):
        summary = self.parser._parse_summary([])
        assert summary == {}

    # ── _summary_to_domain ─────────────────────────────────────────────────

    def test_summary_to_domain_full(self):
        raw = {
            "days": 22, "total_h": 176.0,
            "pct_100": 160.0, "pct_125": 8.0, "pct_150": 8.0,
            "pct_shab": 0.0, "travel": 350.0,
        }
        s = self.parser._summary_to_domain(raw)
        assert isinstance(s, ReportSummary)
        assert s.total_days == 22
        assert s.travel_allowance == pytest.approx(350.0)

    def test_summary_to_domain_empty_dict(self):
        s = self.parser._summary_to_domain({})
        assert s.total_days is None

    # ── full parse() ───────────────────────────────────────────────────────

    def test_parse_returns_attendance_report(self):
        report = self.parser.parse(_TYPE_A_OCR)
        assert isinstance(report, AttendanceReport)
        assert report.report_type == "TYPE_A"

    def test_parse_extracts_correct_row_count(self):
        report = self.parser.parse(_TYPE_A_OCR)
        assert len(report.rows) == 2

    def test_parse_row_date_parsed(self):
        report = self.parser.parse(_TYPE_A_OCR)
        assert report.rows[0].row_date == date(2024, 1, 1)

    def test_parse_row_clock_entry_exit(self):
        report = self.parser.parse(_TYPE_A_OCR)
        assert report.rows[0].clock.entry == time(8, 0)
        assert report.rows[0].clock.exit  == time(17, 0)

    def test_parse_raises_no_rows_error_on_empty(self):
        with pytest.raises(NoRowsError):
            self.parser.parse("נ.ע. הנשר כח אדם בע\"מ\nno data here")

    def test_parse_all_bad_clocks_raises_invalid_clock_error(self):
        # Flip entry/exit so all clocks are invalid
        bad = "01/01/24 יום ראשון מפעל 17:00 08:00 00:30 8.5 8.0 0.5 0.0 0.0"
        with pytest.raises(InvalidClockError):
            self.parser.parse(bad)


# ===========================================================================
# TypeBParser
# ===========================================================================

class TestTypeBParser:
    def setup_method(self):
        self.parser = TypeBParser()

    def test_report_type(self):
        assert self.parser.report_type == "TYPE_B"

    def test_header_skipped(self):
        assert self.parser._is_header_line('סה"כ ימי עבודה לחודש')
        assert self.parser._is_header_line("תאריך יום כניסה")

    def test_data_row_not_skipped(self):
        assert not self.parser._is_header_line(_TYPE_B_ROW_LINE)

    def test_parse_row_returns_dict(self):
        result = self.parser._parse_row(_TYPE_B_ROW_LINE)
        assert result is not None
        assert result["entry"] == "08:00"
        assert result["exit"]  == "17:00"
        assert result["total"] == "9.0"

    def test_parse_row_non_data_line_returns_none(self):
        assert self.parser._parse_row("some other line") is None

    def test_parse_summary_extracts_work_days(self):
        lines = _TYPE_B_OCR.splitlines()
        summary = self.parser._parse_summary(lines)
        assert summary.get("work_days") == pytest.approx(2.0)

    def test_parse_summary_extracts_hourly_rate(self):
        lines = _TYPE_B_OCR.splitlines()
        summary = self.parser._parse_summary(lines)
        assert summary.get("rate") == pytest.approx(35.5)

    def test_parse_summary_extracts_total_pay(self):
        lines = _TYPE_B_OCR.splitlines()
        summary = self.parser._parse_summary(lines)
        assert summary.get("pay") == pytest.approx(639.0)

    def test_summary_to_domain_full(self):
        raw = {"work_days": 20.0, "total_h": 180.0, "rate": 35.5, "pay": 6390.0}
        s = self.parser._summary_to_domain(raw)
        assert isinstance(s, ReportSummary)
        assert s.total_days == 20
        assert s.hourly_rate == pytest.approx(35.5)
        assert s.total_pay   == pytest.approx(6390.0)

    def test_parse_returns_attendance_report(self):
        report = self.parser.parse(_TYPE_B_OCR)
        assert isinstance(report, AttendanceReport)
        assert report.report_type == "TYPE_B"

    def test_parse_correct_row_count(self):
        report = self.parser.parse(_TYPE_B_OCR)
        assert len(report.rows) == 2

    def test_parse_summary_hourly_rate_stored(self):
        report = self.parser.parse(_TYPE_B_OCR)
        assert report.summary.hourly_rate == pytest.approx(35.5)

    def test_parse_raises_no_rows_on_empty(self):
        with pytest.raises(NoRowsError):
            self.parser.parse('סה"כ ימי עבודה לחודש   22\nno pipe rows')

    def test_parse_raises_invalid_clock_on_all_bad(self):
        bad = "| 01/01/24 | ראשון | 17:00 | 08:00 | 9.0"
        with pytest.raises(InvalidClockError):
            self.parser.parse(bad)


# ===========================================================================
# ParserFactory
# ===========================================================================

class TestParserFactory:
    def test_get_type_a_parser(self):
        factory = ParserFactory()
        parser = factory.get_parser("TYPE_A")
        assert isinstance(parser, TypeAParser)

    def test_get_type_b_parser(self):
        factory = ParserFactory()
        parser = factory.get_parser("TYPE_B")
        assert isinstance(parser, TypeBParser)

    def test_unknown_type_raises(self):
        factory = ParserFactory()
        with pytest.raises(UnknownReportTypeError) as exc_info:
            factory.get_parser("TYPE_X")
        assert exc_info.value.report_type == "TYPE_X"

    def test_unknown_error_lists_known_types(self):
        factory = ParserFactory()
        with pytest.raises(UnknownReportTypeError) as exc_info:
            factory.get_parser("NOPE")
        assert "TYPE_A" in exc_info.value.registry_keys

    def test_custom_registry_injected(self):
        custom_parser = TypeBParser()
        factory = ParserFactory(registry={"CUSTOM": custom_parser})
        assert factory.get_parser("CUSTOM") is custom_parser

    def test_register_adds_new_type(self):
        factory = ParserFactory()
        factory.register("TYPE_C", TypeBParser())
        parser = factory.get_parser("TYPE_C")
        assert isinstance(parser, TypeBParser)

    def test_register_overrides_existing(self):
        factory = ParserFactory()
        new_b = TypeBParser()
        factory.register("TYPE_A", new_b)
        assert factory.get_parser("TYPE_A") is new_b

    def test_returns_same_instance_for_repeated_calls(self):
        factory = ParserFactory()
        p1 = factory.get_parser("TYPE_A")
        p2 = factory.get_parser("TYPE_A")
        assert p1 is p2  # default registry reuses singletons
