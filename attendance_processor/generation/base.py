"""
generation/base.py
==================
Abstract base class for all report renderers.

Every concrete renderer must implement a single method:

    render(report, output_path) -> Path

The contract guarantees:
  - The returned Path points to the file that was written.
  - ``output_path`` may be a *directory* (the renderer chooses a filename)
    or a fully qualified file path (the renderer writes exactly there).
  - Pre-flight validation (writable directory) is checked before any
    rendering work begins so failures are reported early.

All custom exceptions are defined in :mod:`errors` and re-exported here
for backward compatibility::

    from generation.base import RenderingError, OutputDirectoryError
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from domain.models import AttendanceReport
from errors import MissingRendererError, OutputDirectoryError, RenderingError

__all__ = [
    "BaseRenderer",
    "RenderingError",
    "OutputDirectoryError",
    "MissingRendererError",
]

logger = logging.getLogger(__name__)


class BaseRenderer(ABC):
    """
    Contract for all report format renderers.

    Subclasses implement :meth:`render`; shared pre-flight helpers are
    provided here so validation is not repeated in every subclass.
    """

    @abstractmethod
    def render(self, report: AttendanceReport, output_path: Path) -> Path:
        """
        Generate the output file for *report* at *output_path*.

        Raises:
            OutputDirectoryError: Directory is missing or not writable.
            RenderingError:       Any other rendering failure.
        """

    # ── Shared pre-flight helpers ────────────────────────────────────────────

    @staticmethod
    def _ensure_output_dir(path: Path) -> None:
        """Create *path* (or its parent); raise :class:`OutputDirectoryError` on failure."""
        directory = path if path.is_dir() else path.parent
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.error("BaseRenderer: cannot create directory %s — %s", directory, exc)
            raise OutputDirectoryError(directory, str(exc)) from exc

        probe = directory / ".write_probe"
        try:
            probe.touch()
            probe.unlink()
        except OSError as exc:
            logger.error("BaseRenderer: directory not writable %s — %s", directory, exc)
            raise OutputDirectoryError(directory, "not writable") from exc

        logger.debug("BaseRenderer: output directory OK  path=%s", directory)

    @staticmethod
    def _resolve_output_path(output_path: Path, default_name: str) -> Path:
        """Append *default_name* when *output_path* is a directory."""
        if output_path.is_dir():
            return output_path / default_name
        return output_path
