import numpy as np
from pdf2image import convert_from_path
import pytesseract

from ocr.preprocess import preprocess_image

POPPLER_PATH = r"C:/Users/user1/Downloads/Release-25.12.0-0/poppler-25.12.0/Library/bin"

pytesseract.pytesseract.tesseract_cmd = r"C:/Program Files/Tesseract-OCR/tesseract.exe"


def extract_text(file_path: str) -> str:
    img = convert_from_path(file_path, poppler_path=POPPLER_PATH)[0]
    img_np = np.array(img)

    clean_img = preprocess_image(img_np)

    text = pytesseract.image_to_string(
        clean_img,
        lang="heb+eng",
        config="--oem 3 --psm 6"
    )

    return text