"""Main monitoring loop: capture -> preprocess -> detect -> notify.

All side-effecting collaborators (capturer, notifier, clock) are injectable so
the whole loop can be exercised in tests with fakes and a deterministic clock.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

from .capture import Capturer, encode_png, is_probably_blank
from .config import AppConfig, Secrets
from .detector import ChangeDetector, Event, preprocess
from .geometry import resolve_region
from .notifier import build_notifier

log = logging.getLogger("changedetector.runner")


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)

    def now(self) -> datetime:
        return datetime.now()


def _compose_text(watcher, alert, label: str, clock) -> str:
    text = f"{label}{watcher.message}"
    if alert.include_timestamp:
        text = f"{text}\n{clock.now().strftime('%Y-%m-%d %H:%M:%S')}"
    return text


def _emit(watcher, alert, label: str, notifier, raw_frame, event: Event, clock) -> None:
    text = _compose_text(watcher, alert, label, clock)
    image = encode_png(raw_frame) if alert.attach_screenshot else None
    try:
        notifier.send(text, image_bytes=image)
        log.info("alert sent for '%s' (ratio=%.3f)", watcher.name, event.ratio)
    except Exception:  # noqa: BLE001 - never let a delivery failure kill the loop
        log.exception("failed to send alert for '%s'", watcher.name)


def _build_watch_state(cfg: AppConfig, capturer):
    """Resolve each watcher's region and give it its own detector."""
    state = []
    for w in cfg.watchers:
        region = w.region
        if w.monitor is not None:
            region = resolve_region(w.region, w.monitor, capturer.monitors())
        detector = ChangeDetector(
            ratio_threshold=w.detection.ratio_threshold,
            settle_ticks=w.detection.settle_ticks,
            cooldown_seconds=w.detection.cooldown_seconds,
            intensity_threshold=w.detection.intensity_threshold,
        )
        state.append((w, detector, region))
    return state


def run(
    cfg: AppConfig,
    secrets: Secrets,
    *,
    capturer=None,
    notifier=None,
    clock=None,
    is_paused=None,
    should_stop=None,
    heartbeat=None,
    max_ticks: Optional[int] = None,
) -> None:
    """Run the monitor loop. ``max_ticks=None`` runs until interrupted.

    Each watcher gets its own detector; one capture loop drives them all.
    Injected hooks (all optional): ``is_paused`` suppresses alerts and skips
    capture while True (rebaselining on resume); ``should_stop`` ends the loop
    cleanly; ``heartbeat`` is called every tick (even while paused) so external
    callers can tell the monitor is alive.
    """
    clock = clock or SystemClock()
    notifier = notifier or build_notifier(cfg.alert.channel, secrets)
    check_paused = is_paused or (lambda: False)
    check_stop = should_stop or (lambda: False)
    beat = heartbeat or (lambda: None)

    own_capturer = capturer is None
    if own_capturer:
        capturer = Capturer().__enter__()

    try:
        watch_state = _build_watch_state(cfg, capturer)
        multi = len(watch_state) > 1
        log.info("monitoring %d area(s) every %.2fs", len(watch_state),
                 cfg.capture.poll_interval_seconds)

        ticks = 0
        was_paused = False
        while max_ticks is None or ticks < max_ticks:
            beat()

            if check_stop():
                log.info("stop requested; exiting")
                break

            if check_paused():
                if not was_paused:
                    log.info("paused; alerts suppressed")
                    was_paused = True
                ticks += 1
                clock.sleep(cfg.capture.poll_interval_seconds)
                continue
            if was_paused:
                for _, detector, _ in watch_state:
                    detector.reset()  # rebaseline so pause-time changes don't alert
                log.info("resumed; rebaselined")
                was_paused = False

            now = clock.monotonic()
            for watcher, detector, region in watch_state:
                # One area's failure (capture, preprocess, diff) must not kill
                # the loop or stop the other areas.
                try:
                    frame = capturer.grab(region)
                    if cfg.runtime.blank_frame_policy == "skip" and is_probably_blank(frame):
                        log.debug("blank/locked frame skipped for '%s'", watcher.name)
                        continue
                    proc = preprocess(frame, cfg.capture.downscale_factor, cfg.capture.grayscale)
                    event = detector.update(proc, now)
                    if event is not None:
                        label = f"{watcher.name}: " if multi else ""
                        _emit(watcher, cfg.alert, label, notifier, frame, event, clock)
                except Exception:  # noqa: BLE001 - isolate per-watcher errors
                    log.exception("error processing watcher '%s'; skipping this tick", watcher.name)
                    continue

            ticks += 1
            clock.sleep(cfg.capture.poll_interval_seconds)
    except KeyboardInterrupt:
        log.info("stopped by user")
    finally:
        if own_capturer:
            capturer.__exit__(None, None, None)
