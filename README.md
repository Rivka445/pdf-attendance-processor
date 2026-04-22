# pdf-attendance-processor

Processes scanned attendance report PDFs, generates deterministic variants, and exports to PDF, Excel, and HTML.

---

## Features

- OCR extraction from scanned PDFs using Tesseract + pdf2image
- Automatic classification into Type A or Type B based on visual page structure
- Structured parsing into typed data models (`TypeA` / `TypeB`)
- Deterministic variant generation with ±15-minute time variation (seed = filename)
- Missing dates and day names reconstructed from the calendar automatically
- Export to PDF (Hebrew BiDi, RTL), Excel (RTL), and HTML (RTL)
- DI container — adding a new document type requires only `container.register_type(...)`
- Clean pipeline with no `if/elif` on document type
- 42 passing unit tests, all mockable via the container

---

## Project Structure

```
app/
├── core/
│   ├── container.py       # DI container — maps doc types and formats to handlers
│   ├── exceptions.py      # Typed exception hierarchy
│   ├── logger.py          # Shared logger setup
│   ├── pipeline.py        # Main processing pipeline
│   └── protocols.py       # Parser / Rules / Renderer structural protocols
├── models/
│   ├── line.py            # Base attendance row
│   ├── line_a.py          # Type A row (pay-rate breakdown)
│   ├── line_b.py          # Type B row (comment + Shabbat flag)
│   ├── type.py            # Generic base report
│   ├── type_a.py          # Type A report (totals, bonus, travel)
│   ├── type_b.py          # Type B report (worker name, payment)
│   └── report_meta.py     # Metadata extracted for variant generation
├── ocr/
│   ├── extractor.py       # PDF → words (x, y, text) via Tesseract
│   └── preprocess.py      # Grayscale + 2.5x upscale before OCR
├── processing/
│   ├── classification/
│   │   └── classifier.py  # Visual structure classifier (A / B / UNKNOWN)
│   ├── parsing/
│   │   ├── parser_type_a.py
│   │   └── parser_type_b.py
│   ├── rules/
│   │   ├── base_rules.py  # Shared utilities: vary_time, calc_total, get_work_days
│   │   ├── rules_type_a.py
│   │   └── rules_type_b.py
│   └── rendering/
│       ├── base_renderer.py
│       ├── pdf_renderer.py
│       ├── excel_renderer.py
│       └── html_renderer.py
├── templates.py           # Column definitions for each report type
└── row_extractor.py       # Field → display string conversion
main.py
tests/
└── test_all.py
```

---

## Requirements

- Python 3.12
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) with Hebrew language pack
- [Poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases)

Install Python dependencies:

```bash
pip install pytesseract pdf2image opencv-python reportlab openpyxl python-bidi
```

---

## Configuration

Set the paths in `app/ocr/extractor.py` to match your local installation:

```python
POPPLER_PATH = r"C:/Users/.../poppler-.../Library/bin"
pytesseract.pytesseract.tesseract_cmd = r"C:/Program Files/Tesseract-OCR/tesseract.exe"
```

---

## Usage

```python
from app.core.pipeline import run_pipeline

run_pipeline("pdf files/report.pdf", n=3, formats=["pdf", "excel", "html"], output_dir="export")
```

Output files are written to `export/<filename>/v1.pdf`, `v1.xlsx`, `v1.html`, etc.

---

## How Classification Works

| Signal | Type A | Type B |
|---|---|---|
| `100%` / `125%` in top 25% of page | ✓ | — |
| First time token below top 25% | — | ✓ |

Classification is purely visual — it uses pixel positions of OCR tokens, not Hebrew text matching.
This makes it robust to OCR encoding issues.

---

## How Variants Work

1. The parser extracts the original attendance rows and computes `ReportMeta` (month, year, typical start/end, work days).
2. For each variant `v1..vN`, a new seed (`filename_v1`) is used to create a seeded `random.Random`.
3. Each row's start and end times are shifted by a value drawn from `[-15, -10, -5, 0, 0, 0, 5, 10, 15]` minutes.
4. Dates and day names missing from OCR output are reconstructed from the calendar.
5. Totals are recalculated from the new times.

The same seed always produces the same output. Different seeds always produce different outputs.

---

## Architecture — Dependency Injection

The pipeline never imports or references `ParserA`, `ParserB`, `RulesA`, or any renderer directly.
Everything is resolved through the `Container` at runtime.

```
run_pipeline()
    │
    ├── container.extract_words()       # OCR
    ├── container.classify()            # classification
    ├── handler.prepare_input()         # format conversion (text or words)
    ├── handler.parser.parse()          # parsing
    ├── handler.parser.extract_meta()   # metadata
    ├── handler.rules.apply()           # variant generation  (×N)
    └── container.get_renderer().render()  # output  (×N × formats)
```

Each component satisfies a structural protocol (`ParserProtocol`, `RulesProtocol`, `RendererProtocol`).
No inheritance is required — any class with the right methods will work.

### Protocols

```python
class ParserProtocol(Protocol):
    def parse(self, input_data) -> object: ...
    def extract_meta(self, input_data, seed: str = "") -> ReportMeta: ...

class RulesProtocol(Protocol):
    def apply(self, meta: ReportMeta, source: object) -> object: ...

class RendererProtocol(Protocol):
    def render(self, report: object, output_path: str) -> str: ...
```

---

## Adding a New Document Type

Implement a parser and rules class, then register them — no other file needs to change:

```python
from app.core.container import Container
from app.core.pipeline import run_pipeline

class ParserC:
    def parse(self, input_data) -> TypeC:
        ...
    def extract_meta(self, input_data, seed: str = "") -> ReportMeta:
        ...

class RulesC:
    def apply(self, meta: ReportMeta, source: TypeC) -> TypeC:
        ...

container = Container()
container.register_type("C", parser=ParserC(), rules=RulesC())
run_pipeline("report.pdf", container=container)
```

If the new type needs a different input format (e.g. raw bytes instead of word list),
pass a custom `prepare_input` function:

```python
container.register_type(
    "C",
    parser=ParserC(),
    rules=RulesC(),
    prepare_input=lambda words, c: my_custom_transform(words),
)
```

---

## Adding a New Output Format

Implement a renderer and register it:

```python
class CsvRenderer:
    def render(self, report, output_path: str) -> str:
        ...

container = Container()
container.register_renderer("csv", CsvRenderer())
run_pipeline("report.pdf", formats=["csv"], container=container)
```

---

## Running Tests

```bash
python -m pytest tests/test_all.py -v
```

The test suite covers: `base_rules`, `RulesA`, `RulesB`, `Classifier`, `ParserA`, `RowExtractor`, `Container`, and `Pipeline`.

### How Tests Work — No Real PDFs Needed

Because all dependencies are injected through the container, every component can be tested
in isolation using `unittest.mock.MagicMock`. The pipeline tests never touch the filesystem or Tesseract:

```python
c = Container()
c.extract_words = MagicMock(return_value=[{"text": "100%", "x": 500, "y": 100}])
c.classify      = MagicMock(return_value="A")
handler = c.get_handler("A")
handler.parser.parse        = MagicMock(return_value=mock_source)
handler.parser.extract_meta = MagicMock(return_value=meta)
handler.rules.apply         = MagicMock(return_value=mock_report)
c.get_renderer("html").render = MagicMock(return_value="v1.html")

created = run_pipeline("test.pdf", n=1, formats=["html"], container=c)
```

### Adding a New Test

To test a new document type `C`, follow the same pattern:

```python
def test_pipeline_type_c(tmp_path):
    from app.core.pipeline import run_pipeline
    c = Container()
    meta = ReportMeta("C", 1, 2024, 20, "09:00", "17:00", False, "test_c")
    mock_source = MagicMock(); mock_source.lines = []
    mock_report = MagicMock(); mock_report.lines = []
    c.extract_words = MagicMock(return_value=[{"text": "x", "x": 0, "y": 0}])
    c.classify      = MagicMock(return_value="C")
    mock_parser = MagicMock()
    mock_parser.parse.return_value        = mock_source
    mock_parser.extract_meta.return_value = meta
    mock_rules = MagicMock()
    mock_rules.apply.return_value = mock_report
    c.register_type("C", parser=mock_parser, rules=mock_rules)
    c.get_renderer("html").render = MagicMock(return_value=str(tmp_path / "v1.html"))
    created = run_pipeline("test.pdf", n=1, formats=["html"],
                           output_dir=str(tmp_path), container=c)
    assert len(created) == 1
    mock_rules.apply.assert_called_once()
```

### Test Coverage by Module

| Module | What is tested |
|---|---|
| `base_rules` | `calc_total`, `minutes_to_str`, `to_minutes` with edge cases |
| `RulesA` | day count, date order, end > start, totals, determinism, different seeds |
| `RulesB` | work day count, Shabbat rows, no break deducted, payment calculation |
| `Classifier` | Type A by % columns, Type B by time position, empty input |
| `ParserA` | meta extraction, typical times, missing dates fallback |
| `RowExtractor` | minute fields, string fields, None fields |
| `Container` | handler registration, renderer registration, prepare_input functions |
| `Pipeline` | unsupported format, OCR failure, unknown classification, full A flow, new type C flow |

---

## Exception Hierarchy

All exceptions inherit from `AttendanceProcessorError` for easy top-level catching:

```
AttendanceProcessorError
├── OcrError               # PDF could not be read or Tesseract failed
├── ClassificationError    # Document type could not be determined
├── ParsingError           # Parser or rules raised an unexpected error
├── RenderingError         # Output file could not be written
└── UnsupportedFormatError # Requested format has no registered renderer
```

```python
from app.core.exceptions import AttendanceProcessorError

try:
    run_pipeline("report.pdf")
except AttendanceProcessorError as e:
    print(f"Processing failed: {e}")
```
