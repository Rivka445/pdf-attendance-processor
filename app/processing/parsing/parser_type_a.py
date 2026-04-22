import re
import calendar
from collections import Counter
from app.models.type_a import TypeA
from app.models.line_a import LineA
from app.models.report_meta import ReportMeta
from app.processing.rules.base_rules import calc_total, BREAK_HOURS_A

DAYS_HE = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
DATE_RE  = re.compile(r"\d{1,2}/\d{1,2}/\d{4}")
TIME_RE  = re.compile(r"\d{2}:\d{2}")


class ParserA:

    def parse(self, text: str) -> TypeA:
        """Parse OCR text into a TypeA report with all attendance rows."""
        report = TypeA()
        _, year = self._extract_month_year(text)
        for raw in text.split("\n"):
            line = self._parse_line(raw, year)
            if line:
                report.lines.append(line)
        report.days        = len(report.lines)
        report.total_hours = sum(l.total or 0 for l in report.lines)
        report.hours_100   = sum(l.hours_100 for l in report.lines)
        report.hours_125   = sum(l.hours_125 for l in report.lines)
        report.hours_150   = sum(l.hours_150 for l in report.lines)
        return report

    def extract_meta(self, text: str, seed: str = "") -> ReportMeta:
        """Extract ReportMeta from OCR text for use in variant generation."""
        report = self.parse(text)
        month, year = self._extract_month_year(text)
        valid = [l for l in report.lines
                 if l.start_time and l.end_time
                 and self._is_valid_time(l.start_time)
                 and self._is_valid_time(l.end_time)
                 and self._to_min(l.start_time) < self._to_min(l.end_time)]
        starts = Counter(l.start_time for l in valid)
        ends   = Counter(l.end_time   for l in valid)
        return ReportMeta(
            doc_type="A",
            month=month,
            year=year,
            work_days=report.days,
            typical_start=starts.most_common(1)[0][0] if starts else "08:00",
            typical_end=ends.most_common(1)[0][0]     if ends   else "16:00",
            has_overtime=report.hours_125 > 0 or report.hours_150 > 0,
            seed=seed,
        )

    def _parse_line(self, raw: str, year: int) -> LineA | None:
        """Parse a single OCR text line into a LineA, or return None if invalid."""
        line = self._clean(raw)
        times = TIME_RE.findall(line)
        if len(times) < 2:
            return None
        valid_times = [t for t in times if self._is_valid_time(t)]
        start = end = None
        for i in range(len(valid_times) - 1):
            if self._to_min(valid_times[i+1]) > self._to_min(valid_times[i]):
                start, end = valid_times[i], valid_times[i+1]
                break
        if not start or not end:
            for i in range(len(valid_times) - 1, 0, -1):
                if self._to_min(valid_times[i-1]) > self._to_min(valid_times[i]):
                    start, end = valid_times[i], valid_times[i-1]
                    break
        if not start or not end:
            return None
        date  = self._extract_date(line)
        day   = self._extract_day(line, date, year)
        nums  = self._numbers(line)
        total = calc_total(start, end, BREAK_HOURS_A)
        h100, h125, h150 = self._hour_types(nums, total)
        return LineA(
            date=date, day=day, start_time=start, end_time=end,
            break_time=int(BREAK_HOURS_A * 60), total=total,
            hours_100=h100, hours_125=h125, hours_150=h150, shabat=0,
        )

    def _extract_day(self, line: str, date: str | None, year: int) -> str | None:
        """Derive the Hebrew day name from the date, or fall back to text search."""
        if date:
            try:
                d, m, y = map(int, date.split("/"))
                return DAYS_HE[calendar.weekday(y, m, d)]
            except Exception:
                pass
        for name in DAYS_HE:
            if name in line:
                return name
        return None

    def _clean(self, line: str) -> str:
        """Normalize an OCR line by removing noise characters."""
        line = line.replace("|", " ")
        line = re.sub(r"[^\w\s:/\.]", "", line)
        return re.sub(r"\s+", " ", line).strip()

    def _numbers(self, line: str) -> list[float]:
        """Extract numeric values from a line, fixing 3-digit OCR artifacts."""
        raw = re.findall(r"\d+\.\d+|\d+", line)
        result = []
        for n in raw:
            if n.isdigit() and len(n) == 3:
                result.append(float(n[0] + "." + n[1:]))
            else:
                result.append(float(n))
        return result

    def _hour_types(self, nums: list[float], total: int) -> tuple[int, int, int]:
        """Split total minutes into 100%/125%/150% buckets based on overtime threshold."""
        overtime_threshold = 8 * 60
        if total > overtime_threshold:
            return overtime_threshold, total - overtime_threshold, 0
        return total, 0, 0

    def _is_valid_time(self, t: str) -> bool:
        """Return True if the time string represents a plausible work hour (06-22)."""
        try:
            h, _ = map(int, t.split(":"))
            return 6 <= h <= 22
        except ValueError:
            return False

    def _to_min(self, t: str) -> int:
        """Convert HH:MM to total minutes from midnight."""
        h, m = map(int, t.split(":"))
        return h * 60 + m

    def _extract_date(self, line: str) -> str | None:
        """Extract the first date pattern from a line, or return None."""
        m = DATE_RE.search(line)
        return m.group(0) if m else None

    def _extract_month_year(self, text: str) -> tuple[int, int]:
        """Extract month and year from the first date found in the full text."""
        m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        return (int(m.group(2)), int(m.group(3))) if m else (1, 2000)
