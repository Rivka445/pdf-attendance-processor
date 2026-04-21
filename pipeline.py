# ===== Pipeline =====
# זרימה מלאה: PDF קלט → OCR → סיווג → פרסור → Rules → N וריאציות פלט
#
# שימוש:
#   run_pipeline("pdf files/a_r_9.pdf", n=5, formats=["pdf","excel","html"])

import os
from ocr.extractor import extract_words, build_lines
from classification.classifier import classify_document
from parsing.parser_type_a import ParserA
from parsing.parser_type_b import ParserB
from rules.rules_type_a import generate_type_a
from rules.rules_type_b import generate_type_b
from rendering.pdf_renderer import PdfRenderer
from rendering.excel_renderer import ExcelRenderer
from rendering.html_renderer import HtmlRenderer
from models.report_meta import ReportMeta


def run_pipeline(
    input_path: str,
    n: int = 3,
    formats: list[str] = None,
    output_dir: str = "export",
) -> list[str]:
    """
    מעבד קובץ PDF אחד ומייצר N וריאציות בפורמטים הרצויים.

    input_path: נתיב לקובץ PDF מקורי
    n:          כמה וריאציות לייצר
    formats:    רשימת פורמטים ["pdf", "excel", "html"]
    output_dir: תיקיית פלט

    מחזיר: רשימת נתיבי קבצים שנוצרו
    """
    if formats is None:
        formats = ["pdf", "excel", "html"]

    # שלב 1: OCR
    words = extract_words(input_path)

    # שלב 2: סיווג
    doc_type = classify_document(words)
    if doc_type == "UNKNOWN":
        print(f"[WARN] Could not classify {input_path}")
        return []

    # שלב 3: חילוץ meta
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    if doc_type == "A":
        text = "\n".join(build_lines(words))
        meta = ParserA().extract_meta(text, seed=base_name)
    else:
        meta = ParserB().extract_meta(words, seed=base_name)

    print(f"[{base_name}] Type={doc_type} | {meta.month}/{meta.year} | "
          f"days={meta.work_days} | {meta.typical_start}-{meta.typical_end}")

    # שלב 4: N וריאציות
    renderers = _get_renderers(formats)
    created = []

    for i in range(1, n + 1):
        # seed שונה לכל וריאציה
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
        report = generate_type_a(variant_meta) if doc_type == "A" else generate_type_b(variant_meta)

        # שלב 6: rendering
        variant_dir = os.path.join(output_dir, base_name)
        for fmt, renderer in renderers.items():
            ext = {"pdf": "pdf", "excel": "xlsx", "html": "html"}[fmt]
            out_path = os.path.join(variant_dir, f"v{i}.{ext}")
            try:
                renderer.render(report, out_path)
                created.append(out_path)
                print(f"  -> {out_path}")
            except PermissionError:
                print(f"  [SKIP] {out_path} - file is open, close it and rerun")

    return created


def _get_renderers(formats: list[str]) -> dict:
    available = {
        "pdf": PdfRenderer(),
        "excel": ExcelRenderer(),
        "html": HtmlRenderer(),
    }
    return {f: available[f] for f in formats if f in available}
