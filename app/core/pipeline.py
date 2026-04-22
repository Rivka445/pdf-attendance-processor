import os
from app.models.report_meta import ReportMeta
from app.core.exceptions import (
    OcrError, ClassificationError, ParsingError,
    RenderingError, UnsupportedFormatError,
)
from app.core.logger import get_logger
from app.core.container import Container

log = get_logger("pipeline")


def run_pipeline(
    input_path: str,
    n: int = 3,
    formats: list[str] = None,
    output_dir: str = "export",
    container: Container = None,
) -> list[str]:
    """
    Process a single PDF file and produce n variants in the requested formats.
    Returns a list of all output file paths created.
    Raises typed exceptions on OCR, classification, parsing, or rendering failure.
    """
    if container is None:
        container = Container()
    if formats is None:
        formats = ["pdf", "excel", "html"]

    for fmt in formats:
        if container.get_renderer(fmt) is None:
            raise UnsupportedFormatError(f"Unsupported format: '{fmt}'")

    base_name = os.path.splitext(os.path.basename(input_path))[0]
    log.info("Starting pipeline for: %s", input_path)

    try:
        words = container.extract_words(input_path)
        if not words:
            raise OcrError(f"No words extracted from {input_path}")
        log.info("[%s] OCR extracted %d words", base_name, len(words))
    except OcrError:
        raise
    except Exception as e:
        raise OcrError(f"OCR failed for {input_path}") from e

    try:
        doc_type = container.classify(words)
        if doc_type == "UNKNOWN":
            raise ClassificationError(f"Could not classify: {input_path}")
        handler = container.get_handler(doc_type)
        if handler is None:
            raise ClassificationError(f"No handler registered for type '{doc_type}'")
        log.info("[%s] Classified as Type %s", base_name, doc_type)
    except ClassificationError:
        raise
    except Exception as e:
        raise ClassificationError(f"Classification failed for {input_path}") from e

    try:
        parser_input = handler.prepare_input(words, container)
        source = handler.parser.parse(parser_input)
        meta   = handler.parser.extract_meta(parser_input, seed=base_name)
        log.info("[%s] Parsed: %d lines | month=%s/%s start=%s end=%s",
                 base_name, len(source.lines),
                 meta.month, meta.year, meta.typical_start, meta.typical_end)
    except Exception as e:
        raise ParsingError(f"Parsing failed for {input_path}") from e

    created = []
    for i in range(1, n + 1):
        variant_meta = ReportMeta(
            doc_type=meta.doc_type,
            month=meta.month,
            year=meta.year,
            work_days=meta.work_days,
            typical_start=meta.typical_start,
            typical_end=meta.typical_end,
            has_overtime=meta.has_overtime,
            seed=f"{base_name}_v{i}",
        )

        try:
            report = handler.rules.apply(variant_meta, source)
            log.debug("[%s] v%d: %d lines", base_name, i, len(report.lines))
        except Exception as e:
            raise ParsingError(f"Rules failed for {input_path} v{i}") from e

        variant_dir = os.path.join(output_dir, base_name)
        for fmt in formats:
            ext = {"pdf": "pdf", "excel": "xlsx", "html": "html"}.get(fmt, fmt)
            out_path = os.path.join(variant_dir, f"v{i}.{ext}")
            try:
                container.get_renderer(fmt).render(report, out_path)
                created.append(out_path)
                log.info("  -> %s", out_path)
            except PermissionError:
                log.warning("  [SKIP] %s - file is open", out_path)
            except Exception as e:
                raise RenderingError(f"Rendering failed: {out_path}") from e

    log.info("[%s] Done. Created %d files.", base_name, len(created))
    return created
