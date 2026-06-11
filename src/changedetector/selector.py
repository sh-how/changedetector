"""Interactive drag-to-select region picker (tkinter overlay).

Call ``enable_dpi_awareness()`` before this (the CLI does). With the process
DPI-aware, tkinter's absolute pointer coordinates (``x_root``/``y_root``) are
physical pixels in the same virtual-screen space mss uses, so the returned
Region feeds ``Capturer.grab`` directly with no scaling.
"""

from __future__ import annotations

import logging
from typing import Optional

from .dpi import is_windows
from .geometry import Region, clamp_to_virtual_screen, normalize_drag

log = logging.getLogger("changedetector.selector")

_MIN_SIZE = 5  # a smaller drag is treated as an accidental click / cancel


def virtual_screen_box(root) -> dict:
    """Bounding box of all monitors, in the same coords as tkinter x_root."""
    if is_windows():
        import ctypes

        u = ctypes.windll.user32
        SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
        SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
        return {
            "left": u.GetSystemMetrics(SM_XVIRTUALSCREEN),
            "top": u.GetSystemMetrics(SM_YVIRTUALSCREEN),
            "width": u.GetSystemMetrics(SM_CXVIRTUALSCREEN),
            "height": u.GetSystemMetrics(SM_CYVIRTUALSCREEN),
        }
    return {
        "left": 0,
        "top": 0,
        "width": root.winfo_screenwidth(),
        "height": root.winfo_screenheight(),
    }


def select_region() -> Optional[Region]:
    """Show a fullscreen overlay; return the dragged Region, or None if cancelled."""
    import tkinter as tk

    root = tk.Tk()
    vbox = virtual_screen_box(root)

    root.overrideredirect(True)
    root.geometry(f"{vbox['width']}x{vbox['height']}+{vbox['left']}+{vbox['top']}")
    root.attributes("-alpha", 0.3)
    root.attributes("-topmost", True)
    root.configure(bg="black")

    canvas = tk.Canvas(root, cursor="cross", bg="gray15", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    canvas.create_text(
        vbox["width"] // 2,
        30,
        text="Drag to select the area to watch  •  Esc to cancel",
        fill="white",
        font=("Segoe UI", 16),
    )

    state = {"x0": 0, "y0": 0, "rx0": 0, "ry0": 0, "rect": None, "result": None}

    def on_press(e):
        state["x0"], state["y0"] = e.x, e.y
        state["rx0"], state["ry0"] = e.x_root, e.y_root
        state["rect"] = canvas.create_rectangle(e.x, e.y, e.x, e.y, outline="red", width=2)

    def on_drag(e):
        if state["rect"] is not None:
            canvas.coords(state["rect"], state["x0"], state["y0"], e.x, e.y)

    def on_release(e):
        state["result"] = normalize_drag(state["rx0"], state["ry0"], e.x_root, e.y_root)
        root.destroy()

    def on_escape(_e):
        state["result"] = None
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_escape)
    root.focus_force()
    root.mainloop()

    region = state["result"]
    if region is None or region.width < _MIN_SIZE or region.height < _MIN_SIZE:
        return None
    return clamp_to_virtual_screen(region, vbox)
