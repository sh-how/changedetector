"""Windows DPI-awareness.

tkinter is DPI-unaware by default and reports logical (scaled) coordinates,
while mss captures in physical pixels. Making the process per-monitor DPI-aware
*before* creating any Tk window or capturing makes both agree on physical
pixels, so a region picked in the selector maps directly onto mss capture.

DPI awareness can only be set once per process, so call ``enable_dpi_awareness``
once at startup (the CLI does this for every subcommand).
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger("changedetector.dpi")


def is_windows() -> bool:
    return sys.platform.startswith("win")


def enable_dpi_awareness() -> None:
    """Best-effort per-monitor DPI awareness. No-op off Windows."""
    if not is_windows():
        return
    import ctypes

    try:
        # PROCESS_PER_MONITOR_DPI_AWARE = 2 (Windows 8.1+)
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        log.debug("per-monitor DPI awareness enabled")
        return
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # legacy system-DPI fallback
        log.debug("system DPI awareness enabled (legacy)")
    except (AttributeError, OSError):
        log.debug("could not set DPI awareness; coordinates may be scaled")
