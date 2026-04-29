"""
cli.py
======
Command-line interface using argparse.

Intentionally thin: it only parses arguments and calls app.process_pdf().
No business logic lives here.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

_DEFAULT_TESSERACT = os.environ.get(
    "TESSERACT_CMD",
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
)

sys.path.insert(0, str(Path(__file__).parent / "attendance_processor"))
sys.path.insert(0, str(Path(__file__).parent))

from attendance_processor.app import process_pdf
from attendance_processor.generation.html_renderer import HtmlRenderer
from attendance_processor.generation.excel_renderer import ExcelRenderer
from attendance_processor.generation.pdf_renderer import PdfRenderer


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="attendance-report",
        description="Generate a logically valid variation of an attendance report PDF.",
    )
    p.add_argument(
        "input",
        type=Path,
        nargs="+",
        help="One or more input PDF paths.",
    )
    p.add_argument(
        "-o", "--output-dir",
        type=Path,
        default=Path("output"),
        help="Directory for output files (default: ./output).",
    )
    p.add_argument(
        "--formats",
        nargs="+",
        choices=["html", "excel", "pdf"],
        default=["html", "excel", "pdf"],
        metavar="FMT",
        help="Output formats: html excel pdf (default: html excel).",
    )
    p.add_argument(
        "--no-transform",
        action="store_true",
        help="Skip the time-jitter transformation step.",
    )
    p.add_argument(
        "--threshold",
        type=float,
        default=0.25,
        metavar="FLOAT",
        help="Classifier confidence threshold 0–1 (default: 0.25).",
    )
    p.add_argument(
        "--tesseract",
        default=_DEFAULT_TESSERACT,
        metavar="PATH",
        help="Path to the tesseract executable.",
    )
    p.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable DEBUG logging.",
    )
    p.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="Suppress INFO messages (warnings and errors only).",
    )
    return p


_RENDERER_MAP = {
    "html":  HtmlRenderer,
    "excel": ExcelRenderer,
    "pdf":   PdfRenderer,
}


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.quiet:
        level = logging.WARNING
    elif args.verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        level=level,
    )

    renderers = [_RENDERER_MAP[fmt]() for fmt in args.formats]

    exit_code = 0
    for pdf_path in args.input:
        result = process_pdf(
            input_path=pdf_path,
            output_dir=args.output_dir,
            renderers=renderers,
            tesseract=args.tesseract,
            transform=not args.no_transform,
            threshold=args.threshold,
        )
        if result.success:
            paths = ', '.join(str(p) for p in result.output_paths)
            print(f"[OK]   {pdf_path.name}  ->  {paths}")
        else:
            errors = '; '.join(result.errors)
            print(f"[FAIL] {pdf_path.name}: {errors}", file=sys.stderr)
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
