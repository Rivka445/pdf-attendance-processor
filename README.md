# Attendance Report Processor

Processes scanned attendance PDF reports (TYPE_A / TYPE_B), applies realistic time-jitter transformation, and renders output as HTML, Excel, and PDF.

---

## Project Structure

```
attendance_processor/
├── classification/     # Classifier — detects TYPE_A vs TYPE_B
├── config/             # Business rules (workday bounds, OT thresholds)
├── domain/             # Immutable domain models + custom exceptions
├── generation/         # Renderers: HTML, Excel, PDF
├── ingestion/          # PDF → OCR text (Tesseract + PyMuPDF)
├── parsers/            # TypeAParser, TypeBParser, ParserFactory
├── transformation/     # Time-jitter strategies + TransformationService
├── app.py              # Application facade — process_pdf()
├── container.py        # DI container (AppContainer / AppConfig)
├── errors.py           # Re-export of domain.errors for bare imports
└── registry.py         # TypeRegistry — single source of truth per type

cli.py                  # CLI entry point (thin — calls app.process_pdf)
main.py                 # Simple script entry point
Dockerfile              # Container definition
requirements.txt        # Pinned dependencies (Windows)
requirements-docker.txt # Unpinned dependencies (Linux/Docker)
tests/
├── unit/               # Unit tests per module
└── integration/        # End-to-end pipeline tests
```

---

## Prerequisites

### Windows (local)
- Python 3.12+
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) — install to `C:\Program Files\Tesseract-OCR\`
- Hebrew language pack: included in the Tesseract installer (select `heb` during setup)
- [GTK3 Runtime](https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases) — required for PDF rendering via WeasyPrint

### Docker
No local dependencies needed — everything is installed inside the container.

---

## Installation (local)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

## Usage

### CLI (recommended)

```powershell
# Single file — HTML + Excel + PDF output
.venv\Scripts\python cli.py input\a_r_25.pdf -o C:\output

# Multiple files at once
.venv\Scripts\python cli.py input\a_r_25.pdf input\n_r_10_n.pdf -o C:\output

# Choose specific formats
.venv\Scripts\python cli.py input\a_r_25.pdf -o C:\output --formats html excel pdf

# Skip transformation step
.venv\Scripts\python cli.py input\a_r_25.pdf --no-transform

# Verbose / quiet logging
.venv\Scripts\python cli.py input\a_r_25.pdf -v
.venv\Scripts\python cli.py input\a_r_25.pdf -q
```

#### All CLI options

| Option | Default | Description |
|--------|---------|-------------|
| `input` | — | One or more PDF paths |
| `-o / --output-dir` | `./output` | Output directory |
| `--formats` | `html excel pdf` | Output formats |
| `--no-transform` | off | Skip time-jitter step |
| `--threshold` | `0.25` | Classifier confidence threshold (0–1) |
| `--tesseract` | auto | Path to tesseract executable |
| `-v / --verbose` | off | DEBUG logging |
| `-q / --quiet` | off | Warnings only |

### Simple script

```powershell
.venv\Scripts\python main.py "input\a_r_25.pdf" C:\output
```

---

## Docker

### Build

```powershell
docker build -t attendance-report .
```

### Run

```powershell
# Output to local folder
docker run --rm -v ${PWD}/input:/data -v ${PWD}/output:/output attendance-report /data/a_r_25.pdf -o /output/

# All formats
docker run --rm -v ${PWD}/input:/data -v ${PWD}/output:/output attendance-report /data/a_r_25.pdf -o /output/ --formats html excel pdf

# Multiple files
docker run --rm -v ${PWD}/input:/data -v ${PWD}/output:/output attendance-report /data/a_r_25.pdf /data/n_r_10_n.pdf -o /output/
```

---

## Output Formats

| Format | Description |
|--------|-------------|
| `.html` | Self-contained RTL HTML with styled table and summary bar |
| `.xlsx` | Two sheets: `נוכחות` (attendance rows) + `סיכום` (summary) |
| `.pdf` | PDF rendered from the HTML via WeasyPrint |

---

## Report Types

| Type | Description |
|------|-------------|
| `TYPE_A` | נ.ע. הנשר — includes location, break column, OT bands (100%/125%/150%/שבת) |
| `TYPE_B` | Hourly/part-time — includes hourly rate, total pay, notes column |

---

## Pipeline

```
PDF file
  └─► PDFExtractor (PyMuPDF + Tesseract OCR)
        └─► Classifier (keyword scoring → TYPE_A / TYPE_B)
              └─► ParserFactory → TypeAParser / TypeBParser
                    └─► TransformationService (time-jitter per date seed)
                          └─► HtmlRenderer / ExcelRenderer / PdfRenderer
```

---

## Running Tests

```powershell
python -m pytest tests/ -q
```

261 tests — unit + integration.

```powershell
# Unit tests only
python -m pytest tests/unit/ -q

# Integration tests only
python -m pytest tests/integration/ -q

# With coverage
python -m pytest tests/ --cov=attendance_processor
```

---

## Architecture

- **Immutable domain models** — `frozen=True` Pydantic models; transformers always return new objects
- **DI Container** (`AppContainer`) — lazy singleton services, all dependencies injected via constructor
- **TypeRegistry** — single registration point for parser + strategy + rules per report type
- **Strategy pattern** — `TypeATransformationStrategy` / `TypeBTransformationStrategy` per report type
- **Template Method** — `BaseParser.parse()` orchestrates; subclasses implement `_parse_row`, `_parse_summary`, etc.
- **Thin CLI** — `cli.py` only parses arguments and calls `app.process_pdf()`; no business logic

---

## Design Patterns

### Strategy
The transformation layer uses the Strategy pattern. `TransformationService` holds a registry of strategies, one per report type. At runtime it selects the correct strategy (`TypeATransformationStrategy` / `TypeBTransformationStrategy`) without any `if/else` branching. Adding a new report type requires only registering a new strategy — no changes to existing code.

```
TransformationService
  └─► TypeRegistry.get_strategy(report_type)
        ├─► TypeATransformationStrategy.transform_row(row, rules)
        └─► TypeBTransformationStrategy.transform_row(row, rules)
```

### Template Method
`BaseParser.parse()` defines the skeleton of the parsing algorithm: split lines → extract summary → filter headers → parse rows → convert to domain objects. Subclasses (`TypeAParser`, `TypeBParser`) implement only the steps that differ (`_parse_row`, `_parse_summary`, `_rows_to_domain`, `_summary_to_domain`). The orchestration logic is never duplicated.

```
BaseParser.parse()          ← template method (shared, never overridden)
  ├─► _parse_summary()      ← implemented by subclass
  ├─► _is_header_line()     ← implemented by subclass
  ├─► _parse_row()          ← implemented by subclass
  ├─► _rows_to_domain()     ← implemented by subclass
  └─► _summary_to_domain()  ← implemented by subclass
```

### Dependency Injection
`AppContainer` wires the entire application. Every service is created once (lazy singleton) and receives its dependencies through the constructor — nothing is imported at module level inside services. This makes every component independently testable and replaceable.

```python
container = AppContainer(AppConfig(tesseract_cmd=r"C:\..."))
container.parser_factory        # ParserFactory(registry=...)
container.transformation_service  # TransformationService(registry=...)
container.renderers             # [HtmlRenderer(), ExcelRenderer(), PdfRenderer()]
```

### Registry
`TypeRegistry` is the single source of truth for every report type. Instead of three separate dicts scattered across `ParserFactory`, `TransformationService`, and `config/rules.py`, all per-type components (parser + strategy + rules) are registered once. Adding a new type is a single `registry.register()` call.

### Facade
`app.process_pdf()` is a facade that hides the full pipeline complexity behind one function call. `cli.py` and `main.py` call only this function — they have zero knowledge of OCR, classification, parsing, or transformation internals.

### Immutable Value Objects
All domain models (`TimeRange`, `BreakRecord`, `OvertimeBuckets`, `AttendanceRow`, `ReportSummary`, `AttendanceReport`) are frozen Pydantic models or frozen dataclasses. Transformers never mutate — they always return new objects. This eliminates an entire class of bugs and makes the pipeline fully deterministic.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TESSERACT_CMD` | `C:\Program Files\Tesseract-OCR\tesseract.exe` | Path to tesseract (auto-set in Docker) |
