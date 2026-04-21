# ===== Pipeline =====
import os
from models.report_meta import ReportMeta
from exceptions import (
    OcrError, ClassificationError, ParsingError,
    RenderingError, UnsupportedFormatError,
)
from logger import get_logger
from container import Container

log = get_logger("pipeline")


def run_pipeline(
    input_path: str,
    n: int = 3,
    formats: list[str] = None,
    output_dir: str = "export",
    container: Container = None,
) -> list[str]:
    """
    מעבד קובץ PDF אחד ומייצר N וריאציות.

    input_path: נתיב לקובץ PDF
    n:          מספר וריאציות
    formats:    ["pdf", "excel", "html"]
    output_dir: תיקיית פלט
    container:  DI container (ברירת מחדל: Container())
    """
    if container is None:
        container = Container()
    if formats is None:
        formats = ["pdf", "excel", "html"]

    # ולידציה של פורמטים
    for fmt in formats:
        if container.get_renderer(fmt) is None:
            raise UnsupportedFormatError(f"Unsupported format: '{fmt}'")

    base_name = os.path.splitext(os.path.basename(input_path))[0]
    log.info("Starting pipeline for: %s", input_path)

    # שלב 1: OCR
    try:
        words = container.extract_words(input_path)
        if not words:
            raise OcrError(f"No words extracted from {input_path}")
        log.info("[%s] OCR extracted %d words", base_name, len(words))
    except OcrError:
        raise
    except Exception as e:
        raise OcrError(f"OCR failed for {input_path}") from e

    # שלב 2: סיווג
    try:
        doc_type = container.classify(words)
        if doc_type == "UNKNOWN":
            raise ClassificationError(f"Could not classify: {input_path}")
        log.info("[%s] Classified as Type %s", base_name, doc_type)
    except ClassificationError:
        raise
    except Exception as e:
        raise ClassificationError(f"Classification failed for {input_path}") from e

    # שלב 3: פרסור meta
    try:
        if doc_type == "A":
            text = "\n".join(container.build_lines(words))
            meta = container.parser_a.extract_meta(text, seed=base_name)
        else:
            meta = container.parser_b.extract_meta(words, seed=base_name)
        log.info("[%s] Meta: month=%s/%s days=%s start=%s end=%s overtime=%s",
                 base_name, meta.month, meta.year, meta.work_days,
                 meta.typical_start, meta.typical_end, meta.has_overtime)
    except Exception as e:
        raise ParsingError(f"Parsing failed for {input_path}") from e

    # שלב 4: N וריאציות
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

        # שלב 5: יצירת דוח
        try:
            report = container.generate_a(variant_meta) if doc_type == "A" else container.generate_b(variant_meta)
            log.debug("[%s] v%d generated: %d lines", base_name, i, len(report.lines))
        except Exception as e:
            raise ParsingError(f"Rules generation failed for {input_path} v{i}") from e

        # שלב 6: rendering
        variant_dir = os.path.join(output_dir, base_name)
        for fmt in formats:
            ext = {"pdf": "pdf", "excel": "xlsx", "html": "html"}[fmt]
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
