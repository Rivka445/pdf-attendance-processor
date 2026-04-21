import re
from collections import Counter
from models.report_meta import ReportMeta


class ParserA:

    def extract_meta(self, text: str, seed: str = "") -> ReportMeta:
        """מחלץ מטא-דטה מהדוח: חודש, שנה, ימי עבודה, שעות אופייניות."""
        lines = self._parse_lines(text)
        month, year = self._extract_month_year(text)

        valid = [
            l for l in lines
            if self._is_valid_time(l["start"]) and self._is_valid_time(l["end"])
            and self._time_to_min(l["start"]) < self._time_to_min(l["end"])
        ]
        starts = Counter(l["start"] for l in valid)
        ends   = Counter(l["end"]   for l in valid)
        has_overtime = any(l["h125"] > 0 or l["h150"] > 0 for l in lines)

        return ReportMeta(
            doc_type="A",
            month=month,
            year=year,
            work_days=len(lines),
            typical_start=starts.most_common(1)[0][0] if starts else "08:00",
            typical_end=ends.most_common(1)[0][0]     if ends   else "16:00",
            has_overtime=has_overtime,
            seed=seed,
        )

    def _parse_lines(self, text: str) -> list[dict]:
        results = []
        for raw in text.split("\n"):
            line = self._clean(raw)
            times = re.findall(r"\d{2}:\d{2}", line)
            if len(times) < 2:
                continue
            nums = self._numbers(line)
            h100, h125, h150 = self._hour_types(nums)
            results.append({"start": times[0], "end": times[1],
                             "h100": h100, "h125": h125, "h150": h150})
        return results

    def _clean(self, line: str) -> str:
        line = line.replace("|", " ")
        line = re.sub(r"[^\w\s:/\.]", "", line)
        return re.sub(r"\s+", " ", line).strip()

    def _numbers(self, line: str) -> list[float]:
        raw = re.findall(r"\d+\.\d+|\d+", line)
        result = []
        for n in raw:
            if n.isdigit() and len(n) == 3:
                result.append(float(n[0] + "." + n[1:]))
            else:
                result.append(float(n))
        return result

    def _hour_types(self, nums: list[float]) -> tuple[float, float, float]:
        h100 = h125 = h150 = 0.0
        for n in nums:
            if 0 < n <= 12:
                if n > 6:      h100 += n
                elif n > 2:    h125 += n
                else:          h150 += n
        return h100, h125, h150

    def _is_valid_time(self, t: str) -> bool:
        try:
            h, _ = map(int, t.split(":"))
            return 6 <= h <= 22
        except ValueError:
            return False

    def _time_to_min(self, t: str) -> int:
        h, m = map(int, t.split(":"))
        return h * 60 + m

    def _extract_month_year(self, text: str) -> tuple[int, int]:
        m = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
        return (int(m.group(2)), int(m.group(3))) if m else (1, 2000)
