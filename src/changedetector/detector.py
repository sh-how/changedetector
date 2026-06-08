"""Pixel-diff change detection with a settle + cooldown state machine.

This module is pure logic over numpy arrays so it can be unit-tested with
synthetic frames and a fake clock. The runner does capture/preprocess and feeds
already-preprocessed frames (grayscale/downscaled) into ``ChangeDetector``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional

import numpy as np


# --- pure diff helpers -----------------------------------------------------

_LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float32)


def preprocess(frame: np.ndarray, downscale_factor: int = 1, grayscale: bool = True) -> np.ndarray:
    """Reduce a captured frame to a stable comparison array.

    Grayscale (luminance) drops chroma noise; integer downscale averages out
    sub-pixel jitter and anti-aliasing shimmer and speeds up the diff.
    """
    arr = frame
    if grayscale and arr.ndim == 3:
        arr = (arr[..., :3].astype(np.float32) @ _LUMA).astype(np.uint8)
    if downscale_factor and downscale_factor > 1:
        arr = _block_mean(arr, downscale_factor)
    return arr


def _block_mean(arr: np.ndarray, f: int) -> np.ndarray:
    """Average non-overlapping f x f blocks (area downsampling)."""
    h, w = arr.shape[:2]
    h2, w2 = (h // f) * f, (w // f) * f
    if h2 == 0 or w2 == 0:
        return arr
    arr = arr[:h2, :w2]
    if arr.ndim == 2:
        blocks = arr.reshape(h2 // f, f, w2 // f, f)
        return blocks.mean(axis=(1, 3)).astype(np.uint8)
    c = arr.shape[2]
    blocks = arr.reshape(h2 // f, f, w2 // f, f, c)
    return blocks.mean(axis=(1, 3)).astype(np.uint8)


def diff_ratio(a: np.ndarray, b: np.ndarray, intensity_threshold: int) -> float:
    """Fraction of pixels (0..1) whose intensity changed by more than the threshold.

    Two-stage threshold: a per-pixel intensity gate (rejects sensor/codec/anti-
    alias noise) followed by the area fraction (consumed by the FSM's ratio gate).
    """
    delta = np.abs(a.astype(np.int16) - b.astype(np.int16))
    changed = delta > intensity_threshold
    return float(changed.sum()) / float(changed.size)


# --- state machine ---------------------------------------------------------


class State(Enum):
    IDLE = auto()
    CHANGING = auto()
    COOLDOWN = auto()


@dataclass
class Event:
    kind: str
    ratio: float
    frame: np.ndarray
    timestamp: float


class ChangeDetector:
    """Emits exactly one Event when a change appears and then settles.

    ``update(frame, now)`` is fed one preprocessed frame per poll tick and
    returns an Event (once, when a change settles) or None.
    """

    def __init__(
        self,
        ratio_threshold: float,
        settle_ticks: int,
        cooldown_seconds: float,
        intensity_threshold: int = 25,
    ):
        self.ratio_threshold = ratio_threshold
        self.settle_ticks = settle_ticks
        self.cooldown_seconds = cooldown_seconds
        self.intensity_threshold = intensity_threshold

        self.state = State.IDLE
        self._reference: Optional[np.ndarray] = None  # last alerted baseline
        self._last: Optional[np.ndarray] = None       # immediately previous frame
        self._stable_count = 0
        self._cooldown_until = 0.0

    def reset(self) -> None:
        """Forget all state so the next frame becomes a fresh baseline.

        Used when resuming from a pause: changes that happened while paused are
        absorbed into the new baseline instead of firing a burst of alerts.
        """
        self.state = State.IDLE
        self._reference = None
        self._last = None
        self._stable_count = 0
        self._cooldown_until = 0.0

    def _diff(self, a: np.ndarray, b: np.ndarray) -> float:
        return diff_ratio(a, b, self.intensity_threshold)

    def update(self, frame: np.ndarray, now: float) -> Optional[Event]:
        # First frame establishes the baseline; nothing to compare against yet.
        if self._reference is None:
            self._reference = frame
            self._last = frame
            return None

        d_ref = self._diff(frame, self._reference)   # vs last alerted baseline
        d_prev = self._diff(frame, self._last)       # vs previous frame (motion)
        self._last = frame

        if self.state is State.COOLDOWN:
            if now < self._cooldown_until:
                return None
            # cooldown expired: rebaseline to current and resume watching
            self.state = State.IDLE
            self._reference = frame
            self._stable_count = 0
            return None

        if self.state is State.IDLE:
            if d_ref >= self.ratio_threshold:
                self.state = State.CHANGING
                self._stable_count = 0
            return None

        # State.CHANGING
        if d_prev >= self.ratio_threshold:
            # still moving; restart the settle counter
            self._stable_count = 0
            return None

        self._stable_count += 1
        if self._stable_count < self.settle_ticks:
            return None

        # settled: did it actually end up different from the baseline?
        self._stable_count = 0
        if d_ref >= self.ratio_threshold:
            self._reference = frame
            self.state = State.COOLDOWN
            self._cooldown_until = now + self.cooldown_seconds
            return Event(kind="change", ratio=d_ref, frame=frame, timestamp=now)

        # reverted to baseline (transient flash): rebaseline silently, no alert
        self._reference = frame
        self.state = State.IDLE
        return None
