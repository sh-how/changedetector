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


def _area_slot(data: dict):
    """Return (container, watchers) where select/remove should edit areas.

    With profiles, that's the ACTIVE profile's mapping; otherwise the top level
    (migrating a legacy single-`region` config into a flat watchers list).
    """
    profiles = data.get("profiles")
    if isinstance(profiles, dict) and profiles:
        from .profiles import resolve_active

        active = resolve_active(data)
        container = profiles.get(active) or {}
        profiles[active] = container
        watchers = container.get("watchers")
        return container, list(watchers) if isinstance(watchers, list) else []

    watchers = data.get("watchers")
    if not isinstance(watchers, list) or not watchers:
        legacy = data.get("region")
        watchers = [{"name": "default", "region": legacy}] if isinstance(legacy, dict) else []
    data.pop("region", None)
    return data, watchers


def _upsert_watcher(config_path: str, name: str, region) -> None:
    """Add or update a named watcher in the active profile (or flat config)."""
    path = Path(config_path)
    data = {}
    if path.is_file():
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}

    container, watchers = _area_slot(data)
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

    container["watchers"] = watchers
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)


def _remove_watcher(config_path: str, name: str) -> str:
    """Remove a named watcher from the active profile (or flat config).

    Returns "removed", "not_found", or "last". Refuses to remove the final area
    (the active profile needs at least one). Does not write the file unless
    something actually changes.
    """
    path = Path(config_path)
    if not path.is_file():
        return "not_found"
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    container, watchers = _area_slot(data)
    names = [w.get("name") for w in watchers if isinstance(w, dict)]
    if name not in names:
        return "not_found"
    if len(watchers) <= 1:
        return "last"

    container["watchers"] = [
        w for w in watchers if not (isinstance(w, dict) and w.get("name") == name)
    ]
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, sort_keys=False)
    return "removed"


def _prompt_name(message: str = "Name this area (e.g. Inbox):") -> Optional[str]:
    """GUI text prompt (so commands work when launched by a tray click)."""
    import tkinter as tk
    from tkinter import simpledialog

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return simpledialog.askstring("changedetector", message, parent=root)
    finally:
        root.destroy()


def _confirm_dialog(message: str) -> bool:
    """GUI yes/no prompt (used by the tray, which passes --confirm)."""
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return bool(messagebox.askyesno("changedetector", message, parent=root))
    finally:
        root.destroy()


def _restart_monitor_if_running(config_path: str) -> bool:
    """If a monitor is running, stop it and start a fresh one so config changes apply."""
    import time

    from .config import read_poll_interval
    from .control import (
        is_running, request_stop, run_file_path, staleness_seconds, stop_file_path,
    )
    from .launcher import spawn_monitor

    run_path = run_file_path(config_path)
    max_age = staleness_seconds(read_poll_interval(config_path))
    if not is_running(run_path, max_age):
        return False

    request_stop(stop_file_path(config_path))
    for _ in range(100):  # wait up to ~10s for the old monitor to exit (clears heartbeat)
        if not is_running(run_path, max_age):
            break
        time.sleep(0.1)
    else:
        print("Warning: the running monitor didn't stop; not restarting. "
              "Run `changedetector stop`, then start it again.", file=sys.stderr)
        return False

    spawn_monitor(config_path)
    return True


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


def _stop_monitor_if_running(config_path: str) -> bool:
    """Request a running monitor to stop. Returns True if one was running."""
    from .config import read_poll_interval
    from .control import (
        is_running, request_stop, run_file_path, staleness_seconds, stop_file_path,
    )

    run_path = run_file_path(config_path)
    if not is_running(run_path, staleness_seconds(read_poll_interval(config_path))):
        return False
    request_stop(stop_file_path(config_path))
    return True


def _apply_profile_change(config_path: str) -> None:
    """After the active profile changed: restart a running monitor, or stop it
    (with guidance) when the new active profile has no areas yet."""
    from .config import ConfigError, load_app_config

    try:
        load_app_config(config_path)
    except ConfigError as exc:
        if _stop_monitor_if_running(config_path):
            print(f"Stopped the running monitor: {exc}")
        else:
            print(f"Note: {exc}")
        return
    if _restart_monitor_if_running(config_path):
        print("Restarted the running monitor on the new active profile.")


def cmd_profile(args) -> int:
    from .profiles import (
        create_profile, delete_profile, read_profiles, switch_profile,
    )

    if args.action == "list":
        names, active = read_profiles(args.config)
        if not names:
            print("No profiles configured yet. Create one with: changedetector profile create <name>")
            return 0
        for n in names:
            print(f"* {n}  (active)" if n == active else f"  {n}")
        return 0

    name = args.name
    if args.action == "create" and not name:
        name = _prompt_name("Name the new profile:")  # tray flow
    if not name or not name.strip():
        print("A profile name is required.", file=sys.stderr)
        return 2
    name = name.strip()

    if args.action == "create":
        if create_profile(args.config, name) == "exists":
            print(f"Profile '{name}' already exists.", file=sys.stderr)
            return 1
        print(f"Created profile '{name}' and switched to it.")
        _apply_profile_change(args.config)
        return 0

    if args.action == "switch":
        status = switch_profile(args.config, name)
        if status == "not_found":
            print(f"No profile named '{name}'.", file=sys.stderr)
            return 1
        if status == "already_active":
            print(f"Profile '{name}' is already active.")
            return 0
        print(f"Switched to profile '{name}'.")
        _apply_profile_change(args.config)
        return 0

    # delete
    status, new_active = delete_profile(args.config, name)
    if status == "not_found":
        print(f"No profile named '{name}'.", file=sys.stderr)
        return 1
    if status == "last":
        print(f"Refusing to delete '{name}': it's the only profile.", file=sys.stderr)
        return 1
    if new_active:
        print(f"Deleted profile '{name}'; switched to '{new_active}'.")
        _apply_profile_change(args.config)
    else:
        print(f"Deleted profile '{name}'.")
    return 0


def cmd_remove(args) -> int:
    if args.confirm and not _confirm_dialog(f"Remove watched area '{args.name}'?"):
        print("Cancelled.")
        return 0

    status = _remove_watcher(args.config, args.name)
    if status == "not_found":
        print(f"No area named '{args.name}'.", file=sys.stderr)
        return 1
    if status == "last":
        print(f"Refusing to remove '{args.name}': it's the only area "
              "(a config must keep at least one).", file=sys.stderr)
        return 1

    print(f"Removed area '{args.name}'.")
    if _restart_monitor_if_running(args.config):
        print("Restarted the running monitor to apply the change.")
    return 0


def cmd_show_areas(args) -> int:
    from .config import load_app_config
    from .overlay import resolved_areas, show_areas_overlay

    cfg = load_app_config(args.config)  # no secrets needed just to show areas
    monitors = None
    if any(w.monitor is not None for w in cfg.watchers):
        from .capture import Capturer
        with Capturer() as cap:
            monitors = cap.monitors()

    areas = resolved_areas(cfg.watchers, monitors)
    if not areas:
        print("No areas configured. Add one with: changedetector select --name <name> --write",
              file=sys.stderr)
        return 1
    # The highlight is drawn OUTSIDE each region (see overlay.py), so a running
    # monitor never captures it — no pausing needed.
    show_areas_overlay(areas, seconds=args.seconds)
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

    poller = _start_telegram_commands(cfg, secrets, pause_path, args.config)
    try:
        runner.run(
            cfg, secrets,
            is_paused=lambda: is_paused(pause_path),
            should_stop=lambda: is_stop_requested(stop_path),
            heartbeat=lambda: write_heartbeat(run_path),
        )
    finally:
        if poller:
            poller.stop()
        clear_heartbeat(run_path)
        clear_stop(stop_path)
    return 0


def _start_telegram_commands(cfg, secrets, pause_path, config_path):
    """Start the Telegram command listener in a daemon thread, if enabled.

    Returns the poller (so the caller can stop it) or None.
    """
    if cfg.alert.channel != "telegram" or not cfg.runtime.telegram_commands:
        return None
    import threading

    from .notifier import build_notifier
    from .profiles import read_profiles
    from .telegram_commands import CommandPoller

    # report what THIS monitor actually loaded (a config/profile change needs a
    # restart, which starts a fresh poller with the new list)
    area_names = [w.name for w in cfg.watchers]
    names, active = read_profiles(config_path)
    profile = active if (len(names) > 1 or (active and active != "default")) else None

    poller = CommandPoller(
        secrets.telegram_bot_token, secrets.telegram_chat_id, pause_path,
        notifier=build_notifier("telegram", secrets),
        area_names=area_names, profile=profile,
    )
    threading.Thread(target=poller.run, daemon=True).start()
    return poller


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

    p_show_areas = add("show-areas", "highlight the watched areas on screen", cmd_show_areas)
    p_show_areas.add_argument("--seconds", type=float, default=4.0,
                              help="how long the highlight stays up (default 4)")

    p_remove = add("remove", "delete a watched area by name", cmd_remove)
    p_remove.add_argument("--name", required=True, help="the area to remove")
    p_remove.add_argument("--confirm", action="store_true",
                          help="ask for confirmation first (used by the tray)")

    p_profile = add("profile", "manage profiles (named sets of watched areas)", cmd_profile)
    p_profile.add_argument("action", choices=["list", "create", "switch", "delete"],
                           help="what to do")
    p_profile.add_argument("name", nargs="?",
                           help="profile name (create prompts if omitted)")

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
