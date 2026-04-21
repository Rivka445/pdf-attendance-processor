# ===== שלב 2: סיווג סוג הדוח =====
# מקבל את רשימת המילים עם מיקום (פלט של extract_words)
# ומחזיר "A" או "B" לפי מבנה ויזואלי של הדף - ללא תלות בעברית.
#
# הלוגיקה:
#   Type A: יש עמודות 100%/125%/150% בחלק העליון של הדף (y < 25%)
#            → הטבלה הראשית למעלה, סיכום למטה
#   Type B: אין עמודות אחוז, השעות מתחילות נמוך בדף (y > 25%)
#            → סיכום למעלה, טבלה ראשית למטה

import re

# תבנית לזיהוי עמודות אחוז: 100%, 125%, 150%
PCT_RE = re.compile(r'^1[02][05]%')

# תבנית לזיהוי שעות: H:MM או HH:MM
TIME_RE = re.compile(r'^\d{1,2}:\d{2}$')


def classify_document(words: list[dict]) -> str:
    """
    מסווג דוח נוכחות ל-A או B לפי מבנה ויזואלי.

    words: רשימת { text, x, y } מ-extract_words()
    מחזיר: "A", "B", או "UNKNOWN"
    """
    if not words:
        return "UNKNOWN"

    # גובה הדף = ה-y המקסימלי שנמצא
    img_h = max(w["y"] for w in words) or 1

    # בדיקה ראשונה: האם יש עמודות 100%/125% בחלק העליון (25% ראשונים של הדף)
    pct_words_top = [
        w for w in words
        if PCT_RE.match(w["text"]) and (w["y"] / img_h) < 0.25
    ]
    if pct_words_top:
        return "A"

    # בדיקה שנייה: האם השעות מתחילות נמוך בדף (סיכום למעלה = Type B)
    time_words = [w for w in words if TIME_RE.match(w["text"])]
    if time_words:
        first_time_y = min(w["y"] / img_h for w in time_words)
        if first_time_y > 0.25:
            return "B"

    return "UNKNOWN"
