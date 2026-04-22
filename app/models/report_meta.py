from dataclasses import dataclass


@dataclass
class ReportMeta:
    """Metadata extracted from a parsed document, used to generate variants."""
    doc_type: str
    month: int
    year: int
    work_days: int
    typical_start: str
    typical_end: str
    has_overtime: bool
    seed: str
