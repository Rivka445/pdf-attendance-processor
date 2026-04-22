import numpy as np
from pdf2image import convert_from_path
import pytesseract
from app.ocr.preprocess import preprocess_image

POPPLER_PATH = r"C:/Users/user1/Downloads/Release-25.12.0-0/poppler-25.12.0/Library/bin"
pytesseract.pytesseract.tesseract_cmd = r"C:/Program Files/Tesseract-OCR/tesseract.exe"


def extract_words(file_path: str) -> list[dict]:
    """
    Convert the first page of a PDF to an image, run Tesseract OCR,
    and return a list of word dicts with keys: text, x, y.
    """
    img = convert_from_path(file_path, poppler_path=POPPLER_PATH)[0]
    img_np = np.array(img)
    clean_img = preprocess_image(img_np)
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
        words.append({"text": text, "x": data["left"][i], "y": data["top"][i]})
    return words


def build_lines(words: list[dict], y_threshold: int = 10) -> list[str]:
    """
    Group words into text lines by proximity on the Y axis.
    Words within y_threshold pixels of each other are merged into one line,
    sorted left-to-right by X position.
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
    """Convenience wrapper: extract words and return grouped text lines."""
    words = extract_words(file_path)
    return build_lines(words)
