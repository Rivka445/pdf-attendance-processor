"""
tests/unit/test_classifier.py
==============================
Unit tests for classification/classifier.py.

Covers:
  - Strong TYPE_A signals → classified as TYPE_A with high confidence.
  - Strong TYPE_B signals → classified as TYPE_B with high confidence.
  - Empty text → LowConfidenceError raised.
  - Ambiguous (balanced) text → LowConfidenceError raised.
  - Custom confidence_threshold respected.
  - ClassificationResult fields are correct.
  - __str__ representation contains key info.
"""

import pytest

from classification.classifier import ClassificationResult, Classifier
from errors import LowConfidenceError


# ---------------------------------------------------------------------------
# Synthetic OCR snippets
# ---------------------------------------------------------------------------

# Heavily TYPE_A: company name, OT columns, break column, location
_TYPE_A_TEXT = """
נ.ע. הנשר כח אדם בע"מ
תאריך  יום  מיקום  כניסה  יציאה  הפסקה  סה"כ  100%  125%  150%  שבת
01/01/24 יום ראשון מפעל 08:00 17:00 00:30 8.5 8.0 0.5 0.0 0.0
נסיעות 350
"""

# Heavily TYPE_B: work-days counter, monthly hours, hourly rate, total payment
_TYPE_B_TEXT = """
סה"כ ימי עבודה לחודש   22
סה"כ שעות חודשיות      198.0
תעריף שעתי             35.50
סה"כ לתשלום            7029.0
| 01/01/24 | ראשון | 08:00 | 17:00 | 9.0
"""

# Balanced: one strong keyword from each side — result depends on totals
# but we can guarantee LowConfidenceError by using a threshold=1.0
_BALANCED_TEXT = "125% 150% ימי עבודה שעות חודשיות"

_EMPTY_TEXT = ""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestClassifier:
    def test_type_a_text_classified_as_type_a(self):
        clf = Classifier(confidence_threshold=0.1)
        result = clf.classify(_TYPE_A_TEXT)
        assert result.report_type == "TYPE_A"

    def test_type_b_text_classified_as_type_b(self):
        clf = Classifier(confidence_threshold=0.1)
        result = clf.classify(_TYPE_B_TEXT)
        assert result.report_type == "TYPE_B"

    def test_type_a_confidence_above_threshold(self):
        clf = Classifier(confidence_threshold=0.1)
        result = clf.classify(_TYPE_A_TEXT)
        assert result.confidence >= 0.1

    def test_type_b_scores_higher_than_a_for_type_b_text(self):
        clf = Classifier(confidence_threshold=0.1)
        result = clf.classify(_TYPE_B_TEXT)
        assert result.score_b > result.score_a

    def test_empty_text_raises_low_confidence(self):
        clf = Classifier()
        with pytest.raises(LowConfidenceError):
            clf.classify(_EMPTY_TEXT)

    def test_low_confidence_error_carries_scores(self):
        clf = Classifier()
        with pytest.raises(LowConfidenceError) as exc_info:
            clf.classify(_EMPTY_TEXT)
        err = exc_info.value
        assert err.score_a == 0.0
        assert err.score_b == 0.0

    def test_threshold_above_actual_confidence_raises(self):
        """Use balanced text so confidence is < 1.0, then set threshold above it."""
        # This text has keywords from both sides → confidence < 1.0
        balanced = "125% 150% שבת נסיעות ימי עבודה שעות חודשיות תעריף שעתי"
        clf = Classifier(confidence_threshold=0.0)
        result = clf.classify(balanced)
        # Now set threshold higher than the actual confidence
        clf_high = Classifier(confidence_threshold=result.confidence + 0.01)
        with pytest.raises(LowConfidenceError):
            clf_high.classify(balanced)

    def test_threshold_0_never_raises_for_nonempty_signal(self):
        clf = Classifier(confidence_threshold=0.0)
        result = clf.classify(_TYPE_A_TEXT)
        assert result.report_type in ("TYPE_A", "TYPE_B")

    def test_result_scores_are_non_negative(self):
        clf = Classifier(confidence_threshold=0.0)
        result = clf.classify(_TYPE_A_TEXT)
        assert result.score_a >= 0
        assert result.score_b >= 0

    def test_result_confidence_in_0_1(self):
        clf = Classifier(confidence_threshold=0.0)
        result = clf.classify(_TYPE_A_TEXT)
        assert 0.0 <= result.confidence <= 1.0


class TestClassificationResult:
    def _make_result(self, rtype="TYPE_A", sa=5.0, sb=1.0, conf=0.67):
        return ClassificationResult(
            report_type=rtype, score_a=sa, score_b=sb, confidence=conf
        )

    def test_str_contains_type(self):
        r = self._make_result()
        assert "TYPE_A" in str(r)

    def test_str_contains_confidence(self):
        r = self._make_result()
        assert "confidence" in str(r).lower()

    def test_fields_stored(self):
        r = self._make_result("TYPE_B", 1.0, 5.0, 0.67)
        assert r.report_type == "TYPE_B"
        assert r.score_a == 1.0
        assert r.score_b == 5.0
        assert r.confidence == pytest.approx(0.67)
