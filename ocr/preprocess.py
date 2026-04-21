# ===== עיבוד מקדים של תמונה לפני OCR =====
# מטרה: לשפר את איכות הקלט ל-Tesseract
#   - המרה לגווני אפור (grayscale) - Tesseract עובד טוב יותר על תמונות חד-ערוציות
#   - הגדלה x2.5 - מגדילה פרטים קטנים ומשפרת זיהוי תווים קטנים

import cv2
import numpy as np


def preprocess_image(img_np: np.ndarray) -> np.ndarray:
    """
    מקבל תמונה כ-numpy array (RGB) ומחזיר תמונה מעובדת (grayscale מוגדל).
    """
    gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2.5, fy=2.5)
    return gray
