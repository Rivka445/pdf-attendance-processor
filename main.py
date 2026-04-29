"""
main.py - pipeline runtime
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "attendance_processor"))

from attendance_processor.container import AppContainer, AppConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


def run(input_pdf: Path, output_dir: Path | None = None, container: AppContainer | None = None) -> None:
    container  = container or AppContainer(AppConfig(
        tesseract_cmd=r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    ))
    output_dir = output_dir or input_pdf.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Extracting text ...")
    text = container.extractor.extract(input_pdf)

    logger.info("Classifying report type ...")
    result = container.classifier.classify(text)
    logger.info("Type: %s  (confidence=%.2f)", result.report_type, result.confidence)

    logger.info("Parsing rows ...")
    report = container.parser_factory.get_parser(result.report_type).parse(
        text, source_file=str(input_pdf)
    )
    logger.info("Parsed %d rows", len(report.rows))

    logger.info("Transforming ...")
    report = container.transformation_service.transform(report)

    logger.info("Rendering ...")
    for renderer in container.renderers:
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