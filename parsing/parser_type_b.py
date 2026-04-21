# ===== פרסר לדוח Type B =====
# מבנה שורה בדוח B (עמודות לפי x):
#
#   RTL (n_r_5):  total | end_time | start_time | day | date   (date בימין, x גבוה)
#   LTR (n_r_10): total | start_time | end_time  | day | date   (date בשמאל, x נמוך)
#
# זיהוי כיוון: אם התאריכים נמצאים ב-x גבוה (>900) → RTL, אחרת LTR

import re
from collections import Counter
from models.type_b import TypeB
from models.line_b import LineB
from models.report_meta import ReportMeta

DATE_RE = re.compile(r'^\d{1,2}/\d{1,2}/\d{2,4}$')
TIME_RE = re.compile(r'^\d{1,2}:\d{2}$')
NUMBER_RE = re.compile(r'^\d+[\.:]\d+$')
OCR_3DIGIT_RE = re.compile(r'^\d{3,4}$')  # OCR שגוי: 350 → 3.50, 3550 → 3.50


class ParserB:

    def parse(self, words: list[dict]) -> TypeB:
        """
        מקבל רשימת { text, x, y } מ-extract_words.
        מקבץ לשורות לפי y, מזהה כיוון, ומפרסר כל שורה.
        """
        report = TypeB()

        rows = self._group_rows(words)
        if not rows:
            return report

        direction = self._detect_direction(rows)
        report.month = self._extract_month(rows)

        for row in rows:
            line = self._parse_row(row, direction)
            if line:
                report.lines.append(line)

        report.days = len(report.lines)
        report.total_hours = sum(l.total or 0 for l in report.lines)

        return report

    def extract_meta(self, words: list[dict], seed: str = "") -> ReportMeta:
        """
        מחלץ מטא-דטה מהדוח: חודש, שנה, ימי עבודה, שעות אופייניות.
        """
        report = self.parse(words)

        month, year = self._parse_month_year(report.month)

        valid_lines = [
            l for l in report.lines
            if l.start_time and l.end_time
            and self._is_valid_time(l.start_time)
            and self._is_valid_time(l.end_time)
            and self._time_to_minutes(l.start_time) < self._time_to_minutes(l.end_time)
        ]
        start_counter = Counter(l.start_time for l in valid_lines)
        end_counter = Counter(l.end_time for l in valid_lines)
        typical_start = start_counter.most_common(1)[0][0] if start_counter else "08:00"
        typical_end = end_counter.most_common(1)[0][0] if end_counter else "16:00"

        return ReportMeta(
            doc_type="B",
            month=month,
            year=year,
            work_days=report.days,
            typical_start=typical_start,
            typical_end=typical_end,
            has_overtime=False,
            seed=seed,
        )

    def _is_valid_time(self, t: str) -> bool:
        """שעה הגיונית: בין 06:00 ל-22:00."""
        try:
            h, _ = map(int, t.split(":"))
            return 6 <= h <= 22
        except ValueError:
            return False

    def _time_to_minutes(self, t: str) -> int:
        """ממיר שעה למספר דקות מחצות."""
        h, m = map(int, t.split(":"))
        return h * 60 + m

    def _parse_month_year(self, month_str: str | None) -> tuple[int, int]:
        """ממיר מחרוזת '9/22' ל-(9, 2022)."""
        if not month_str:
            return 1, 2000
        parts = month_str.split("/")
        month = int(parts[0])
        year = int(parts[1]) if len(parts[1]) == 4 else 2000 + int(parts[1])
        return month, year

    def _group_rows(self, words: list[dict], y_threshold: int = 20) -> list[list[dict]]:
        """מקבץ מילים לשורות לפי קרבת y."""
        buckets: dict[int, list[dict]] = {}
        for w in words:
            key = w["y"] // y_threshold
            buckets.setdefault(key, []).append(w)

        rows = []
        for _, row_words in sorted(buckets.items()):
            # שורת נתונים: חייבת להכיל תאריך ולפחות שעה אחת
            texts = [w["text"] for w in row_words]
            has_date = any(DATE_RE.match(t) for t in texts)
            has_time = any(TIME_RE.match(t) for t in texts)
            if has_date and has_time:
                rows.append(sorted(row_words, key=lambda w: w["x"]))
        return rows

    def _detect_direction(self, rows: list[list[dict]]) -> str:
        """
        מזהה כיוון הדף לפי מיקום התאריכים:
        אם x ממוצע של תאריכים > 900 → RTL (עברית רגילה)
        אחרת → LTR
        """
        date_xs = [
            w["x"]
            for row in rows
            for w in row
            if DATE_RE.match(w["text"])
        ]
        if not date_xs:
            return "LTR"
        return "RTL" if (sum(date_xs) / len(date_xs)) > 900 else "LTR"

    def _parse_row(self, row: list[dict], direction: str) -> LineB | None:
        """
        מפרסר שורה בודדת לפי כיוון.
        RTL: date בימין (x גבוה), total בשמאל (x נמוך)
        LTR: date בשמאל (x נמוך), total בשמאל גם
        """
        texts = [w["text"] for w in row]

        date_words = [w for w in row if DATE_RE.match(w["text"])]
        time_words = [w for w in row if TIME_RE.match(w["text"])]
        num_words = [w for w in row if self._is_total(w["text"])]

        if not date_words or not time_words:
            return None

        date = date_words[0]["text"]

        if direction == "RTL":
            # שעות: start = x גבוה יותר, end = x נמוך יותר
            time_sorted = sorted(time_words, key=lambda w: w["x"], reverse=True)
        else:
            # שעות: start = x נמוך יותר, end = x גבוה יותר
            time_sorted = sorted(time_words, key=lambda w: w["x"])

        start_time = time_sorted[0]["text"] if len(time_sorted) > 0 else None
        end_time = time_sorted[1]["text"] if len(time_sorted) > 1 else None
        total = self._calc_total(start_time, end_time, num_words)

        return LineB(
            date=date,
            start_time=start_time,
            end_time=end_time,
            total=total,
        )

    def _fix_ocr_number(self, text: str) -> float | None:
        """
        מתקן מספרים שגויים של OCR:
        - '350' / '3550' → 3.50  (3 או 4 ספרות ללא נקודה)
        - '3.50' → 3.50 (תקין)
        מחזיר None אם לא מספר שעות הגיוני.
        """
        if NUMBER_RE.match(text):
            val = float(text.replace(":", "."))
            if 0.5 <= val <= 12:
                return val
        if OCR_3DIGIT_RE.match(text):
            # נסה להוסיף נקודה אחרי הספרה הראשונה: 350 → 3.50
            val = float(text[0] + "." + text[1:])
            if 0.5 <= val <= 12:
                return val
        return None

    def _is_total(self, text: str) -> bool:
        """מזהה מספר שעות תקין (כולל תיקון OCR)."""
        return self._fix_ocr_number(text) is not None

    def _calc_total(self, start: str, end: str, num_words: list[dict]) -> float:
        """
        מחשב סה"כ שעות: קודם מנסה מהמספרים שבשורה (עם תיקון OCR),
        אחרת מחשב הפרש start/end.
        """
        for w in num_words:
            val = self._fix_ocr_number(w["text"])
            if val is not None:
                return val

        if start and end:
            try:
                sh, sm = map(int, start.split(":"))
                eh, em = map(int, end.split(":"))
                diff = (eh * 60 + em - sh * 60 - sm) / 60
                if 0 < diff <= 12:
                    return round(diff, 2)
            except ValueError:
                pass
        return 0.0

    def _extract_month(self, rows: list[list[dict]]) -> str | None:
        """מחלץ חודש/שנה מהתאריך הראשון שנמצא."""
        for row in rows:
            for w in row:
                if DATE_RE.match(w["text"]):
                    parts = w["text"].split("/")
                    if len(parts) == 3:
                        return f"{parts[1]}/{parts[2]}"
        return None
