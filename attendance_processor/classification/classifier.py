"""
classification/classifier.py
============================
Classifies a normalised OCR text string as "TYPE_A", "TYPE_B", or "UNKNOWN".

  1. Each type has a list of (compiled_pattern, weight) pairs.
  2. _score() sums hit-count × weight for one type.
  3. Classifier.classify() picks the winner or raises LowConfidenceError.

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

from domain.errors import LowConfidenceError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keyword patterns  — (compiled regex, weight)
# ---------------------------------------------------------------------------

# TYPE_A signals: 125%/150% overtime columns are unique to this layout.
_TYPE_A: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"125\s*%", re.IGNORECASE), 2.0),
    (re.compile(r"150\s*%", re.IGNORECASE), 2.0),
]

# TYPE_B signals: work-day counter and monthly hours header.
_TYPE_B: list[tuple[re.Pattern[str], float]] = [
    (re.compile(r"עבודה\s+לחודש",  re.IGNORECASE), 2.5),
    (re.compile(r"שעות\s+חודשיות", re.IGNORECASE), 3.0),
]


def _score(text: str, patterns: list[tuple[re.Pattern[str], float]]) -> float:
    return sum(weight * len(p.findall(text)) for p, weight in patterns)


# ---------------------------------------------------------------------------
# Result + Classifier
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

    def classify(self, text: str) -> ClassificationResult:
        """
        Args:
            text: Normalised OCR text (output of ``PDFExtractor.extract``).

        Returns:
            :class:`ClassificationResult` with the winning type and scores.

        Raises:
            LowConfidenceError: If the winning score does not exceed the
                                threshold.
        """
        score_a = _score(text, _TYPE_A)
        score_b = _score(text, _TYPE_B)
        total   = score_a + score_b

        if total == 0:
            logger.warning("no keyword hits — result=UNKNOWN")
            raise LowConfidenceError(
                score_a=0.0, score_b=0.0, confidence=0.0, threshold=self._threshold
            )

        confidence = abs(score_a - score_b) / total

        if confidence < self._threshold:
            logger.warning(
                "low confidence %.2f%% < threshold %.2f%% — result=UNKNOWN",
                confidence * 100, self._threshold * 100,
            )
            raise LowConfidenceError(
                score_a=score_a,
                score_b=score_b,
                confidence=confidence,
                threshold=self._threshold,
            )

        return ClassificationResult(
            report_type="TYPE_A" if score_a >= score_b else "TYPE_B",
            score_a=score_a,
            score_b=score_b,
            confidence=confidence,
        )
