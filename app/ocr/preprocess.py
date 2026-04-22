import cv2
import numpy as np


def preprocess_image(img_np: np.ndarray) -> np.ndarray:
    """
    Convert an RGB image to grayscale and upscale by 2.5x
    to improve Tesseract OCR accuracy on small text.
    """
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2.5, fy=2.5)
    return gray
