import numpy as np

from changedetector.detector import (
    ChangeDetector,
    Event,
    diff_ratio,
    preprocess,
)


def gray(value, shape=(100, 100)):
    return np.full(shape, value, dtype=np.uint8)


def half_changed(shape=(100, 100)):
    """A frame where ~50% of pixels are white (the rest black)."""
    f = np.zeros(shape, dtype=np.uint8)
    f[: shape[0] // 2, :] = 255
    return f


class TestDiffRatio:
    def test_identical_frames_zero(self):
        a = gray(0)
        assert diff_ratio(a, a, intensity_threshold=25) == 0.0

    def test_fraction_of_changed_pixels(self):
        a = np.zeros((10, 10), dtype=np.uint8)
        b = a.copy()
        b.flat[:20] = 255  # 20 of 100 pixels flipped hard
        assert diff_ratio(a, b, intensity_threshold=25) == 0.2

    def test_subthreshold_intensity_ignored(self):
        # a uniform +10 shift is below the 25 intensity threshold -> no change
        a = gray(100)
        b = gray(110)
        assert diff_ratio(a, b, intensity_threshold=25) == 0.0

    def test_suprathreshold_intensity_counts(self):
        a = gray(100)
        b = gray(130)  # +30 > 25 everywhere
        assert diff_ratio(a, b, intensity_threshold=25) == 1.0


class TestPreprocess:
    def test_grayscale_collapses_channels(self):
        frame = np.zeros((4, 4, 3), dtype=np.uint8)
        out = preprocess(frame, downscale_factor=1, grayscale=True)
        assert out.shape == (4, 4)
        assert out.dtype == np.uint8

    def test_grayscale_luminance_of_red(self):
        frame = np.zeros((2, 2, 3), dtype=np.uint8)
        frame[..., 0] = 255  # pure red (R,G,B)
        out = preprocess(frame, downscale_factor=1, grayscale=True)
        # luminance ~ 0.299 * 255 = 76
        assert np.all(np.abs(out.astype(int) - 76) <= 1)

    def test_downscale_halves_dimensions(self):
        frame = np.zeros((8, 8), dtype=np.uint8)
        out = preprocess(frame, downscale_factor=2, grayscale=False)
        assert out.shape == (4, 4)


def run_sequence(detector, frames, start=0.0, step=1.0):
    """Feed frames at increasing timestamps; return [(tick, Event), ...]."""
    events = []
    for i, frame in enumerate(frames):
        now = start + i * step
        ev = detector.update(frame, now=now)
        if ev is not None:
            events.append((i, ev))
    return events


class TestChangeDetectorFSM:
    def make(self, settle_ticks=3, cooldown_seconds=1000.0):
        return ChangeDetector(
            ratio_threshold=0.02,
            settle_ticks=settle_ticks,
            cooldown_seconds=cooldown_seconds,
            intensity_threshold=25,
        )

    def test_static_frames_no_event(self):
        det = self.make()
        events = run_sequence(det, [gray(0)] * 6)
        assert events == []

    def test_single_change_emits_once_after_settle(self):
        det = self.make(settle_ticks=3)
        base = gray(0)
        changed = half_changed()
        # change first appears at index 2; settle requires 3 still frames
        frames = [base, base, changed, changed, changed, changed, changed]
        events = run_sequence(det, frames)
        assert len(events) == 1
        tick, ev = events[0]
        assert tick == 5  # change@2 + 3 still frames
        assert isinstance(ev, Event)
        assert ev.ratio >= 0.02
        assert np.array_equal(ev.frame, changed)

    def test_ongoing_animation_no_event_until_settled(self):
        det = self.make(settle_ticks=3)
        base = gray(0)
        a = half_changed()
        b = gray(255)  # differs from `a` every tick -> continuous motion
        frames = [base, base] + [a, b] * 5  # never two equal consecutive frames
        events = run_sequence(det, frames)
        assert events == []

    def test_transient_flash_reverting_to_baseline_no_event(self):
        det = self.make(settle_ticks=2)
        base = gray(0)
        flash = half_changed()
        # flash appears for one tick then reverts and settles back to baseline
        frames = [base, base, flash, base, base, base]
        events = run_sequence(det, frames)
        assert events == []

    def test_reset_returns_to_idle_and_rebaselines(self):
        det = self.make(settle_ticks=2)
        det.update(gray(0), now=0.0)        # baseline established
        det.update(half_changed(), now=1.0)  # now CHANGING
        det.reset()
        # after reset the next frame becomes the new baseline (no event), even
        # though it differs from the original baseline
        assert det.update(half_changed(), now=2.0) is None
        assert det.update(half_changed(), now=3.0) is None
        assert det.update(half_changed(), now=4.0) is None

    def test_reset_models_resume_no_alert_for_changes_during_gap(self):
        # mimics pause->resume: whatever is on screen at resume becomes the new
        # baseline, so only a NEW change after resume should alert.
        det = self.make(settle_ticks=2)
        a, b, c = gray(0), half_changed(), gray(255)
        det.update(a, now=0.0)              # baseline a
        det.reset()                         # "resume"
        # b is on screen at resume -> absorbed as baseline, no alert
        det.update(b, now=1.0)
        det.update(b, now=2.0)
        det.update(b, now=3.0)
        # a genuinely new change (c) appears and settles -> one alert
        events = [det.update(c, now=t) for t in (4.0, 5.0, 6.0)]
        assert sum(e is not None for e in events) == 1

    def test_cooldown_suppresses_then_allows_new_change(self):
        det = self.make(settle_ticks=2, cooldown_seconds=10.0)
        base = gray(0)
        b = half_changed()
        c = gray(255)
        # phase 1: base->b settles -> emit #1 at tick 4, cooldown until t=14.
        # phase 2: c persists through cooldown; on expiry the detector rebaselines
        #          to the current frame (c) instead of alerting.
        # phase 3: a *new* change (c->base) appears after expiry, settles -> emit #2.
        frames = (
            [base, base, b, b, b]          # emit #1 at tick 4
            + [c] * 12                     # cooldown window; rebaseline to c on expiry
            + [base, base, base]           # new change after cooldown -> emit #2
        )
        events = run_sequence(det, frames)
        assert len(events) == 2
        assert events[0][0] == 4
        assert events[1][0] > 14  # strictly after cooldown expired
