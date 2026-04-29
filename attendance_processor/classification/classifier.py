"""
classification/classifier.py
============================
Classifies a normalised OCR text string as "TYPE_A", "TYPE_B", or "UNKNOWN".

Two internal stages (both live in this file):
  1. Keyword scan   — regex-based pattern matching, one hit per keyword.
  2. Weighted score — sum hit weights per type, normalise to confidence.

Public surface:
  ClassificationResult  — frozen dataclass: report_type, confidence, scores
  Classifier            — single method: classify(text) → ClassificationResult

Dependency injection:
  Pass ``confidence_threshold`` to ``Classifier.__init__`` to override the
  default 0.25 cut-off without touching module-level constants.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import NamedTuple

from errors import LowConfidenceError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stage 1 – keyword definitions and scanner
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Keyword:
    key:            str
    pattern:        str
    weight:         float
    case_sensitive: bool = False


class _ScanHit(NamedTuple):
    key:    str
    count:  int
    weight: float


# TYPE_A signals: company name header, 125 %/150 % overtime columns, break,
# location column, Saturday, travel allowance.
_TYPE_A_KEYWORDS: tuple[_Keyword, ...] = (
    _Keyword("company_name",   r"חברת\s+(?:הניקיון|האבטחה|השמירה)", weight=3.0),
    _Keyword("col_125",        r"125\s*%",                            weight=2.0),
    _Keyword("col_150",        r"150\s*%",                            weight=2.0),
    _Keyword("break_col",      r"הפסקה",                              weight=1.5),
    _Keyword("location_col",   r"(?:אתר|סניף|מיקום)",                 weight=1.0),
    _Keyword("saturday_col",   r"שבת",                                weight=1.0),
    _Keyword("travel_col",     r"נסיעות",                             weight=1.0),
)

# TYPE_B signals: work-day counter, monthly hours, hourly rate, total payment,
# half-day.
_TYPE_B_KEYWORDS: tuple[_Keyword, ...] = (
    _Keyword("work_days",      r"ימי\s+עבודה",    weight=3.0),
    _Keyword("work_month",     r"עבודה\s+לחודש",  weight=2.5),  # catches noisy OCR
    _Keyword("monthly_hours",  r"שעות\s+חודשיות", weight=3.0),
    _Keyword("hourly_rate",    r"(?:תעריף|מחיר)\s+(?:שעתי|לשעה)", weight=2.0),
    _Keyword("total_payment",  r"סה\"כ\s+לתשלום", weight=2.0),
    _Keyword("half_day",       r"חצי\s+יום",       weight=1.0),
)

_TYPE_A_KEYS: frozenset[str] = frozenset(kw.key for kw in _TYPE_A_KEYWORDS)
_TYPE_B_KEYS: frozenset[str] = frozenset(kw.key for kw in _TYPE_B_KEYWORDS)


def _compile(keywords: tuple[_Keyword, ...]) -> dict[str, re.Pattern[str]]:
    return {
        kw.key: re.compile(
            kw.pattern,
            0 if kw.case_sensitive else re.IGNORECASE,
        )
        for kw in keywords
    }


_COMPILED: dict[str, re.Pattern[str]] = {
    **_compile(_TYPE_A_KEYWORDS),
    **_compile(_TYPE_B_KEYWORDS),
}
_ALL_KEYWORDS: tuple[_Keyword, ...] = _TYPE_A_KEYWORDS + _TYPE_B_KEYWORDS


def _scan(text: str) -> list[_ScanHit]:
    """Return one _ScanHit per keyword."""
    hits: list[_ScanHit] = []
    for kw in _ALL_KEYWORDS:
        matches = _COMPILED[kw.key].findall(text)
        count   = len(matches)
        hits.append(_ScanHit(key=kw.key, count=count, weight=kw.weight))
    return hits


# ---------------------------------------------------------------------------
# Stage 2 – scoring and result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ClassificationResult:
    """
    Output of the classifier.

    Attributes:
        report_type:  ``"TYPE_A"``, ``"TYPE_B"``, or ``"UNKNOWN"``.
        score_a:      Weighted keyword score for TYPE_A.
        score_b:      Weighted keyword score for TYPE_B.
        confidence:   Normalised score difference in [0, 1].
                      0.0 = tied / no signal, 1.0 = unambiguous.
    """
    report_type: str
    score_a:     float
    score_b:     float
    confidence:  float

    def __str__(self) -> str:
        return (
            f"ClassificationResult("
            f"type={self.report_type}, "
            f"score_a={self.score_a:.2f}, "
            f"score_b={self.score_b:.2f}, "
            f"confidence={self.confidence:.2%})"
        )


# ---------------------------------------------------------------------------
# Public classifier
# ---------------------------------------------------------------------------

class Classifier:
    """
    Classifies normalised OCR text as TYPE_A, TYPE_B, or UNKNOWN.

    Dependency injection
    --------------------
    ``confidence_threshold`` controls the minimum score difference ratio
    required to commit to a type; pass it at construction time::

        classifier = Classifier(confidence_threshold=0.35)
        result = classifier.classify(text)
    """

    def __init__(self, confidence_threshold: float = 0.25) -> None:
        self._threshold = confidence_threshold
        logger.debug("Classifier initialised: confidence_threshold=%.2f", confidence_threshold)

    def classify(self, text: str) -> ClassificationResult:
        """
        Args:
            text: Normalised OCR text (output of ``PDFExtractor.extract``).

        Returns:
            :class:`ClassificationResult` with the winning type and scores.

        Raises:
            LowConfidenceError: If the winning score does not exceed the
                                threshold (result.report_type will be UNKNOWN
                                but callers that need a hard failure can catch
                                this exception instead).
        """
        logger.debug("Classifier.classify: scanning text length=%d", len(text))
        hits    = _scan(text)
        score_a = sum(h.weight * h.count for h in hits if h.key in _TYPE_A_KEYS)
        score_b = sum(h.weight * h.count for h in hits if h.key in _TYPE_B_KEYS)
        total   = score_a + score_b

        logger.debug(
            "Classifier.classify: score_a=%.2f score_b=%.2f total=%.2f",
            score_a, score_b, total,
        )

        if total == 0:
            logger.warning("Classifier.classify: no keyword hits — result=UNKNOWN")
            raise LowConfidenceError(
                score_a=0.0, score_b=0.0, confidence=0.0, threshold=self._threshold
            )

        confidence = abs(score_a - score_b) / total

        if confidence < self._threshold:
            logger.warning(
                "Classifier.classify: low confidence %.2f%% < threshold %.2f%% — result=UNKNOWN",
                confidence * 100, self._threshold * 100,
            )
            raise LowConfidenceError(
                score_a=score_a,
                score_b=score_b,
                confidence=confidence,
                threshold=self._threshold,
            )

        report_type = "TYPE_A" if score_a >= score_b else "TYPE_B"
        logger.info(
            "Classifier.classify: result=%s confidence=%.2f%%",
            report_type, confidence * 100,
        )

        return ClassificationResult(
            report_type=report_type,
            score_a=score_a,
            score_b=score_b,
            confidence=confidence,
        )
