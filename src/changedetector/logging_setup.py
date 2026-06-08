"""Logging configuration: rotating file always, console when one is attached.

Under ``pythonw.exe`` there is no console (stdout/stderr may be missing), so the
console handler is added only when a real stdout is present.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler


def setup_logging(log_file: str, level: str = "INFO") -> None:
    root = logging.getLogger("changedetector")
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Add a console handler only when a usable stdout exists (not under pythonw).
    if sys.stdout is not None and getattr(sys.stdout, "fileno", None) is not None:
        try:
            sys.stdout.fileno()
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setFormatter(fmt)
            root.addHandler(stream_handler)
        except (OSError, ValueError):
            pass
