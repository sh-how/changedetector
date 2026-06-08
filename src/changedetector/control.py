"""Control the running monitor via small sidecar files it polls each tick.

Three files live next to the config, named after it so every command (and the
tray) agrees on the paths without parsing the config or needing any secrets:

- ``<config>.pause`` — present means alerts are suppressed.
- ``<config>.stop``  — present means "exit cleanly at the next tick".
- ``<config>.run``   — heartbeat the monitor touches each tick; a fresh mtime
  means a monitor is alive (used for status and the double-start guard).
"""

from __future__ import annotations

import time
from pathlib import Path


def _sidecar(config_path, suffix: str) -> Path:
    p = Path(config_path).resolve()
    return p.parent / (p.stem + suffix)


# --- pause -----------------------------------------------------------------

def pause_file_path(config_path) -> Path:
    return _sidecar(config_path, ".pause")


def is_paused(pause_path) -> bool:
    return Path(pause_path).exists()


def set_paused(pause_path) -> None:
    Path(pause_path).write_text("paused\n", encoding="utf-8")


def clear_paused(pause_path) -> None:
    Path(pause_path).unlink(missing_ok=True)


# --- stop ------------------------------------------------------------------

def stop_file_path(config_path) -> Path:
    return _sidecar(config_path, ".stop")


def is_stop_requested(stop_path) -> bool:
    return Path(stop_path).exists()


def request_stop(stop_path) -> None:
    Path(stop_path).write_text("stop\n", encoding="utf-8")


def clear_stop(stop_path) -> None:
    Path(stop_path).unlink(missing_ok=True)


# --- heartbeat / running state --------------------------------------------

def run_file_path(config_path) -> Path:
    return _sidecar(config_path, ".run")


def write_heartbeat(run_path) -> None:
    """Touch the run file (rewriting updates its mtime)."""
    Path(run_path).write_text("running\n", encoding="utf-8")


def clear_heartbeat(run_path) -> None:
    Path(run_path).unlink(missing_ok=True)


def staleness_seconds(poll_interval: float) -> float:
    """Heartbeat age (>= 10s) beyond which a monitor is considered not running.

    Scales with the poll interval so slow-polling monitors aren't misreported.
    """
    return max(10.0, poll_interval * 3.0)


def is_running(run_path, max_age: float, now=None) -> bool:
    """True if a heartbeat exists and was updated within ``max_age`` seconds.

    ``now`` defaults to the current time; pass it explicitly in tests.
    """
    p = Path(run_path)
    if not p.exists():
        return False
    if now is None:
        now = time.time()
    return (now - p.stat().st_mtime) <= max_age
