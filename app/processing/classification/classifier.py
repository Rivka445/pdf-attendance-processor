import re

PCT_RE  = re.compile(r'^1[02][05]%')
TIME_RE = re.compile(r'^\d{1,2}:\d{2}$')


def classify_document(words: list[dict]) -> str:
    """
    Classify a document as Type A or Type B based on visual structure.

    Type A: percentage columns (100%/125%/150%) appear in the top 25% of the page.
    Type B: no percentage columns, and time values start below the top 25%.
    Returns 'A', 'B', or 'UNKNOWN'.
    """
    if not words:
        return "UNKNOWN"
    img_h = max(w["y"] for w in words) or 1
    pct_words_top = [w for w in words if PCT_RE.match(w["text"]) and (w["y"] / img_h) < 0.25]
    if pct_words_top:
        return "A"
    time_words = [w for w in words if TIME_RE.match(w["text"])]
    if time_words:
        first_time_y = min(w["y"] / img_h for w in time_words)
        if first_time_y > 0.25:
            return "B"
    return "UNKNOWN"
