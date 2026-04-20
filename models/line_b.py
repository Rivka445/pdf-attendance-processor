from dataclasses import dataclass
from typing import Optional
from .line import Line


@dataclass
class LineB(Line):
    comment: Optional[str] = None