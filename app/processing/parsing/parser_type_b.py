import re
import calendar
from collections import Counter
from app.models.type_b import TypeB
from app.models.line_b import LineB
from app.models.report_meta import ReportMeta

DAYS_HE       = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
DATE_RE       = re.compile(r'^\d{1,2}/\d{1,2}/\d{2,4}$')
TIME_RE       = re.compile(r'^\d{1,2}:\d{2}$')


class ParserB:

    def parse(self, words: list[dict]) -> TypeB:
        """
        Parse a list of OCR word dicts into a TypeB report.
        Groups words into rows by Y position, detects RTL/LTR direction,
        then parses each row into a LineB.
        """
        report = TypeB()
        rows = self._group_rows(words)
        if not rows:
            return report
        direction    = self._detect_direction(rows)
        report.month = self._extract_month(rows)
        for row in rows:
            line = self._parse_row(row, direction)
            if line:
                report.lines.append(line)
        report.days        = len(report.lines)
        report.total_hours = sum(l.total or 0 for l in report.lines)
        return report

    def extract_meta(self, words: list[dict], seed: str = "") -> ReportMeta:
        """Extract ReportMeta from OCR word list for use in variant generation."""
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
        end_counter   = Counter(l.end_time   for l in valid_lines)
        return ReportMeta(
            doc_type="B",
            month=month,
            year=year,
            work_days=report.days,
            typical_start=start_counter.most_common(1)[0][0] if start_counter else "08:00",
            typical_end=end_counter.most_common(1)[0][0]     if end_counter   else "16:00",
            has_overtime=False,
            seed=seed,
        )

    def _is_valid_time(self, t: str) -> bool:
        """Return True if the time string is a plausible work hour (06-22)."""
        try:
            h, _ = map(int, t.split(":"))
            return 6 <= h <= 22
        except ValueError:
            return False

    def _time_to_minutes(self, t: str) -> int:
        """Convert H:MM or HH:MM to total minutes from midnight."""
        h, m = map(int, t.split(":"))
        return h * 60 + m

    def _parse_month_year(self, month_str: str | None) -> tuple[int, int]:
        """Parse a 'M/YY' or 'M/YYYY' string into (month, year) integers."""
        if not month_str:
            return 1, 2000
        parts = month_str.split("/")
        month = int(parts[0])
        year  = int(parts[1]) if len(parts[1]) == 4 else 2000 + int(parts[1])
        return month, year

    def _group_rows(self, words: list[dict], y_threshold: int = 20) -> list[list[dict]]:
        """
        Bucket words by Y position and keep only rows that contain
        both a date and at least one time value.
        """
        buckets: dict[int, list[dict]] = {}
        for w in words:
            key = w["y"] // y_threshold
            buckets.setdefault(key, []).append(w)
        rows = []
        for _, row_words in sorted(buckets.items()):
            texts    = [w["text"] for w in row_words]
            has_date = any(DATE_RE.match(t) for t in texts)
            has_time = any(TIME_RE.match(t) for t in texts)
            if has_date and has_time:
                rows.append(sorted(row_words, key=lambda w: w["x"]))
        return rows

    def _detect_direction(self, rows: list[list[dict]]) -> str:
        """
        Determine page direction by the average X position of date tokens.
        X > 900 means dates are on the right side, indicating RTL layout.
        """
        date_xs = [w["x"] for row in rows for w in row if DATE_RE.match(w["text"])]
        if not date_xs:
            return "LTR"
        return "RTL" if (sum(date_xs) / len(date_xs)) > 900 else "LTR"

    def _parse_row(self, row: list[dict], direction: str) -> LineB | None:
        """
        Parse a single word row into a LineB.
        In RTL layout the start time has a higher X value than the end time.
        """
        date_words = [w for w in row if DATE_RE.match(w["text"])]
        time_words = [w for w in row if TIME_RE.match(w["text"])]
        num_words  = [w for w in row if self._is_total(w["text"])]
        if not date_words or not time_words:
            return None
        date = date_words[0]["text"]
        day  = self._day_from_date(date)
        if direction == "RTL":
            time_sorted = sorted(time_words, key=lambda w: w["x"], reverse=True)
        else:
            time_sorted = sorted(time_words, key=lambda w: w["x"])
        start_time = time_sorted[0]["text"] if len(time_sorted) > 0 else None
        end_time   = time_sorted[1]["text"] if len(time_sorted) > 1 else None
        total = self._calc_total(start_time, end_time, num_words)
        return LineB(date=date, day=day, start_time=start_time, end_time=end_time, total=total)

    def _fix_ocr_number(self, text: str) -> float | None:
        """
        Attempt to interpret a token as a decimal hour value.
        Handles OCR artifacts like '350' -> 3.50 and '3.50' -> 3.50.
        Returns None if the value is outside the plausible range 0.5-12.
        """
        if re.match(r'^\d+[.]\d+$', text):
            val = float(text)
            if 0.5 <= val <= 12:
                return val
        if re.match(r'^\d{3,4}$', text):
            val = float(text[0] + "." + text[1:])
            if 0.5 <= val <= 12:
                return val
        return None

    def _is_total(self, text: str) -> bool:
        """Return True if the token looks like a valid total-hours value."""
        return self._fix_ocr_number(text) is not None

    def _calc_total(self, start: str, end: str, num_words: list[dict]) -> float:
        """
        Compute total hours from explicit numeric tokens in the row,
        falling back to end - start arithmetic if none are found.
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

    def _day_from_date(self, date_str: str) -> str | None:
        """Compute the Hebrew weekday name from a date string (D/M/YY or D/M/YYYY)."""
        try:
            parts = date_str.split("/")
            d, m = int(parts[0]), int(parts[1])
            y = int(parts[2]) if len(parts[2]) == 4 else 2000 + int(parts[2])
            return DAYS_HE[calendar.weekday(y, m, d)]
        except Exception:
            return None

    def _extract_month(self, rows: list[list[dict]]) -> str | None:
        """Extract the month/year string from the first date token found."""
        for row in rows:
            for w in row:
                if DATE_RE.match(w["text"]):
                    parts = w["text"].split("/")
                    if len(parts) == 3:
                        return f"{parts[1]}/{parts[2]}"
        return None
