"""
ingestion/pdf_extractor.py
==========================
Converts a scanned PDF into clean, normalised text ready for classification
and parsing.

Pipeline (all three stages live here):
  1. PDF → images          fitz renders each page at the configured DPI.
  2. Images → raw text     pytesseract OCRs each page image.
  3. Raw text → clean text A 7-step normalisation pass fixes unicode issues,
                            OCR substitutions, whitespace, and noise lines.

Public surface:
  PDFExtractorConfig  — immutable settings (dpi, lang, tesseract paths …)
  PDFExtractor        — single method: extract(pdf_path) → str

Dependency injection:
  Pass a ``PDFExtractorConfig`` to ``PDFExtractor.__init__`` to override
  any default (dpi, lang, oem, psm, tesseract_cmd).
"""

from __future__ import annotations

import io
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import fitz          # PyMuPDF
import pytesseract
from PIL import Image

from domain.errors import ExtractionError, OCRError, PDFOpenError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PDFExtractorConfig:
    """
    All tuneable knobs for the extraction pipeline.

    Attributes:
        dpi:            Rendering resolution.  300 is standard for OCR.
        lang:           Tesseract language string, e.g. ``"heb+eng"``.
        oem:            OCR Engine Mode (3 = LSTM default).
        psm:            Page Segmentation Mode (6 = single uniform block).
        tesseract_cmd:  Absolute path to the tesseract executable, or ``None``
                        to rely on the system PATH.
    """
    dpi:           int   = 300
    lang:          str   = "heb+eng"
    oem:           int   = 3
    psm:           int   = 6
    tesseract_cmd: str | None = None


# ---------------------------------------------------------------------------
# Public extractor
# ---------------------------------------------------------------------------

class PDFExtractor:
    """
    Converts a scanned-PDF file into a single normalised text string.

    Usage::

        config    = PDFExtractorConfig(dpi=300, lang="heb+eng")
        extractor = PDFExtractor(config)
        text      = extractor.extract("reports/january.pdf")
    """

    def __init__(self, config: PDFExtractorConfig | None = None) -> None:
        self._cfg = config or PDFExtractorConfig()
        if self._cfg.tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self._cfg.tesseract_cmd

    # ── Public API ──────────────────────────────────────────────────────────

    def extract(self, pdf_path: str | Path) -> str:
        """
        Full pipeline: PDF file → normalised text.

        Args:
            pdf_path: Path to the input PDF (single-page).

        Returns:
            A single string containing the normalised text of the page.

        Raises:
            PDFOpenError: If fitz cannot open the file.
            OCRError:     If tesseract fails on the page.
        """
        path          = Path(pdf_path)
        custom_config = f"--oem {self._cfg.oem} --psm {self._cfg.psm}"

        try:
            doc = fitz.open(str(path))
        except Exception as exc:
            logger.error("PDFExtractor: cannot open PDF  path=%s  reason=%s", path, exc)
            raise PDFOpenError(path, reason=str(exc)) from exc

        with doc:
            page = doc[0]
            mat  = fitz.Matrix(self._cfg.dpi / 72, self._cfg.dpi / 72)
            pix  = page.get_pixmap(matrix=mat)
            img  = Image.open(io.BytesIO(pix.tobytes("png")))
            try:
                raw = pytesseract.image_to_string(
                    img,
                    lang=self._cfg.lang,
                    config=custom_config,
                )
            except Exception as exc:
                logger.error("PDFExtractor: OCR failed  path=%s  reason=%s", path, exc)
                raise OCRError(path, page_index=0, reason=str(exc)) from exc

        text = _normalize(raw)
        return text


# ---------------------------------------------------------------------------
# Stage 3: normalisation pipeline (module-private)
# ---------------------------------------------------------------------------

# Common single-character OCR errors in Hebrew + numeric contexts, applied
# as anchored regex replacements only where the character is surrounded by digits.
_OCR_RE: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?<=\d)O(?=\d)"), "0"),   # digit-O → 0
    (re.compile(r"(?<=\d)l(?=\d)"), "1"),   # lone l   → 1
    (re.compile(r"(?<=\d)\|(?=\d)"), "1"),  # pipe     → 1
]

_TIME_SEP_RE    = re.compile(r"(\d{1,2})[.,;](\d{2})(?=\s|$)")
_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_MULTI_NL_RE    = re.compile(r"\n{3,}")
_RTL_CHARS_RE   = re.compile(r"[\u200e\u200f\u202a-\u202e\u2066-\u2069]")
_SHEKEL_RE      = re.compile(r"\u20aa")

# Patterns that mark artefact lines produced by tesseract on borders/headers
_NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^[-=_]{4,}$"),       # horizontal rules
    re.compile(r"^\s*\|\s*\|\s*$"),   # empty table borders
    re.compile(r"^\s*[●•·]\s*$"),     # lone bullet
]


def _normalize(raw: str) -> str:
    """Seven-step normalisation: returns clean, analysis-ready text."""
    # 1. Unicode NFC + null bytes + RTL direction marks + shekel sign
    text = unicodedata.normalize("NFC", raw).replace("\x00", "")
    text = _RTL_CHARS_RE.sub("", text)
    text = _SHEKEL_RE.sub("0", text)

    # 2. OCR character substitutions (digits context) + curly quotes
    for pattern, replacement in _OCR_RE:
        text = pattern.sub(replacement, text)
    text = (text.replace("\u2018", "'").replace("\u2019", "'")
                .replace("\u201c", '"').replace("\u201d", '"'))

    # 3. Normalise HH,MM / HH.MM / HH;MM → HH:MM
    text = _TIME_SEP_RE.sub(r"\1:\2", text)

    # 4. Collapse runs of spaces/tabs; collapse 3+ blank lines to 2
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _MULTI_NL_RE.sub("\n\n", text)

    # 5. Drop blank lines
    text = "\n".join(line for line in text.splitlines() if line.strip())

    # 6. Strip tesseract border/header noise lines
    text = "\n".join(
        line for line in text.splitlines()
        if not any(p.match(line.strip()) for p in _NOISE_PATTERNS)
    )
    return text
