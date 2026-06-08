"""Coordinate types and pure geometry helpers.

All coordinates are physical pixels in the virtual-screen space, which is the
same space mss uses. The virtual screen may have a negative origin on
multi-monitor setups (a monitor placed left of / above the primary).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    """A rectangle in virtual-screen physical-pixel coordinates."""

    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def to_mss_dict(self) -> dict:
        """Shape expected by ``mss.mss().grab(...)``."""
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


def normalize_drag(x0: float, y0: float, x1: float, y1: float) -> Region:
    """Build a Region from two drag corners in any order.

    Coordinates are rounded to ints so the result maps cleanly onto pixels.
    """
    left = round(min(x0, x1))
    top = round(min(y0, y1))
    width = round(max(x0, x1)) - left
    height = round(max(y0, y1)) - top
    return Region(left, top, width, height)


def clamp_to_virtual_screen(region: Region, vbox: dict) -> Region:
    """Clamp ``region`` so it stays within ``vbox`` (an mss monitor dict).

    ``vbox`` has keys left/top/width/height and may have a negative origin.
    Returns a Region whose edges lie within the box; width/height may shrink
    to (a minimum of) zero if the region falls largely outside.
    """
    v_left = vbox["left"]
    v_top = vbox["top"]
    v_right = v_left + vbox["width"]
    v_bottom = v_top + vbox["height"]

    left = min(max(region.left, v_left), v_right)
    top = min(max(region.top, v_top), v_bottom)
    right = min(max(region.right, left), v_right)
    bottom = min(max(region.bottom, top), v_bottom)

    return Region(left, top, right - left, bottom - top)


def resolve_region(region: Region, monitor, monitors) -> Region:
    """Resolve a monitor-relative region to absolute virtual-screen coordinates.

    ``monitor`` is a 1-based index into ``monitors`` (the mss list, whose [0] is
    the whole virtual screen). ``None`` means the region is already absolute.
    """
    if monitor is None:
        return region
    if monitor < 1 or monitor >= len(monitors):
        raise ValueError(
            f"monitor {monitor} out of range (have {len(monitors) - 1} monitors)"
        )
    m = monitors[monitor]
    return Region(
        region.left + m["left"],
        region.top + m["top"],
        region.width,
        region.height,
    )
