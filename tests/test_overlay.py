from changedetector.overlay import resolved_areas
from changedetector.config import Watcher, DetectionConfig
from changedetector.geometry import Region


def W(name, region, monitor=None):
    return Watcher(name=name, region=region, monitor=monitor,
                   detection=DetectionConfig(), message="m")


MONITORS = [
    {"left": -1920, "top": 0, "width": 3840, "height": 1080},  # virtual
    {"left": 0, "top": 0, "width": 1920, "height": 1080},       # monitor 1
    {"left": -1920, "top": 0, "width": 1920, "height": 1080},   # monitor 2 (left)
]


def test_absolute_region_passthrough():
    assert resolved_areas([W("A", Region(10, 20, 30, 40))], None) == [("A", Region(10, 20, 30, 40))]


def test_resolves_monitor_relative_region():
    areas = resolved_areas([W("B", Region(5, 5, 10, 10), monitor=2)], MONITORS)
    assert areas == [("B", Region(-1915, 5, 10, 10))]


def test_multiple_areas_preserve_order():
    ws = [W("A", Region(0, 0, 1, 1)), W("B", Region(2, 2, 2, 2))]
    assert [name for name, _ in resolved_areas(ws, None)] == ["A", "B"]


def test_monitor_relative_without_monitors_falls_back_to_as_is():
    areas = resolved_areas([W("C", Region(1, 2, 3, 4), monitor=2)], None)
    assert areas == [("C", Region(1, 2, 3, 4))]
