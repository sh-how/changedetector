"""Command-line interface.

Commands: select | run | pause | resume | stop | status | tray | test-alert |
show-config. All control commands (pause/resume/stop/status) talk to a running
monitor through sidecar control files, so they work even when it runs headless.
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from pathlib import Path
from typing import Optional

import yaml

from .dpi import enable_dpi_awareness


# --- helpers ---------------------------------------------------------------

def _render_watcher_yaml(name: str, region) -> str:
    return (
        f"  - name: {name}\n"
        f"    region: {{left: {region.left}, top: {region.top}, "
        f"width: {region.width}, height: {region.height}, monitor: null}}\n"
    )


def _upsert_watcher(config_path: str, name: str, region) -> None:
    """Add or update a named watcher in the YAML config (comments not preserved)."""
    path = Path(config_path)
    data = {}
    if path.is_file():
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

    watchers = data.get("watchers")
    if not isinstance(watchers, list) or not watchers:
        watchers = []
        legacy = data.get("region")
        if isinstance(legacy, dict):  # migrate a legacy single-region config
            watchers.append({"name": "default", "region": legacy})
    data.pop("region", None)

    new_region = {
        "left": region.left, "top": region.top,
        "width": region.width, "height": region.height, "monitor": None,
    }
    for w in watchers:
        if isinstance(w, dict) and w.get("name") == name:
            w["region"] = new_region  # update region, keep any per-area overrides
            break
    else:
        watchers.append({"name": name, "region": new_region})

    data["watchers"] = watchers
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)


def _prompt_name() -> Optional[str]:
    """GUI prompt for an area name (so this works when launched by a click)."""
    import tkinter as tk
    from tkinter import simpledialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return simpledialog.askstring("changedetector", "Name this area (e.g. Inbox):", parent=root)
    finally:
        root.destroy()


# --- commands --------------------------------------------------------------

def cmd_select(args) -> int:
    from .selector import select_region

    name = args.name or _prompt_name()
    if not name or not name.strip():
        print("Cancelled (no area name given).", file=sys.stderr)
        return 1
    name = name.strip()

    region = select_region()
    if region is None:
        print("Selection cancelled (no region captured).", file=sys.stderr)
        return 1

    if args.write:
        _upsert_watcher(args.config, name, region)
        print(f"Saved area '{name}' to {args.config}")
    else:
        print(_render_watcher_yaml(name, region))
        print(f"Add the block above under 'watchers:' in {args.config} (or re-run with --write).")
    return 0


def cmd_run(args) -> int:
    from .config import load_config
    from .control import (
        clear_heartbeat, clear_paused, clear_stop, is_paused, is_running,
        is_stop_requested, pause_file_path, run_file_path, staleness_seconds,
        stop_file_path, write_heartbeat,
    )
    from .logging_setup import setup_logging
    from . import runner

    cfg, secrets = load_config(args.config)
    setup_logging(cfg.runtime.log_file, cfg.runtime.log_level)

    run_path = run_file_path(args.config)
    max_age = staleness_seconds(cfg.capture.poll_interval_seconds)
    if is_running(run_path, max_age) and not args.force:
        print("A monitor already appears to be running for this config "
              "(use --force to start anyway).", file=sys.stderr)
        return 1

    pause_path = pause_file_path(args.config)
    stop_path = stop_file_path(args.config)
    clear_stop(stop_path)          # ignore any stale stop request
    clear_paused(pause_path)       # a fresh start is always active, never silently paused
    write_heartbeat(run_path)
    try:
        runner.run(
            cfg, secrets,
            is_paused=lambda: is_paused(pause_path),
            should_stop=lambda: is_stop_requested(stop_path),
            heartbeat=lambda: write_heartbeat(run_path),
        )
    finally:
        clear_heartbeat(run_path)
        clear_stop(stop_path)
    return 0


def cmd_pause(args) -> int:
    from .control import pause_file_path, set_paused

    set_paused(pause_file_path(args.config))
    print(f"Paused - alerts suppressed. Resume with: changedetector resume --config {args.config}")
    return 0


def cmd_resume(args) -> int:
    from .control import clear_paused, pause_file_path

    clear_paused(pause_file_path(args.config))
    print("Resumed - monitoring active.")
    return 0


def cmd_stop(args) -> int:
    from .control import request_stop, stop_file_path

    request_stop(stop_file_path(args.config))
    print("Stop requested - the monitor will exit within one poll interval.")
    return 0


def cmd_status(args) -> int:
    from .config import read_poll_interval
    from .control import (
        is_paused, is_running, pause_file_path, run_file_path, staleness_seconds,
    )

    max_age = staleness_seconds(read_poll_interval(args.config))
    if not is_running(run_file_path(args.config), max_age):
        print("not running")
    elif is_paused(pause_file_path(args.config)):
        print("running (paused)")
    else:
        print("running")
    return 0


def cmd_tray(args) -> int:
    from .tray import run_tray

    return run_tray(args.config)


def cmd_test_alert(args) -> int:
    from .capture import Capturer, encode_png
    from .config import load_config
    from .geometry import resolve_region
    from .logging_setup import setup_logging
    from .notifier import build_notifier

    cfg, secrets = load_config(args.config)
    setup_logging(cfg.runtime.log_file, cfg.runtime.log_level)
    notifier = build_notifier(cfg.alert.channel, secrets)
    multi = len(cfg.watchers) > 1

    with Capturer() as cap:
        for w in cfg.watchers:
            image = None
            if cfg.alert.attach_screenshot:
                region = w.region
                if w.monitor is not None:
                    region = resolve_region(w.region, w.monitor, cap.monitors())
                image = encode_png(cap.grab(region))
            label = f"{w.name}: " if multi else ""
            notifier.send(f"{label}changedetector test alert", image_bytes=image)

    print(f"Test alert sent for {len(cfg.watchers)} area(s) via {cfg.alert.channel}.")
    return 0


def cmd_show_config(args) -> int:
    from .config import load_config

    cfg, _ = load_config(args.config)
    print(yaml.safe_dump(dataclasses.asdict(cfg), sort_keys=False))
    return 0


# --- parser ----------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="changedetector",
        description="Headless screen-region change detector with Telegram alerts.",
    )
    sub = parser.add_subparsers(dest="command")

    def add(name, help_text, func):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--config", default="config.yaml")
        p.set_defaults(func=func)
        return p

    p_select = add("select", "interactively drag-select an area to watch", cmd_select)
    p_select.add_argument("--name", help="name for this area (prompts if omitted)")
    p_select.add_argument("--write", action="store_true", help="save the area into the config file")

    p_run = add("run", "start monitoring", cmd_run)
    p_run.add_argument("--force", action="store_true", help="start even if one seems to be running")

    add("pause", "suppress alerts while you work", cmd_pause)
    add("resume", "re-enable alerts (rebaselines)", cmd_resume)
    add("stop", "tell a running monitor to exit", cmd_stop)
    add("status", "show running / paused / not running", cmd_status)
    add("tray", "launch the system-tray controller", cmd_tray)
    add("test-alert", "send a one-off test alert per area (with screenshot)", cmd_test_alert)
    add("show-config", "print the resolved config (no secrets)", cmd_show_config)

    return parser


def main(argv: Optional[list] = None) -> int:
    # Must run before any Tk window or screen capture so coordinates are physical.
    enable_dpi_awareness()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except Exception as exc:  # noqa: BLE001 - surface a clean message, not a traceback
        from .config import ConfigError

        if isinstance(exc, ConfigError):
            print(f"Config error: {exc}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    sys.exit(main())
