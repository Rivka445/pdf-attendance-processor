"""
attendance_processor/config/logging_config.py
Centralised logging configuration for the attendance processor.

Usage
-----
Call ``setup_logging()`` once at the entry point of the application
(main.py / cli.py).  Every module that does::

    import logging
    logger = logging.getLogger(__name__)

will automatically inherit the handlers and level set here.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

# Default log directory (project-root / logs)
_DEFAULT_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"

LOG_FORMAT = "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    level: int = logging.INFO,
    log_dir: Path | str | None = None,
    log_filename: str = "attendance_processor.log",
    max_bytes: int = 5 * 1024 * 1024,   # 5 MB
    backup_count: int = 3,
) -> None:
    """Configure the root logger with a console handler and a rotating file handler.

    Parameters
    ----------
    level:
        Minimum log level for both handlers (e.g. ``logging.DEBUG``).
    log_dir:
        Directory where the log file is written.  Defaults to ``<project_root>/logs``.
    log_filename:
        Name of the rotating log file.
    max_bytes:
        Maximum size of a single log file before rotation.
    backup_count:
        Number of rotated backup files to keep.
    """
    log_dir = Path(log_dir) if log_dir else _DEFAULT_LOG_DIR

    formatter = logging.Formatter(fmt=LOG_FORMAT, datefmt=DATE_FORMAT)

    # ── Console handler (stderr) ──────────────────────────────────────────
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    handlers: list[logging.Handler] = [console_handler]

    # ── Rotating file handler ─────────────────────────────────────────────
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / log_filename
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(log_path),   # explicit str avoids Path issues on some Windows builds
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
            delay=False,              # open the file immediately so failures are caught here
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        handlers.append(file_handler)
    except Exception as exc:  # noqa: BLE001
        # Surface the error on stderr before the root logger is ready
        print(
            f"[logging_config] WARNING: could not create log file in {log_dir}: {exc}",
            file=sys.stderr,
        )

    # ── Root logger ───────────────────────────────────────────────────────
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()   # remove any handlers added before our call
    for h in handlers:
        root_logger.addHandler(h)

    # Silence noisy third-party loggers that are not relevant to the app
    logging.getLogger("fontTools").setLevel(logging.WARNING)
    logging.getLogger("fontTools.subset").setLevel(logging.ERROR)
    logging.getLogger("weasyprint").setLevel(logging.ERROR)
