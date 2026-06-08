import pytest

from changedetector.geometry import (
    Region,
    normalize_drag,
    clamp_to_virtual_screen,
    resolve_region,
)


class TestRegion:
    def test_to_mss_dict(self):
        r = Region(left=10, top=20, width=30, height=40)
        assert r.to_mss_dict() == {"left": 10, "top": 20, "width": 30, "height": 40}

    def test_right_and_bottom(self):
        r = Region(left=10, top=20, width=30, height=40)
        assert r.right == 40
        assert r.bottom == 60


class TestNormalizeDrag:
    def test_top_left_to_bottom_right(self):
        assert normalize_drag(10, 20, 50, 80) == Region(10, 20, 40, 60)

    def test_bottom_right_to_top_left(self):
        # dragging in reverse yields the same region
        assert normalize_drag(50, 80, 10, 20) == Region(10, 20, 40, 60)

    def test_mixed_direction(self):
        assert normalize_drag(50, 20, 10, 80) == Region(10, 20, 40, 60)

    def test_rounds_to_int(self):
        r = normalize_drag(10.6, 20.2, 50.9, 80.4)
        assert isinstance(r.left, int) and isinstance(r.width, int)
        assert r == Region(11, 20, 40, 60)


class TestClampToVirtualScreen:
    # primary-only virtual screen at origin
    VBOX = {"left": 0, "top": 0, "width": 1920, "height": 1080}

    def test_fully_inside_unchanged(self):
        r = Region(100, 100, 200, 200)
        assert clamp_to_virtual_screen(r, self.VBOX) == r

    def test_clamps_overflow_right_and_bottom(self):
        r = Region(1800, 1000, 400, 400)
        assert clamp_to_virtual_screen(r, self.VBOX) == Region(1800, 1000, 120, 80)

    def test_clamps_origin_before_left_top(self):
        # region starts left of / above the virtual screen
        r = Region(-50, -30, 200, 100)
        assert clamp_to_virtual_screen(r, self.VBOX) == Region(0, 0, 150, 70)

    def test_negative_origin_virtual_screen(self):
        # secondary monitor positioned to the left of primary
        vbox = {"left": -1920, "top": 0, "width": 3840, "height": 1080}
        r = Region(-1900, 100, 300, 200)
        assert clamp_to_virtual_screen(r, vbox) == r

    def test_negative_origin_overflow_clamped(self):
        vbox = {"left": -1920, "top": 0, "width": 1920, "height": 1080}
        r = Region(-100, 100, 300, 200)  # extends past right edge (0)
        assert clamp_to_virtual_screen(r, vbox) == Region(-100, 100, 100, 200)


class TestResolveRegion:
    # mss-style list: [0] = virtual screen, [1..] = individual monitors
    MONITORS = [
        {"left": -1920, "top": 0, "width": 3840, "height": 1080},  # virtual
        {"left": 0, "top": 0, "width": 1920, "height": 1080},       # monitor 1 (primary)
        {"left": -1920, "top": 0, "width": 1920, "height": 1080},   # monitor 2 (left of primary)
    ]

    def test_none_monitor_passthrough(self):
        r = Region(100, 200, 300, 400)
        assert resolve_region(r, None, self.MONITORS) == r

    def test_relative_to_primary(self):
        r = Region(100, 50, 300, 200)
        assert resolve_region(r, 1, self.MONITORS) == Region(100, 50, 300, 200)

    def test_relative_to_secondary_negative_origin(self):
        r = Region(100, 50, 300, 200)
        # monitor 2 has left=-1920, so absolute left = -1920 + 100
        assert resolve_region(r, 2, self.MONITORS) == Region(-1820, 50, 300, 200)

    def test_out_of_range_monitor_raises(self):
        with pytest.raises(ValueError):
            resolve_region(Region(0, 0, 10, 10), 5, self.MONITORS)
