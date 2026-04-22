from typing import Protocol, runtime_checkable
from app.models.report_meta import ReportMeta


@runtime_checkable
class ParserProtocol(Protocol):
    """Contract for all document parsers."""

    def parse(self, input_data) -> object:
        """Parse raw input and return a typed report object."""
        ...

    def extract_meta(self, input_data, seed: str = "") -> ReportMeta:
        """Extract metadata from the document for variant generation."""
        ...


@runtime_checkable
class RulesProtocol(Protocol):
    """Contract for all variant-generation rules."""

    def apply(self, meta: ReportMeta, source: object) -> object:
        """Apply deterministic variation to source and return a new report."""
        ...


@runtime_checkable
class RendererProtocol(Protocol):
    """Contract for all output renderers."""

    def render(self, report: object, output_path: str) -> str:
        """Render the report to a file and return the output path."""
        ...
