# ===== שלב 1: OCR - חילוץ מילים מ-PDF =====
# הקובץ הזה אחראי על:
#   - המרת PDF לתמונה
#   - עיבוד מקדים של התמונה (preprocess)
#   - הרצת Tesseract OCR לחילוץ מילים עם מיקום x,y
#   - קיבוץ המילים לשורות לפי קרבת Y

import numpy as np
from pdf2image import convert_from_path
import pytesseract

from ocr.preprocess import preprocess_image

POPPLER_PATH = r"C:/Users/user1/Downloads/Release-25.12.0-0/poppler-25.12.0/Library/bin"
pytesseract.pytesseract.tesseract_cmd = r"C:/Program Files/Tesseract-OCR/tesseract.exe"


def extract_words(file_path: str) -> list[dict]:
    """
    ממיר PDF לתמונה ומחלץ מילים עם מיקום פיקסלים.
    מחזיר רשימה של: { text, x, y }
    המיקום x,y משמש גם לסיווג (classifier) וגם לבניית שורות (build_lines).
    """
    img = convert_from_path(file_path, poppler_path=POPPLER_PATH)[0]
    img_np = np.array(img)

    # עיבוד מקדים: המרה לגווני אפור + הגדלה לשיפור דיוק OCR
    clean_img = preprocess_image(img_np)

    # image_to_data מחזיר dict עם text, left, top לכל מילה
    data = pytesseract.image_to_data(
        clean_img,
        lang="heb+eng",
        config="--oem 3 --psm 6",
        output_type=pytesseract.Output.DICT
    )

    words = []
    for i in range(len(data["text"])):
        text = data["text"][i].strip()
        if not text:
            continue
        words.append({
            "text": text,
            "x": data["left"][i],
            "y": data["top"][i]
        })

    return words


def build_lines(words: list[dict], y_threshold: int = 10) -> list[str]:
    """
    מקבץ מילים לשורות לפי קרבת ציר Y.
    y_threshold: כמה פיקסלים הפרש מקסימלי בין מילים באותה שורה.
    בתוך כל שורה ממיין לפי X (שמאל לימין).
    מחזיר רשימת מחרוזות - שורה אחת לכל רכיב.
    """
    lines = {}
    for w in words:
        y_bucket = w["y"] // y_threshold
        lines.setdefault(y_bucket, []).append(w)

    result = []
    for _, ws in sorted(lines.items()):
        ws_sorted = sorted(ws, key=lambda x: x["x"])
        line = " ".join(w["text"] for w in ws_sorted)
        result.append(line)

    return result


def extract_text(file_path: str) -> list[str]:
    """
    פונקציית עזר: מחלץ מילים ובונה שורות בקריאה אחת.
    מחזיר רשימת שורות טקסט (ללא מיקום).
    """
    words = extract_words(file_path)
    return build_lines(words)
