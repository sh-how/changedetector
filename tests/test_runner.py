from datetime import datetime
from unittest import mock

import numpy as np

from changedetector.config import build_config, Secrets
from changedetector import runner


def base_frame():
    # varied content (a column gradient) so it is NOT classified as a blank frame
    f = np.zeros((40, 40, 3), dtype=np.uint8)
    f[:] = np.arange(40, dtype=np.uint8)[None, :, None]
    return f


def changed_frame():
    f = base_frame()
    f[:20, :, :] = 255  # paint the top half white -> ~50% of pixels change
    return f


def blank_frame():
    return np.zeros((40, 40, 3), dtype=np.uint8)  # all black -> "blank" (locked screen)


class FakeCapturer:
    def __init__(self, frames):
        self.frames = frames
        self.i = 0
        self.grabs = 0

    def grab(self, region):
        self.grabs += 1
        frame = self.frames[min(self.i, len(self.frames) - 1)]
        self.i += 1
        return frame

    def monitors(self):
        m = {"left": 0, "top": 0, "width": 1920, "height": 1080}
        return [m, m]


class FakeMultiCapturer:
    """Returns a per-region frame sequence, keyed by the region's coordinates."""

    def __init__(self, frames_by_region):
        self.frames_by_region = frames_by_region
        self.idx = {k: 0 for k in frames_by_region}
        self.grabs = 0

    def grab(self, region):
        self.grabs += 1
        key = (region.left, region.top, region.width, region.height)
        frames = self.frames_by_region[key]
        i = min(self.idx[key], len(frames) - 1)
        self.idx[key] += 1
        return frames[i]

    def monitors(self):
        m = {"left": 0, "top": 0, "width": 1920, "height": 1080}
        return [m, m]


class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = 0

    def monotonic(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds
        self.sleeps += 1

    def now(self):
        return datetime(2026, 6, 3, 12, 0, 0)


def make_cfg(**overrides):
    data = {
        "region": {"left": 0, "top": 0, "width": 40, "height": 40, "monitor": None},
        "capture": {"poll_interval_seconds": 0.01, "downscale_factor": 2, "grayscale": True},
        "detection": {
            "intensity_threshold": 25,
            "ratio_threshold": 0.02,
            "settle_ticks": 2,
            "cooldown_seconds": 1000,
        },
        "alert": {
            "channel": "console",
            "message": "Change detected",
            "attach_screenshot": True,
            "include_timestamp": False,
        },
        "runtime": {"blank_frame_policy": "skip", "log_level": "INFO", "log_file": "x.log"},
    }
    for section, vals in overrides.items():
        data[section].update(vals)
    cfg, _ = build_config(data, {})
    return cfg


def make_multi_cfg():
    data = {
        "watchers": [
            {"name": "Inbox", "region": {"left": 0, "top": 0, "width": 40, "height": 40, "monitor": None}},
            {"name": "Teams", "region": {"left": 100, "top": 0, "width": 40, "height": 40, "monitor": None}},
        ],
        "capture": {"poll_interval_seconds": 0.01, "downscale_factor": 2, "grayscale": True},
        "detection": {"intensity_threshold": 25, "ratio_threshold": 0.02, "settle_ticks": 2, "cooldown_seconds": 1000},
        "alert": {"channel": "console", "message": "Change detected", "attach_screenshot": False, "include_timestamp": False},
        "runtime": {"blank_frame_policy": "skip", "log_level": "INFO", "log_file": "x.log"},
    }
    cfg, _ = build_config(data, {})
    return cfg


INBOX_KEY = (0, 0, 40, 40)
TEAMS_KEY = (100, 0, 40, 40)


class FakePause:
    """Returns a scripted paused/running state per tick (one call per loop iteration)."""

    def __init__(self, schedule):
        self.schedule = schedule
        self.i = 0

    def __call__(self):
        v = self.schedule[min(self.i, len(self.schedule) - 1)]
        self.i += 1
        return v


class TestRunnerLoop:
    def test_change_triggers_single_alert(self):
        cfg = make_cfg()
        frames = [base_frame(), base_frame()] + [changed_frame()] * 3
        cap = FakeCapturer(frames)
        notifier = mock.Mock()
        runner.run(cfg, Secrets(), capturer=cap, notifier=notifier, clock=FakeClock(), max_ticks=5)
        notifier.send.assert_called_once()
        _, kwargs = notifier.send.call_args
        text = notifier.send.call_args[0][0]
        assert "Change detected" in text
        assert kwargs.get("image_bytes")  # screenshot attached

    def test_no_screenshot_when_disabled(self):
        cfg = make_cfg(alert={"attach_screenshot": False})
        frames = [base_frame(), base_frame()] + [changed_frame()] * 3
        notifier = mock.Mock()
        runner.run(cfg, Secrets(), capturer=FakeCapturer(frames), notifier=notifier,
                   clock=FakeClock(), max_ticks=5)
        notifier.send.assert_called_once()
        assert notifier.send.call_args.kwargs.get("image_bytes") is None

    def test_blank_frames_never_alert(self):
        cfg = make_cfg()
        cap = FakeCapturer([blank_frame()] * 6)
        notifier = mock.Mock()
        runner.run(cfg, Secrets(), capturer=cap, notifier=notifier, clock=FakeClock(), max_ticks=6)
        notifier.send.assert_not_called()

    def test_respects_max_ticks_and_sleeps_each_tick(self):
        cfg = make_cfg()
        cap = FakeCapturer([base_frame()] * 10)
        clock = FakeClock()
        runner.run(cfg, Secrets(), capturer=cap, notifier=mock.Mock(), clock=clock, max_ticks=4)
        assert cap.grabs == 4
        assert clock.sleeps == 4

    def test_no_capture_while_paused(self):
        cfg = make_cfg()
        cap = FakeCapturer([base_frame()] * 10)
        # is_paused is checked once per tick; paused on ticks 1 and 2
        pause = FakePause([False, True, True, False])
        runner.run(cfg, Secrets(), capturer=cap, notifier=mock.Mock(),
                   clock=FakeClock(), is_paused=pause, max_ticks=4)
        # only the 2 running ticks grabbed; paused ticks skipped capture
        assert cap.grabs == 2

    def test_change_during_pause_does_not_alert_after_resume(self):
        cfg = make_cfg()  # settle_ticks=2
        a, c = base_frame(), changed_frame()
        # frames are consumed ONLY on running ticks. Running ticks see: a, a, c, c, c
        # (baseline a; then at resume the screen already shows c -> rebaselined, no alert)
        cap = FakeCapturer([a, a, c, c, c])
        pause = FakePause([False, False, True, True, False, False, False])
        notifier = mock.Mock()
        runner.run(cfg, Secrets(), capturer=cap, notifier=notifier,
                   clock=FakeClock(), is_paused=pause, max_ticks=7)
        notifier.send.assert_not_called()

    def test_new_change_after_resume_alerts(self):
        cfg = make_cfg()  # settle_ticks=2
        a, c = base_frame(), changed_frame()
        # running ticks see: a, a, c, a, a, a -> resume rebaselines to c, then a is a
        # genuinely new change that settles -> exactly one alert
        cap = FakeCapturer([a, a, c, a, a, a])
        pause = FakePause([False, False, True, True, False, False, False, False])
        notifier = mock.Mock()
        runner.run(cfg, Secrets(), capturer=cap, notifier=notifier,
                   clock=FakeClock(), is_paused=pause, max_ticks=8)
        notifier.send.assert_called_once()

    def test_timestamp_included_when_enabled(self):
        cfg = make_cfg(alert={"include_timestamp": True})
        frames = [base_frame(), base_frame()] + [changed_frame()] * 3
        notifier = mock.Mock()
        runner.run(cfg, Secrets(), capturer=FakeCapturer(frames), notifier=notifier,
                   clock=FakeClock(), max_ticks=5)
        text = notifier.send.call_args[0][0]
        assert "2026-06-03" in text

    def test_single_watcher_has_no_label_prefix(self):
        cfg = make_cfg()  # legacy single region -> one watcher
        frames = [base_frame(), base_frame()] + [changed_frame()] * 3
        notifier = mock.Mock()
        runner.run(cfg, Secrets(), capturer=FakeCapturer(frames), notifier=notifier,
                   clock=FakeClock(), max_ticks=5)
        assert notifier.send.call_args[0][0] == "Change detected"  # no "name: " prefix


class TestMultiWatcher:
    def test_alert_labeled_by_area_and_others_silent(self):
        cfg = make_multi_cfg()
        a, c = base_frame(), changed_frame()
        frames = {INBOX_KEY: [a, a, c, c, c], TEAMS_KEY: [a, a, a, a, a]}
        notifier = mock.Mock()
        runner.run(cfg, Secrets(), capturer=FakeMultiCapturer(frames), notifier=notifier,
                   clock=FakeClock(), max_ticks=5)
        notifier.send.assert_called_once()
        text = notifier.send.call_args[0][0]
        assert "Inbox" in text and "Teams" not in text

    def test_both_areas_alert_independently(self):
        cfg = make_multi_cfg()
        a, c = base_frame(), changed_frame()
        frames = {INBOX_KEY: [a, a, c, c, c], TEAMS_KEY: [a, a, c, c, c]}
        notifier = mock.Mock()
        runner.run(cfg, Secrets(), capturer=FakeMultiCapturer(frames), notifier=notifier,
                   clock=FakeClock(), max_ticks=5)
        assert notifier.send.call_count == 2
        texts = [call.args[0] for call in notifier.send.call_args_list]
        assert any("Inbox" in t for t in texts)
        assert any("Teams" in t for t in texts)


class TestStopAndHeartbeat:
    def test_stop_request_exits_loop_early(self):
        cfg = make_cfg()
        cap = FakeCapturer([base_frame()] * 100)

        class Stop:
            def __init__(self):
                self.n = 0

            def __call__(self):
                self.n += 1
                return self.n >= 3  # request stop on the 3rd tick

        runner.run(cfg, Secrets(), capturer=cap, notifier=mock.Mock(), clock=FakeClock(),
                   should_stop=Stop(), max_ticks=100)
        assert cap.grabs == 2  # stopped before the 3rd capture

    def test_heartbeat_called_every_tick(self):
        cfg = make_cfg()
        beats = []
        runner.run(cfg, Secrets(), capturer=FakeCapturer([base_frame()] * 5),
                   notifier=mock.Mock(), clock=FakeClock(),
                   heartbeat=lambda: beats.append(1), max_ticks=4)
        assert len(beats) == 4

    def test_heartbeat_continues_while_paused(self):
        cfg = make_cfg()
        beats = []
        runner.run(cfg, Secrets(), capturer=FakeCapturer([base_frame()] * 5),
                   notifier=mock.Mock(), clock=FakeClock(),
                   is_paused=FakePause([True, True, False, False]),
                   heartbeat=lambda: beats.append(1), max_ticks=4)
        assert len(beats) == 4  # heartbeat every tick, even while paused
