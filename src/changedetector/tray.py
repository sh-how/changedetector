"""System-tray controller.

A small foreground helper that controls the (separate, headless) monitor purely
through the sidecar control files, so the tray and the CLI are interchangeable
and closing the tray never kills monitoring. ``tray_state`` is pure and unit
tested; the pystray/Pillow wiring is verified manually.
"""

from __future__ import annotations

import logging
import sys

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


def _hover_fixed_icon_class(pystray):
    """A pystray.Icon subclass that fixes Windows tray-menu mouse tracking.

    pystray (0.19.x) foregrounds the icon window before showing the popup, but
    the popup is owned by a *different* window (``_menu_hwnd``); per Win32 the
    menu-owning window must be foreground or the popup won't track the mouse
    (items don't highlight on hover, and it doesn't dismiss on click-away). This
    overrides ``_on_notify`` with pystray's own logic, foregrounding the menu's
    own window. Returns None (use stock pystray) off Windows or if internals
    differ.
    """
    if not sys.platform.startswith("win"):
        return None
    try:
        import ctypes
        from ctypes import wintypes

        from pystray._win32 import win32
    except Exception:  # noqa: BLE001 - unknown pystray internals -> fall back
        log.warning("tray hover fix unavailable; using stock pystray menu")
        return None

    class _HoverFixedIcon(pystray.Icon):
        def _on_notify(self, wparam, lparam):
            if lparam == win32.WM_LBUTTONUP:
                self()
            elif lparam == win32.WM_RBUTTONUP:
                # Rebuild the menu NOW, on this thread, before showing it. The
                # menu must never be rebuilt while displayed: update_menu()
                # destroys the live HMENU, which kills mouse tracking (no hover
                # highlight). Rebuilding at open also evaluates enabled-states
                # and labels at the freshest possible moment.
                self.update_menu()
                if not self._menu_handle:
                    return
                win32.SetForegroundWindow(self._menu_hwnd)  # menu's own window
                point = wintypes.POINT()
                win32.GetCursorPos(ctypes.byref(point))
                hmenu, descriptors = self._menu_handle
                index = win32.TrackPopupMenuEx(
                    hmenu,
                    win32.TPM_RIGHTALIGN | win32.TPM_BOTTOMALIGN | win32.TPM_RETURNCMD,
                    point.x, point.y, self._menu_hwnd, None)
                # Canonical tray-menu recipe (KB135788): nudge the message loop
                # so the next popup behaves after a click-away dismissal.
                win32.PostMessage(self._menu_hwnd, 0, 0, 0)  # WM_NULL
                if index > 0:
                    descriptors[index - 1](self)

    return _HoverFixedIcon


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
        # Quit stops the monitor too (a running monitor sees the stop file and
        # exits within one poll interval), then closes the tray.
        request_stop(stop_path)
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
        Item("Quit (stops monitoring)", on_quit),
    )

    icon_cls = _hover_fixed_icon_class(pystray)
    rebuilds_menu_on_open = icon_cls is not None
    icon_cls = icon_cls or pystray.Icon
    icon = icon_cls("changedetector", _icon_image(_COLORS["Stopped"]), "changedetector", menu)

    def setup(icon):
        icon.visible = True

        def poll():
            while icon.visible:
                try:
                    st = tray_state(running_now(), paused_now())
                    icon.icon = _icon_image(st["color"])
                    icon.title = f"changedetector: {st['status']}"
                    # Never rebuild the menu from this thread on Windows: doing
                    # so destroys the HMENU the user may have open, which kills
                    # hover highlighting. The hover-fixed icon rebuilds the menu
                    # each time it is opened instead. (Stock-pystray fallback
                    # keeps the periodic rebuild so states don't go stale.)
                    if not rebuilds_menu_on_open:
                        icon.update_menu()
                except Exception:  # noqa: BLE001 - keep the poller alive on any GUI/FS error
                    log.exception("tray poll error")
                time.sleep(2)

        threading.Thread(target=poll, daemon=True).start()

    icon.run(setup=setup)
    return 0
