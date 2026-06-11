"""Briefly highlight the watched areas on screen.

``resolved_areas`` is pure and unit tested; ``show_areas_overlay`` is a DPI-aware
tkinter overlay (call ``enable_dpi_awareness`` first, which the CLI does) and is
verified manually.
"""

from __future__ import annotations

import logging

from .geometry import resolve_region

log = logging.getLogger("changedetector.overlay")

_CHROMA = "#010203"  # near-black key color made transparent on Windows
_FRAME_GAP = 10       # px the highlight frame sits OUTSIDE each region (must exceed _FRAME_WIDTH/2)
_FRAME_WIDTH = 4      # highlight frame line thickness


def resolved_areas(watchers, monitors=None):
    """Return [(name, absolute Region)] for each watcher, resolving monitor-relative ones."""
    areas = []
    for w in watchers:
        if w.monitor is not None and monitors is not None:
            region = resolve_region(w.region, w.monitor, monitors)
        else:
            region = w.region
        areas.append((w.name, region))
    return areas


def show_areas_overlay(areas, seconds: float = 4.0) -> None:
    """Draw labeled rectangles over the live screen at each area, then auto-close."""
    if not areas:
        return

    import tkinter as tk

    from .selector import virtual_screen_box

    root = tk.Tk()
    vbox = virtual_screen_box(root)
    root.overrideredirect(True)
    root.geometry(f"{vbox['width']}x{vbox['height']}+{vbox['left']}+{vbox['top']}")
    root.attributes("-topmost", True)

    # A normal, visible window. The region interiors stay transparent (live
    # screen) and the highlight frames are drawn outside the regions, so the
    # monitor's capture of each region is unchanged and never alerts.
    transparent = True
    try:
        root.configure(bg=_CHROMA)
        root.attributes("-transparentcolor", _CHROMA)  # Windows: only drawn pixels show
    except tk.TclError:
        transparent = False
        root.attributes("-alpha", 0.4)

    canvas = tk.Canvas(root, bg=_CHROMA if transparent else "gray15", highlightthickness=0)
    canvas.pack(fill="both", expand=True)

    # The frame is drawn entirely OUTSIDE each watched region (GAP px beyond the
    # boundary). The monitor captures exactly the region rectangle, so it never
    # sees these pixels — the highlight can't trigger an alert, with no pausing.
    gap, width = _FRAME_GAP, _FRAME_WIDTH
    for name, region in areas:
        x0 = region.left - vbox["left"]
        y0 = region.top - vbox["top"]
        x1, y1 = x0 + region.width, y0 + region.height
        canvas.create_rectangle(x0 - gap, y0 - gap, x1 + gap, y1 + gap,
                                outline="#ff3030", width=width)
        label_y = y0 - gap - 10
        if label_y < 14:  # region near the top edge -> put the label below instead
            label_y = y1 + gap + 10
        canvas.create_text(x0, label_y, anchor="w", text=name,
                           fill="#ff3030", font=("Segoe UI", 14, "bold"))

    canvas.create_text(
        vbox["width"] // 2, 24,
        text=f"Watched areas ({len(areas)}) — closes in {int(seconds)}s, or press Esc / click",
        fill="#ff3030", font=("Segoe UI", 14, "bold"),
    )

    root.bind("<Escape>", lambda _e: root.destroy())
    root.bind("<Button-1>", lambda _e: root.destroy())
    root.after(int(seconds * 1000), root.destroy)
    root.mainloop()
