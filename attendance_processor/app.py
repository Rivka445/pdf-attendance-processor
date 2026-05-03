"""
attendance_processor/app.py
============================
Application facade — the single entry point for the full pipeline.

process_pdf() orchestrates: extract → classify → parse → transform → render.
All business logic lives here; cli.py only parses arguments and calls this.
Services are wired through AppContainer (DI) rather than constructed inline.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from attendance_processor.container import AppConfig, AppContainer

logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    success:      bool
    output_paths: list[Path] = field(default_factory=list)
    errors:       list[str]  = field(default_factory=list)


def process_pdf(
    input_path:  Path,
    output_dir:  Path,
    renderers:   list,
    tesseract:   str   = AppConfig.tesseract_cmd,
    transform:   bool  = True,
    threshold:   float = 0.25,
) -> ProcessResult:
    """
    Run the full attendance-report pipeline for one PDF.

    Parameters
    ----------
    input_path: Path to the source PDF.
    output_dir: Directory where output files are written.
    renderers:  List of renderer instances (HtmlRenderer, ExcelRenderer, …).
    tesseract:  Path to the tesseract executable.
    transform:  Whether to apply the time-jitter transformation step.
    threshold:  Classifier confidence threshold (0–1).

    Returns
    -------
    ProcessResult with success flag, output paths, and any error messages.
    """
    container = AppContainer(AppConfig(
        tesseract_cmd=tesseract,
        confidence_threshold=threshold,
    ))

    output_dir.mkdir(parents=True, exist_ok=True)
    result = ProcessResult(success=False)

    try:
        # 1. Extract
        logger.debug("Extracting: %s", input_path.name)
        text = container.extractor.extract(input_path)
        logger.debug("  %d chars extracted", len(text))

        # 2. Classify
        clf = container.classifier.classify(text)
        logger.debug("  Type: %s  (confidence=%.1f%%)",
                    clf.report_type, clf.confidence * 100)

        # 3. Parse
        report = container.parser_factory.get_parser(clf.report_type).parse(
            text, source_file=str(input_path)
        )
        logger.debug("  %d rows parsed", len(report.rows))

        # 4. Transform
        if transform:
            report = container.transformation_service.transform(report)
            logger.debug("  total_hours=%.2f", report.summary.total_hours or 0)

        # 5. Render
        for renderer in renderers:
            try:
                out = renderer.render(report, output_dir)
                result.output_paths.append(out)
                logger.debug("  [%s] -> %s", type(renderer).__name__, out)
            except Exception as exc:
                msg = f"{type(renderer).__name__} failed: {exc}"
                logger.warning("  %s", msg)
                result.errors.append(msg)

        result.success = True

    except Exception as exc:
        logger.error("Pipeline failed for %s: %s", input_path.name, exc)
        result.errors.append(str(exc))

    return result
