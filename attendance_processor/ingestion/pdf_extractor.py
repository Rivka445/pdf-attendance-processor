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

from errors import ExtractionError, OCRError, PDFOpenError

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
        logger.debug(
            "PDFExtractor initialised: dpi=%d lang=%s oem=%d psm=%d",
            self._cfg.dpi, self._cfg.lang, self._cfg.oem, self._cfg.psm,
        )

    # ── Public API ──────────────────────────────────────────────────────────

    def extract(self, pdf_path: str | Path) -> str:
        """
        Full pipeline: PDF file → normalised text.

        Args:
            pdf_path: Path to the input PDF.

        Returns:
            A single string containing the normalised text of every page,
            pages separated by form-feed (``\\f``).

        Raises:
            PDFOpenError: If fitz cannot open the file.
            OCRError:     If tesseract fails on a page.
        """
        path = Path(pdf_path)
        logger.info("PDFExtractor.extract: starting  path=%s", path)
        pages = self._pdf_to_pages(path)
        raw   = "\f".join(pages)
        text  = _normalize(raw)
        logger.info(
            "PDFExtractor.extract: done  pages=%d chars=%d", len(pages), len(text)
        )
        return text

    # ── Stage 1 + 2: PDF → text pages ───────────────────────────────────────

    def _pdf_to_pages(self, pdf_path: Path) -> list[str]:
        """Render each PDF page to an image and OCR it."""
        custom_config = f"--oem {self._cfg.oem} --psm {self._cfg.psm}"
        pages: list[str] = []

        try:
            doc = fitz.open(str(pdf_path))
        except Exception as exc:
            logger.error("PDFExtractor: cannot open PDF  path=%s  reason=%s", pdf_path, exc)
            raise PDFOpenError(pdf_path, reason=str(exc)) from exc

        with doc:
            total = len(doc)
            logger.debug("PDFExtractor: opened PDF  pages=%d  path=%s", total, pdf_path)
            for idx, page in enumerate(doc):
                logger.debug("PDFExtractor: OCR page %d/%d", idx + 1, total)
                mat = fitz.Matrix(self._cfg.dpi / 72, self._cfg.dpi / 72)
                pix = page.get_pixmap(matrix=mat)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                try:
                    text = pytesseract.image_to_string(
                        img,
                        lang=self._cfg.lang,
                        config=custom_config,
                    )
                except Exception as exc:
                    logger.error(
                        "PDFExtractor: OCR failed  path=%s page=%d reason=%s",
                        pdf_path, idx, exc,
                    )
                    raise OCRError(pdf_path, page_index=idx, reason=str(exc)) from exc
                pages.append(text)

        return pages


# ---------------------------------------------------------------------------
# Stage 3: normalisation pipeline (module-private)
# ---------------------------------------------------------------------------

def _normalize(raw: str) -> str:
    """Seven-step normalisation: returns clean, analysis-ready text."""
    text = raw
    text = _fix_unicode(text)
    text = _remove_null_bytes(text)
    text = _fix_ocr_substitutions(text)
    text = _normalize_time_separators(text)
    text = _collapse_whitespace(text)
    text = _remove_empty_lines(text)
    text = _strip_header_footer_noise(text)
    return text


# — step helpers ─────────────────────────────────────────────────────────────

def _fix_unicode(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def _remove_null_bytes(text: str) -> str:
    return text.replace("\x00", "")


# Common single-character OCR errors in Hebrew + numeric contexts, applied
# as anchored regex replacements only where the character is surrounded by digits.
_OCR_RE: list[tuple[re.Pattern[str], str]] = [
    # digit-O: "O" surrounded by digits → "0"
    (re.compile(r"(?<=\d)O(?=\d)"), "0"),
    # lone lowercase l between digits → 1
    (re.compile(r"(?<=\d)l(?=\d)"), "1"),
    # pipe between digits → 1
    (re.compile(r"(?<=\d)\|(?=\d)"), "1"),
]


def _fix_ocr_substitutions(text: str) -> str:
    for pattern, replacement in _OCR_RE:
        text = pattern.sub(replacement, text)
    # Straight-quote normalisation
    text = text.replace("\u2018", "'").replace("\u2019", "'")
    text = text.replace("\u201c", '"').replace("\u201d", '"')
    return text


_TIME_SEP_RE = re.compile(r"(\d{1,2})[.,;](\d{2})(?=\s|$)")


def _normalize_time_separators(text: str) -> str:
    """Replace , . ; used as HH:MM separator with :"""
    return _TIME_SEP_RE.sub(r"\1:\2", text)


_MULTI_SPACE_RE  = re.compile(r"[ \t]+")
_MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


def _collapse_whitespace(text: str) -> str:
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _MULTI_NEWLINE_RE.sub("\n\n", text)
    return text


def _remove_empty_lines(text: str) -> str:
    lines = text.splitlines()
    return "\n".join(line for line in lines if line.strip())


# Patterns that mark artefact lines produced by tesseract on borders/headers
_NOISE_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^[-=_]{4,}$"),          # horizontal rules
    re.compile(r"^\s*\|\s*\|\s*$"),       # empty table borders
    re.compile(r"^\s*[●•·]\s*$"),         # lone bullet
]


def _strip_header_footer_noise(text: str) -> str:
    lines = text.splitlines()
    clean = [
        line for line in lines
        if not any(p.match(line.strip()) for p in _NOISE_PATTERNS)
    ]
    return "\n".join(clean)
