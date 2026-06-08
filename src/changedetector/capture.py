"""Screen capture via mss, plus pure image helpers (blank detection, PNG encode).

Coordinates are physical pixels in the virtual-screen space. Capture only works
against an interactive, unlocked desktop session; locked/disconnected sessions
return black frames (handled via ``is_probably_blank`` + the runner's policy).
"""

from __future__ import annotations

import io

import numpy as np
from PIL import Image

from .geometry import Region


def is_probably_blank(frame: np.ndarray, std_threshold: float = 2.0, max_threshold: int = 8) -> bool:
    """Heuristic for a locked/disconnected screen: near-uniform or near-black."""
    return bool(frame.max() < max_threshold or frame.std() < std_threshold)


def encode_png(frame: np.ndarray) -> bytes:
    """Encode an RGB (HxWx3) or grayscale (HxW) uint8 frame to PNG bytes."""
    mode = "L" if frame.ndim == 2 else "RGB"
    img = Image.fromarray(frame, mode=mode)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


class Capturer:
    """Grabs screen regions as RGB numpy arrays. Use as a context manager."""

    def __init__(self):
        self._sct = None

    def __enter__(self) -> "Capturer":
        import mss

        self._sct = mss.mss()
        return self

    def __exit__(self, *exc) -> None:
        if self._sct is not None:
            self._sct.close()
            self._sct = None

    def virtual_screen_box(self) -> dict:
        """The bounding box covering all monitors (mss ``monitors[0]``)."""
        return dict(self._sct.monitors[0])

    def monitors(self) -> list:
        """Full mss monitor list: [0]=virtual screen, [1..]=individual monitors."""
        return [dict(m) for m in self._sct.monitors]

    def grab(self, region: Region) -> np.ndarray:
        """Capture ``region`` and return it as an HxWx3 uint8 RGB array."""
        shot = self._sct.grab(region.to_mss_dict())
        bgra = np.asarray(shot)  # mss returns BGRA
        return np.ascontiguousarray(bgra[:, :, [2, 1, 0]])  # -> RGB
