"""Spawn the monitor / selector as detached processes (used by the tray).

The tray controls the monitor only through control files, but it needs to be
able to *start* it. Starting via ``pythonw.exe`` keeps the monitor windowless,
and detaching it means it keeps running after the tray closes.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def gui_python() -> str:
    """Path to pythonw.exe (windowless) next to the current interpreter, if present."""
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return str(candidate) if candidate.exists() else str(exe)


def monitor_command(config_path, python: str = None) -> list:
    return [python or gui_python(), "-m", "changedetector", "run", "--config", str(config_path)]


def select_command(config_path, name: str = None, python: str = None) -> list:
    cmd = [python or gui_python(), "-m", "changedetector", "select", "--write",
           "--config", str(config_path)]
    if name:
        cmd += ["--name", name]
    return cmd


def _spawn(argv) -> int:
    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = subprocess.CREATE_NO_WINDOW | getattr(subprocess, "DETACHED_PROCESS", 0)
    proc = subprocess.Popen(argv, creationflags=creationflags, close_fds=True)
    return proc.pid


def spawn_monitor(config_path) -> int:
    return _spawn(monitor_command(config_path))


def spawn_select(config_path, name: str = None) -> int:
    return _spawn(select_command(config_path, name))
