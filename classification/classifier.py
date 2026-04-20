from rapidfuzz import fuzz


def match(text, keyword):
    return fuzz.partial_ratio(keyword, text) > 65


def _calc_score(text, keywords):
    return sum(
        match(text, kw.strip().lower())
        for kw in keywords
    )


def classify_document(text, config):
    score_a = _calc_score(text, config["type_a"]["keywords"])
    score_b = _calc_score(text, config["type_b"]["keywords"])

    if score_a == 0 and score_b == 0:
        return "UNKNOWN"

    return "A" if score_a > score_b else "B"