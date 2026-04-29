"""
main.py - pipeline runtime
"""

import sys
import logging
from pathlib import Path

# Mirror the same sys.path setup used by conftest.py so that intra-package
# bare imports (e.g. "from domain.models import ...") resolve correctly.
sys.path.insert(0, str(Path(__file__).parent / "attendance_processor"))

from attendance_processor.ingestion.pdf_extractor import PDFExtractor, PDFExtractorConfig
from attendance_processor.classification.classifier import Classifier
from attendance_processor.parsers.parser_factory import ParserFactory
from attendance_processor.transformation.service import TransformationService
from attendance_processor.generation.html_renderer import HtmlRenderer
from attendance_processor.generation.pdf_renderer import PdfRenderer
from attendance_processor.generation.excel_renderer import ExcelRenderer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def run(input_pdf: Path, output_dir: Path | None = None) -> None:
    output_dir = output_dir or input_pdf.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Extracting text ...")
    text = PDFExtractor(config=PDFExtractorConfig(
        tesseract_cmd=r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    )).extract(input_pdf)

    logger.info("Classifying report type ...")
    result = Classifier().classify(text)
    logger.info("Type: %s  (confidence=%.2f)", result.report_type, result.confidence)

    logger.info("Parsing rows ...")
    report = ParserFactory().get_parser(result.report_type).parse(
        text, source_file=str(input_pdf)
    )
    logger.info("Parsed %d rows", len(report.rows))

    logger.info("Transforming ...")
    report = TransformationService().transform(report)

    logger.info("Rendering ...")
    for renderer in (HtmlRenderer(), ExcelRenderer(), PdfRenderer()):
        out = renderer.render(report, output_dir)
        logger.info("  -> %s", out)

    logger.info("Done.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <input_pdf> [output_dir]", file=sys.stderr)
        sys.exit(1)

    run(
        input_pdf=Path(sys.argv[1]),
        output_dir=Path(sys.argv[2]) if len(sys.argv) > 2 else None,
    )