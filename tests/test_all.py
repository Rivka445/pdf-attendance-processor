import pytest
from unittest.mock import MagicMock
from app.models.report_meta import ReportMeta
from app.models.type_a import TypeA
from app.models.type_b import TypeB
from app.models.line_a import LineA
from app.models.line_b import LineB
from app.processing.rules.base_rules import calc_total, minutes_to_str, to_minutes, BREAK_HOURS_A, BREAK_HOURS_B
from app.processing.rules.rules_type_a import generate_type_a
from app.processing.rules.rules_type_b import generate_type_b
from app.processing.classification.classifier import classify_document
from app.processing.parsing.parser_type_a import ParserA
from app.row_extractor import get_cell_value
from app.core.exceptions import OcrError, ClassificationError, UnsupportedFormatError
from app.core.container import Container


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def meta_a():
    return ReportMeta("A", 10, 2022, 10, "08:00", "16:00", True, "test_a")

@pytest.fixture
def meta_b():
    return ReportMeta("B", 9, 2022, 10, "8:30", "12:00", False, "test_b")

@pytest.fixture
def source_a():
    report = TypeA()
    import calendar
    for day_num in range(2, 12):
        weekday = calendar.weekday(2022, 10, day_num)
        if weekday >= 5:
            continue
        report.lines.append(LineA(
            date=f"{day_num:02d}/10/2022",
            day=["שני","שלישי","רביעי","חמישי","שישי","שבת","ראשון"][weekday],
            start_time="08:00", end_time="16:00",
            break_time=30, total=450,
            hours_100=450, hours_125=0, hours_150=0, shabat=0,
        ))
    return report

@pytest.fixture
def source_b():
    report = TypeB()
    report.month = "09/2022"
    for day_num in range(1, 11):
        report.lines.append(LineB(
            date=f"{day_num}/9/22",
            day="ראשון",
            start_time="8:30", end_time="12:00",
            total=210,
        ))
    return report


# ── base_rules ───────────────────────────────────────────────────────────────

class TestBaseRules:

    def test_calc_total_type_a(self):
        assert calc_total("08:00", "16:00", BREAK_HOURS_A) == 450

    def test_calc_total_type_b(self):
        assert calc_total("8:30", "12:00", BREAK_HOURS_B) == 210

    def test_calc_total_single_digit_hour(self):
        assert calc_total("8:00", "11:00", BREAK_HOURS_B) == 180

    def test_calc_total_end_before_start_returns_zero(self):
        assert calc_total("16:00", "08:00", BREAK_HOURS_A) == 0

    def test_minutes_to_str(self):
        assert minutes_to_str(450) == "7:30"
        assert minutes_to_str(210) == "3:30"
        assert minutes_to_str(0)   == "0:00"
        assert minutes_to_str(60)  == "1:00"

    def test_to_minutes(self):
        assert to_minutes("08:00") == 480
        assert to_minutes("8:30")  == 510
        assert to_minutes("0:00")  == 0


# ── Rules Type A ─────────────────────────────────────────────────────────────

class TestRulesTypeA:

    def test_generates_correct_day_count(self, meta_a, source_a):
        report = generate_type_a(meta_a, source_a)
        assert report.days == len(source_a.lines)

    def test_no_saturday_in_days(self, meta_a, source_a):
        report = generate_type_a(meta_a, source_a)
        assert all(l.day != "שבת" for l in report.lines)

    def test_preserves_source_dates(self, meta_a, source_a):
        report = generate_type_a(meta_a, source_a)
        assert [l.date for l in source_a.lines] == [l.date for l in report.lines]

    def test_end_always_after_start(self, meta_a, source_a):
        report = generate_type_a(meta_a, source_a)
        for l in report.lines:
            assert to_minutes(l.end_time) > to_minutes(l.start_time)

    def test_total_equals_end_minus_start_minus_break(self, meta_a, source_a):
        report = generate_type_a(meta_a, source_a)
        for l in report.lines:
            assert l.total == calc_total(l.start_time, l.end_time, BREAK_HOURS_A)

    def test_hours_100_plus_125_equals_total(self, meta_a, source_a):
        report = generate_type_a(meta_a, source_a)
        for l in report.lines:
            assert l.hours_100 + l.hours_125 + l.hours_150 == l.total

    def test_deterministic_same_seed(self, meta_a, source_a):
        r1 = generate_type_a(meta_a, source_a)
        r2 = generate_type_a(meta_a, source_a)
        assert [(l.start_time, l.end_time) for l in r1.lines] == \
               [(l.start_time, l.end_time) for l in r2.lines]

    def test_different_seeds_differ(self, source_a):
        m1 = ReportMeta("A", 10, 2022, 10, "08:00", "16:00", False, "seed1")
        m2 = ReportMeta("A", 10, 2022, 10, "08:00", "16:00", False, "seed2")
        r1 = generate_type_a(m1, source_a)
        r2 = generate_type_a(m2, source_a)
        assert [(l.start_time, l.end_time) for l in r1.lines] != \
               [(l.start_time, l.end_time) for l in r2.lines]

    def test_summary_totals_correct(self, meta_a, source_a):
        report = generate_type_a(meta_a, source_a)
        assert report.total_hours == sum(l.total for l in report.lines)
        assert report.hours_100   == sum(l.hours_100 for l in report.lines)
        assert report.hours_125   == sum(l.hours_125 for l in report.lines)


# ── Rules Type B ─────────────────────────────────────────────────────────────

class TestRulesTypeB:

    def test_generates_correct_work_day_count(self, meta_b, source_b):
        report = generate_type_b(meta_b, source_b)
        assert report.days == len(source_b.lines)

    def test_shabat_rows_are_empty(self, meta_b, source_b):
        report = generate_type_b(meta_b, source_b)
        for l in report.lines:
            if l.is_shabat:
                assert l.start_time is None
                assert l.end_time is None
                assert l.total is None

    def test_no_break_deducted(self, meta_b, source_b):
        report = generate_type_b(meta_b, source_b)
        for l in report.lines:
            if not l.is_shabat and l.start_time and l.end_time:
                assert l.total == calc_total(l.start_time, l.end_time, BREAK_HOURS_B)

    def test_total_payment_calculated(self, meta_b, source_b):
        report = generate_type_b(meta_b, source_b)
        expected = round(report.total_hours / 60 * report.price_per_hour, 2)
        assert report.total_payment == expected

    def test_shabat_follows_friday(self, meta_b):
        source = TypeB()
        source.month = "09/2022"
        source.lines = [LineB(date="2/9/22", day="שישי", start_time="8:30", end_time="12:00", total=210)]
        report = generate_type_b(meta_b, source)
        shabat = [l for l in report.lines if l.is_shabat]
        assert len(shabat) >= 1
        assert all(l.day == "שבת" for l in shabat)


# ── Classifier ───────────────────────────────────────────────────────────────

class TestClassifier:

    def _make_word(self, text, x, y):
        return {"text": text, "x": x, "y": y}

    def test_classify_type_a_by_percent_columns(self):
        words = [
            self._make_word("100%", 500, 100),
            self._make_word("125%", 600, 100),
            self._make_word("08:00", 300, 500),
        ]
        assert classify_document(words) == "A"

    def test_classify_type_b_by_time_position(self):
        words = [
            self._make_word("08:30", 500, 700),
            self._make_word("12:00", 600, 700),
            self._make_word("1/9/22", 800, 700),
        ]
        assert classify_document(words) == "B"

    def test_classify_unknown_empty(self):
        assert classify_document([]) == "UNKNOWN"


# ── ParserA ───────────────────────────────────────────────────────────────────

class TestParserA:

    def test_extract_meta_basic(self):
        text = "08:00 16:00 00:30 7.50 7.50 0.00 0.00 0.00 01/10/2022\n" * 5
        meta = ParserA().extract_meta(text, seed="test")
        assert meta.doc_type == "A"
        assert meta.month == 10
        assert meta.year == 2022
        assert meta.work_days == 5

    def test_extract_meta_typical_times(self):
        text = "08:00 16:00 00:30 7.50 01/10/2022\n" * 10
        meta = ParserA().extract_meta(text, seed="test")
        assert meta.typical_start == "08:00"
        assert meta.typical_end == "16:00"

    def test_extract_meta_no_dates_returns_defaults(self):
        meta = ParserA().extract_meta("no times here", seed="test")
        assert meta.month == 1
        assert meta.year == 2000


# ── RowExtractor ─────────────────────────────────────────────────────────────

class TestRowExtractor:

    def test_minute_field_zero_shows_zero(self):
        line = LineA(total=0, hours_100=0, hours_125=0, hours_150=0, shabat=0, break_time=0)
        assert get_cell_value(line, "total") == "0:00"

    def test_minute_field_value(self):
        line = LineA(total=450)
        assert get_cell_value(line, "total") == "7:30"

    def test_string_field(self):
        line = LineA(date="01/10/2022")
        assert get_cell_value(line, "date") == "01/10/2022"

    def test_none_field_returns_empty(self):
        line = LineA(date=None)
        assert get_cell_value(line, "date") == ""


# ── Container / DI ───────────────────────────────────────────────────────────

class TestContainer:

    def test_default_handlers_registered(self):
        c = Container()
        assert c.get_handler("A") is not None
        assert c.get_handler("B") is not None
        assert c.get_handler("C") is None

    def test_register_new_type(self):
        c = Container()
        mock_parser = MagicMock(spec=["parse", "extract_meta"])
        mock_rules  = MagicMock(spec=["apply"])
        c.register_type("C", parser=mock_parser, rules=mock_rules)
        assert c.get_handler("C") is not None
        assert c.get_handler("C").parser is mock_parser
        assert c.get_handler("C").rules  is mock_rules

    def test_default_renderers_available(self):
        c = Container()
        assert c.get_renderer("pdf")   is not None
        assert c.get_renderer("excel") is not None
        assert c.get_renderer("html")  is not None

    def test_register_custom_renderer(self):
        c = Container()
        mock_renderer = MagicMock()
        c.register_renderer("csv", mock_renderer)
        assert c.get_renderer("csv") is mock_renderer

    def test_unknown_renderer_returns_none(self):
        c = Container()
        assert c.get_renderer("unknown") is None

    def test_handler_prepare_input_a(self):
        c = Container()
        handler = c.get_handler("A")
        words = [{"text": "test", "x": 0, "y": 0}]
        c.build_lines = MagicMock(return_value=["line1"])
        result = handler.prepare_input(words, c)
        assert result == "line1"

    def test_handler_prepare_input_b(self):
        c = Container()
        handler = c.get_handler("B")
        words = [{"text": "test", "x": 0, "y": 0}]
        result = handler.prepare_input(words, c)
        assert result is words


# ── Pipeline ─────────────────────────────────────────────────────────────────

class TestPipeline:

    def test_unsupported_format_raises(self):
        from app.core.pipeline import run_pipeline
        c = Container()
        with pytest.raises(UnsupportedFormatError):
            run_pipeline("any.pdf", formats=["csv"], container=c)

    def test_ocr_failure_raises_ocr_error(self):
        from app.core.pipeline import run_pipeline
        c = Container()
        c.extract_words = MagicMock(side_effect=RuntimeError("OCR crash"))
        with pytest.raises(OcrError):
            run_pipeline("any.pdf", formats=["html"], container=c)

    def test_classification_unknown_raises(self):
        from app.core.pipeline import run_pipeline
        c = Container()
        c.extract_words = MagicMock(return_value=[{"text": "x", "x": 0, "y": 0}])
        c.classify = MagicMock(return_value="UNKNOWN")
        with pytest.raises(ClassificationError):
            run_pipeline("any.pdf", formats=["html"], container=c)

    def test_full_pipeline_type_a(self, tmp_path):
        from app.core.pipeline import run_pipeline
        c = Container()
        meta = ReportMeta("A", 10, 2022, 5, "08:00", "16:00", False, "test")
        mock_source = MagicMock()
        mock_source.lines = []
        c.extract_words = MagicMock(return_value=[{"text": "100%", "x": 500, "y": 100}])
        c.classify      = MagicMock(return_value="A")
        handler = c.get_handler("A")
        handler.parser.parse        = MagicMock(return_value=mock_source)
        handler.parser.extract_meta = MagicMock(return_value=meta)
        handler.rules.apply         = MagicMock(return_value=mock_source)
        c.get_renderer("html").render = MagicMock(return_value=str(tmp_path / "v1.html"))
        created = run_pipeline("test.pdf", n=1, formats=["html"],
                               output_dir=str(tmp_path), container=c)
        assert len(created) == 1
        handler.rules.apply.assert_called_once()

    def test_pipeline_uses_handler_not_if_elif(self, tmp_path):
        from app.core.pipeline import run_pipeline
        c = Container()
        meta = ReportMeta("C", 1, 2023, 5, "09:00", "17:00", False, "test_c")
        mock_source = MagicMock()
        mock_source.lines = []
        mock_report = MagicMock()
        mock_report.lines = []
        c.extract_words = MagicMock(return_value=[{"text": "x", "x": 0, "y": 0}])
        c.classify      = MagicMock(return_value="C")
        mock_parser = MagicMock()
        mock_parser.parse.return_value        = mock_source
        mock_parser.extract_meta.return_value = meta
        mock_rules  = MagicMock()
        mock_rules.apply.return_value = mock_report
        c.register_type("C", parser=mock_parser, rules=mock_rules)
        c.get_renderer("html").render = MagicMock(return_value=str(tmp_path / "v1.html"))
        created = run_pipeline("test.pdf", n=1, formats=["html"],
                               output_dir=str(tmp_path), container=c)
        assert len(created) == 1
        mock_rules.apply.assert_called_once()
