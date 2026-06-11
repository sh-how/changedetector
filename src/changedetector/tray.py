"""System-tray controller.

A small foreground helper that controls the (separate, headless) monitor purely
through the sidecar control files, so the tray and the CLI are interchangeable
and closing the tray never kills monitoring. ``tray_state`` is pure and unit
tested; the pystray/Pillow wiring is verified manually.
"""

from __future__ import annotations

import logging

log = logging.getLogger("changedetector.tray")

_COLORS = {
    "Stopped": (120, 120, 120),
    "Running": (40, 170, 70),
    "Paused": (220, 170, 0),
}


def tray_state(running: bool, paused: bool) -> dict:
    """Map (running, paused) to the tray's status, icon color, and enabled actions."""
    if not running:
        status = "Stopped"
    elif paused:
        status = "Paused"
    else:
        status = "Running"
    return {
        "status": status,
        "color": _COLORS[status],
        "can_start": status == "Stopped",
        "can_pause": status == "Running",
        "can_resume": status == "Paused",
        "can_stop": status in ("Running", "Paused"),
    }


def _icon_image(color):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((8, 8, 56, 56), fill=tuple(color))
    return img


def run_tray(config_path) -> int:
    """Launch the tray icon (blocks until 'Quit tray'). Returns an exit code."""
    import threading
    import time

    import pystray
    from pystray import Menu, MenuItem as Item

    from .config import read_poll_interval
    from .control import (
        clear_paused, is_paused, is_running, pause_file_path, request_stop,
        run_file_path, set_paused, staleness_seconds, stop_file_path,
    )
    from .config import load_app_config
    from .launcher import spawn_monitor, spawn_remove, spawn_select, spawn_show_areas

    pause_path = pause_file_path(config_path)
    stop_path = stop_file_path(config_path)
    run_path = run_file_path(config_path)
    stale = staleness_seconds(read_poll_interval(config_path))

    def running_now() -> bool:
        return is_running(run_path, stale)

    def paused_now() -> bool:
        return is_paused(pause_path)

    def status_now() -> str:
        return tray_state(running_now(), paused_now())["status"]

    def on_start(icon, item):
        if not running_now():
            spawn_monitor(config_path)
            icon.notify("Monitoring started", "changedetector")

    def on_pause(icon, item):
        set_paused(pause_path)
        icon.notify("Alerts paused", "changedetector")

    def on_resume(icon, item):
        clear_paused(pause_path)
        icon.notify("Alerts resumed", "changedetector")

    def on_stop(icon, item):
        request_stop(stop_path)
        icon.notify("Stop requested", "changedetector")

    def on_configure(icon, item):
        spawn_select(config_path)  # prompts for a name, then shows the drag overlay

    def on_show_areas(icon, item):
        spawn_show_areas(config_path)  # briefly highlights the watched areas on screen

    def area_names():
        try:
            return [w.name for w in load_app_config(config_path).watchers]
        except Exception:  # noqa: BLE001 - a bad/missing config just yields an empty submenu
            return []

    def _make_remove_cb(name):
        # a factory keeps the callback at exactly (icon, item) — pystray rejects
        # actions with more than 2 params — while capturing this area's name
        def cb(icon, item):
            spawn_remove(config_path, name)
        return cb

    def remove_submenu():
        names = area_names()
        if not names:
            yield Item("(no areas)", None, enabled=False)
            return
        for name in names:
            yield Item(name, _make_remove_cb(name))

    def on_status(icon, item):
        icon.notify(f"Status: {status_now()}", "changedetector")

    def on_quit(icon, item):
        icon.visible = False
        icon.stop()

    menu = Menu(
        Item(lambda item: f"Status: {status_now()}", on_status),
        Menu.SEPARATOR,
        Item("Start", on_start, enabled=lambda item: not running_now()),
        Item("Pause", on_pause, enabled=lambda item: running_now() and not paused_now()),
        Item("Resume", on_resume, enabled=lambda item: running_now() and paused_now()),
        Item("Stop", on_stop, enabled=lambda item: running_now()),
        Menu.SEPARATOR,
        Item("Show watched areas", on_show_areas),
        Item("Configure area...", on_configure),
        Item("Remove area", Menu(remove_submenu)),
        Menu.SEPARATOR,
        Item("Quit tray", on_quit),
    )

    icon = pystray.Icon("changedetector", _icon_image(_COLORS["Stopped"]), "changedetector", menu)

    def setup(icon):
        icon.visible = True

        def poll():
            while icon.visible:
                try:
                    st = tray_state(running_now(), paused_now())
                    icon.icon = _icon_image(st["color"])
                    icon.title = f"changedetector: {st['status']}"
                    icon.update_menu()
                except Exception:  # noqa: BLE001 - keep the poller alive on any GUI/FS error
                    log.exception("tray poll error")
                time.sleep(2)

        threading.Thread(target=poll, daemon=True).start()

    icon.run(setup=setup)
    return 0
